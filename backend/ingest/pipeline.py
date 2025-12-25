from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import psycopg
from psycopg.types.json import Jsonb

MAX_CONTENT_LEN = 32_000
MAX_TURN_SUMMARY_LEN = 4_000
ALLOWED_ROLES = {"user", "assistant"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def dsn_from_env() -> str:
    user = os.environ.get("POSTGRES_USER", "lens")
    password = os.environ.get("POSTGRES_PASSWORD", "lens")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "lens")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


@dataclass
class IngestStats:
    conversations_written: int = 0
    conversations_skipped: int = 0
    messages_written: int = 0
    messages_role_skipped: int = 0
    messages_content_empty_skipped: int = 0
    messages_truncated: int = 0
    turn_summary_truncated: int = 0
    lines_processed: int = 0

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IngestConfig:
    dsn: Optional[str] = None
    content_limit: int = MAX_CONTENT_LEN
    turn_summary_limit: int = MAX_TURN_SUMMARY_LEN


def scrub_nulls(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [scrub_nulls(item) for item in value]
    if isinstance(value, dict):
        return {k: scrub_nulls(v) for k, v in value.items()}
    return value


def ingest_jsonl(path: str | Path, config: Optional[IngestConfig] = None) -> IngestStats:
    cfg = config or IngestConfig()
    stats = IngestStats()
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"Input not found: {source_path}")

    dsn = cfg.dsn or dsn_from_env()
    started_at = utcnow()

    with psycopg.connect(dsn) as conn:
        run_id = create_ingest_run(conn, str(source_path), started_at, stats)
        conn.commit()
        try:
            for line_no, convo in enumerate(iter_jsonl(source_path), start=1):
                stats.lines_processed += 1
                convo_clean = scrub_nulls(convo)
                conv_id = upsert_conversation(conn, convo_clean, stats)
                insert_messages(
                    conn,
                    conv_id,
                    convo_clean.get("mapping") or {},
                    cfg,
                    stats,
                )
                conn.commit()
            finalize_ingest_run(conn, run_id, "succeeded", stats, None)
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            finalize_ingest_run(conn, run_id, "failed", stats, str(exc))
            conn.commit()
            raise
    return stats


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as err:
                raise ValueError(f"Malformed JSON at line {line_no}: {err}") from err


def create_ingest_run(
    conn: psycopg.Connection[Any],
    source_path: str,
    started_at: datetime,
    stats: IngestStats,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_runs (source_path, started_at, status, stats)
            VALUES (%s, %s, 'running', %s)
            RETURNING id
            """,
            (source_path, started_at, Jsonb(stats.to_json())),
        )
        run_id = cur.fetchone()[0]
    return run_id


def finalize_ingest_run(
    conn: psycopg.Connection[Any],
    run_id: str,
    status: str,
    stats: IngestStats,
    error: Optional[str],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingest_runs
            SET completed_at = %s,
                status = %s,
                stats = %s,
                error = %s
            WHERE id = %s
            """,
            (utcnow(), status, Jsonb(stats.to_json()), error, run_id),
        )


def upsert_conversation(
    conn: psycopg.Connection[Any],
    convo: Dict[str, Any],
    stats: IngestStats,
) -> str:
    conv_id = convo.get("id") or convo.get("conversation_id")
    if not conv_id:
        raise ValueError("Conversation missing id")

    create_ts = to_timestamp(convo.get("create_time"))
    update_ts = to_timestamp(convo.get("update_time"))

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (
                id, title, create_time, update_time, current_node,
                is_archived, is_starred, origin, default_model_slug, memory_scope, raw
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                conv_id,
                convo.get("title"),
                create_ts,
                update_ts,
                convo.get("current_node"),
                convo.get("is_archived", False),
                convo.get("is_starred"),
                convo.get("conversation_origin") or convo.get("origin"),
                convo.get("default_model_slug"),
                convo.get("memory_scope"),
                Jsonb(convo),
            ),
        )
        if cur.rowcount == 1:
            stats.conversations_written += 1
        else:
            stats.conversations_skipped += 1

    return conv_id


def insert_messages(
    conn: psycopg.Connection[Any],
    conv_id: str,
    mapping: Dict[str, Any],
    config: IngestConfig,
    stats: IngestStats,
) -> None:
    children, roots = build_children_index(mapping)
    message_id_by_node: Dict[str, str] = {}
    idx_in_conv = 0

    def parent_message_id(node_id: Optional[str]) -> Optional[str]:
        current = node_id
        while current:
            if current in message_id_by_node:
                return message_id_by_node[current]
            current = mapping.get(current, {}).get("parent")
        return None

    with conn.cursor() as cur:
        for node_id in traverse_nodes(roots, children, mapping):
            node = mapping.get(node_id) or {}
            message = node.get("message")
            if not message:
                continue

            role = (message.get("author") or {}).get("role")
            if role not in ALLOWED_ROLES:
                stats.messages_role_skipped += 1
                continue

            content_raw = message.get("content")
            content = content_raw if isinstance(content_raw, dict) else {}
            metadata_raw = message.get("metadata")
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
            content_text = extract_content_text(content)
            if not content_text or not content_text.strip():
                stats.messages_content_empty_skipped += 1
                continue
            truncated = False
            if content_text and len(content_text) > config.content_limit:
                content_text = content_text[: config.content_limit]
                truncated = True
                stats.messages_truncated += 1

            turn_summary = extract_turn_summary(metadata)
            summary_truncated = False
            if turn_summary and len(turn_summary) > config.turn_summary_limit:
                turn_summary = turn_summary[: config.turn_summary_limit]
                summary_truncated = True
                stats.turn_summary_truncated += 1

            parent_id = parent_message_id(node.get("parent"))
            message_id = message.get("id")
            if not message_id:
                raise ValueError(f"Message missing id for node {node_id}")

            cur.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, role, parent_id, idx_in_conv,
                    create_time, update_time, content_text, content_parts, content_type,
                    turn_summary, model_slug, finish_type, finish_stop, weight,
                    end_turn, recipient, channel, request_id, turn_exchange_id, metadata, raw
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                    conversation_id = EXCLUDED.conversation_id,
                    role = EXCLUDED.role,
                    parent_id = EXCLUDED.parent_id,
                    idx_in_conv = EXCLUDED.idx_in_conv,
                    create_time = EXCLUDED.create_time,
                    update_time = EXCLUDED.update_time,
                    content_text = EXCLUDED.content_text,
                    content_parts = EXCLUDED.content_parts,
                    content_type = EXCLUDED.content_type,
                    turn_summary = EXCLUDED.turn_summary,
                    model_slug = EXCLUDED.model_slug,
                    finish_type = EXCLUDED.finish_type,
                    finish_stop = EXCLUDED.finish_stop,
                    weight = EXCLUDED.weight,
                    end_turn = EXCLUDED.end_turn,
                    recipient = EXCLUDED.recipient,
                    channel = EXCLUDED.channel,
                    request_id = EXCLUDED.request_id,
                    turn_exchange_id = EXCLUDED.turn_exchange_id,
                    metadata = EXCLUDED.metadata,
                    raw = EXCLUDED.raw
                """,
                (
                    message_id,
                    conv_id,
                    role,
                    parent_id,
                    idx_in_conv,
                    to_timestamp(message.get("create_time")),
                    to_timestamp(message.get("update_time")),
                    content_text,
                    Jsonb(content) if content else None,
                    (content or {}).get("content_type"),
                    turn_summary,
                    metadata.get("model_slug"),
                    extract_finish_type(metadata),
                    extract_finish_stop(metadata),
                    message.get("weight"),
                    message.get("end_turn"),
                    message.get("recipient"),
                    message.get("channel"),
                    metadata.get("request_id"),
                    metadata.get("turn_exchange_id") or metadata.get("exchange_id"),
                    Jsonb(metadata) if metadata else None,
                    Jsonb(message),
                ),
            )

            message_id_by_node[node_id] = message_id
            stats.messages_written += 1
            idx_in_conv += 1
            if truncated or summary_truncated:
                # Already counted in stats; kept for clarity.
                pass


def build_children_index(
    mapping: Dict[str, Any],
) -> Tuple[Dict[str, List[str]], List[str]]:
    children: Dict[str, List[str]] = {}
    roots: List[str] = []
    for node_id, node in mapping.items():
        parent_id = node.get("parent")
        if parent_id:
            children.setdefault(parent_id, []).append(node_id)
        else:
            roots.append(node_id)
    return children, roots


def traverse_nodes(
    roots: List[str],
    children: Dict[str, List[str]],
    mapping: Dict[str, Any],
) -> Iterable[str]:
    def sort_key(node_id: str) -> Tuple[float, str]:
        message = (mapping.get(node_id) or {}).get("message") or {}
        ts = message.get("create_time")
        ts = ts if isinstance(ts, (int, float)) else message.get("update_time") or 0.0
        return (float(ts), node_id)

    def dfs(node_id: str) -> Iterable[str]:
        yield node_id
        for child_id in sorted(children.get(node_id, []), key=sort_key):
            yield from dfs(child_id)

    for root_id in sorted(roots, key=sort_key):
        yield from dfs(root_id)


def extract_content_text(content: Dict[str, Any]) -> Optional[str]:
    parts = content.get("parts")
    texts: List[str] = []
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict):
                if "text" in part and isinstance(part["text"], str):
                    texts.append(part["text"])
                elif "content" in part and isinstance(part["content"], str):
                    texts.append(part["content"])
    for key in ("user_instructions", "text"):
        val = content.get(key)
        if isinstance(val, str):
            texts.append(val)
    if not texts:
        return None
    return "\n".join(texts)


def extract_turn_summary(metadata: Dict[str, Any]) -> Optional[str]:
    summary = metadata.get("turn_summary")
    if isinstance(summary, list):
        summary = "\n".join(str(item) for item in summary)
    if isinstance(summary, str):
        return summary
    return None


def extract_finish_type(metadata: Dict[str, Any]) -> Optional[str]:
    finish = metadata.get("finish_details") or {}
    if isinstance(finish, dict):
        return finish.get("type")
    return None


def extract_finish_stop(metadata: Dict[str, Any]) -> Optional[str]:
    finish = metadata.get("finish_details") or {}
    if isinstance(finish, dict):
        stop = finish.get("stop")
        if isinstance(stop, str):
            return stop
    return None


def to_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError):
        return None


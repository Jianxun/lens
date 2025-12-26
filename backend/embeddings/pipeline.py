from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

import httpx
import psycopg

MAX_CONTENT_LEN = 32_000


def dsn_from_env() -> str:
    user = os.environ.get("POSTGRES_USER", "lens")
    password = os.environ.get("POSTGRES_PASSWORD", "lens")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "lens")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


@dataclass
class EmbeddingCandidate:
    user_message_id: str
    assistant_message_id: str
    user_text: str
    assistant_text: str
    turn_summary: Optional[str]
    existing_hash: Optional[str]


@dataclass
class EmbeddingResult:
    embedded: int = 0
    skipped_existing_hash: int = 0
    batches: int = 0


@dataclass
class EmbeddingConfig:
    dsn: Optional[str] = None
    provider: str = "supermind"
    model: str = "text-embedding-3-large"
    batch_size: int = 32
    max_content_len: int = MAX_CONTENT_LEN
    base_url: str = "https://space.ai-builders.com/backend/v1"
    api_key_env: str = "SUPER_MIND_API_KEY"
    timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0
    force: bool = False


class EmbeddingFetchError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def fetch_candidates(
    conn: psycopg.Connection[Any],
    provider: str,
    model: str,
    limit: int,
    offset: int,
) -> List[EmbeddingCandidate]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                a.id AS assistant_message_id,
                u.id AS user_message_id,
                u.content_text AS user_text,
                a.content_text AS assistant_text,
                u.turn_summary AS turn_summary,
                me.content_hash AS existing_hash
            FROM messages a
            JOIN messages u ON u.id = a.parent_id
            LEFT JOIN message_embeddings me
              ON me.user_message_id = u.id
             AND me.provider = %s
             AND me.model = %s
            WHERE a.role = 'assistant'
              AND u.role = 'user'
              AND a.content_text IS NOT NULL
              AND length(a.content_text) > 0
              AND u.content_text IS NOT NULL
              AND length(u.content_text) > 0
            ORDER BY COALESCE(a.create_time, u.create_time) ASC
            LIMIT %s
            OFFSET %s
            """,
            (provider, model, limit, offset),
        )
        rows = cur.fetchall()
    return [
        EmbeddingCandidate(
            user_message_id=row[1],
            assistant_message_id=row[0],
            user_text=row[2],
            assistant_text=row[3],
            turn_summary=row[4],
            existing_hash=row[5],
        )
        for row in rows
    ]


def build_content(
    user_text: str,
    assistant_text: str,
    turn_summary: Optional[str],
    max_len: int,
) -> Tuple[str, bool]:
    assistant_part = (turn_summary or "").strip() or assistant_text
    used_summary = bool(turn_summary and turn_summary.strip())
    content = f"User: {user_text}\nAssistant: {assistant_part}"
    if len(content) > max_len:
        content = content[:max_len]
    return content, used_summary


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def embedding_client(cfg: EmbeddingConfig) -> httpx.Client:
    api_key = os.environ.get(cfg.api_key_env)
    if not api_key:
        raise RuntimeError(f"{cfg.api_key_env} is not set")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return httpx.Client(base_url=cfg.base_url, headers=headers, timeout=cfg.timeout_seconds)


def fetch_embeddings(
    client: httpx.Client,
    model: str,
    texts: Sequence[str],
    max_retries: int,
    backoff: float,
) -> List[List[float]]:
    last_exc: Optional[Exception] = None
    last_status: Optional[int] = None
    last_body: Optional[str] = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.post(
                "/embeddings",
                json={"model": model, "input": list(texts)},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = [item["embedding"] for item in data.get("data", [])]
            if len(embeddings) != len(texts):
                raise ValueError(
                    f"Embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
                )
            return embeddings
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            last_status, last_body = _extract_response_details(exc)
            if attempt == max_retries:
                break
            time.sleep(backoff * attempt)
    _log_retry_failure(model, max_retries, len(texts), last_exc, last_status, last_body)
    raise EmbeddingFetchError(
        f"Failed to fetch embeddings after {max_retries} attempts",
        status=last_status,
        body=last_body,
    ) from last_exc


def _extract_response_details(exc: Exception) -> Tuple[Optional[int], Optional[str]]:
    response = None
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
    elif isinstance(exc, httpx.HTTPError):
        response = exc.response
    if response is None:
        return None, None
    try:
        body = response.text
    except Exception:  # noqa: BLE001
        body = "<unable to read response text>"
    body = (body or "").strip().replace("\n", " ")
    max_len = 500
    if len(body) > max_len:
        body = f"{body[:max_len]}...(truncated)"
    return response.status_code, body


def _log_retry_failure(
    model: str,
    attempts: int,
    text_count: int,
    exc: Optional[Exception],
    status: Optional[int],
    body: Optional[str],
) -> None:
    if exc is None:
        return
    parts = [
        "[embeddings] retries_exhausted",
        f"model={model}",
        f"attempts={attempts}",
        f"text_count={text_count}",
        f"error_type={type(exc).__name__}",
    ]
    if status is not None:
        parts.append(f"status={status}")
    if body:
        parts.append(f"response_snippet={body}")
    parts.append(f"error={exc}")
    print(" ".join(parts), file=sys.stderr)


def _is_context_length_error(exc: EmbeddingFetchError) -> bool:
    if exc.status != 400:
        return False
    if not exc.body:
        return False
    lowered = exc.body.lower()
    return "maximum context length" in lowered or "requested" in lowered and "tokens" in lowered


def _log_context_skip(
    user_ids: Sequence[Any],
    assistant_ids: Sequence[Any],
    content_hashes: Sequence[str],
    exc: EmbeddingFetchError,
) -> None:
    def _join(values: Sequence[Any]) -> str:
        head = [str(v) for v in values[:5]]
        return ",".join(head) + ("..." if len(values) > 5 else "")

    snippet = (exc.body or "").replace("\n", " ")
    if len(snippet) > 300:
        snippet = f"{snippet[:300]}...(truncated)"
    print(
        "[embeddings] batch_skipped reason=context_length "
        f"user_ids={_join(user_ids)} assistant_ids={_join(assistant_ids)} "
        f"hashes={_join(content_hashes)} status={exc.status} response_snippet={snippet}",
        file=sys.stderr,
    )

def to_vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def upsert_embeddings(
    conn: psycopg.Connection[Any],
    provider: str,
    model: str,
    content_hashes: Sequence[str],
    contents: Sequence[str],
    used_summaries: Sequence[bool],
    embeddings: Sequence[Sequence[float]],
    user_ids: Sequence[str],
    assistant_ids: Sequence[str],
) -> int:
    with conn.cursor() as cur:
        for idx, emb in enumerate(embeddings):
            vector_lit = to_vector_literal(emb)
            dim = len(emb)
            cur.execute(
                """
                INSERT INTO message_embeddings (
                    user_message_id,
                    assistant_message_id,
                    provider,
                    model,
                    dim,
                    content_used,
                    content_hash,
                    used_turn_summary,
                    vector
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (user_message_id, provider, model)
                DO UPDATE SET
                    assistant_message_id = EXCLUDED.assistant_message_id,
                    dim = EXCLUDED.dim,
                    content_used = EXCLUDED.content_used,
                    content_hash = EXCLUDED.content_hash,
                    used_turn_summary = EXCLUDED.used_turn_summary,
                    vector = EXCLUDED.vector,
                    created_at = now()
                """,
                (
                    user_ids[idx],
                    assistant_ids[idx],
                    provider,
                    model,
                    dim,
                    contents[idx],
                    content_hashes[idx],
                    used_summaries[idx],
                    vector_lit,
                ),
            )
    return len(embeddings)


def run_embedding_job(
    cfg: Optional[EmbeddingConfig] = None,
    limit: Optional[int] = None,
) -> EmbeddingResult:
    cfg = cfg or EmbeddingConfig()
    dsn = cfg.dsn or dsn_from_env()
    stats = EmbeddingResult()
    client = embedding_client(cfg)

    with psycopg.connect(dsn) as conn:
        processed = 0
        while True:
            remaining = None if limit is None else max(limit - processed, 0)
            if remaining is not None and remaining == 0:
                break
            batch_limit = cfg.batch_size if remaining is None else min(cfg.batch_size, remaining)
            candidates = fetch_candidates(
                conn,
                cfg.provider,
                cfg.model,
                batch_limit,
                processed,
            )
            if not candidates:
                break

            contents: List[str] = []
            hashes: List[str] = []
            used_summaries: List[bool] = []
            user_ids: List[str] = []
            assistant_ids: List[str] = []
            batch_skipped = 0

            for cand in candidates:
                content, used_summary = build_content(
                    cand.user_text,
                    cand.assistant_text,
                    cand.turn_summary,
                    cfg.max_content_len,
                )
                content_hash = sha256_text(content)
                if (
                    not cfg.force
                    and cand.existing_hash
                    and cand.existing_hash == content_hash
                ):
                    stats.skipped_existing_hash += 1
                    batch_skipped += 1
                    continue
                contents.append(content)
                hashes.append(content_hash)
                used_summaries.append(used_summary)
                user_ids.append(cand.user_message_id)
                assistant_ids.append(cand.assistant_message_id)

            if not contents:
                processed += len(candidates)
                continue

            try:
                embeddings = fetch_embeddings(
                    client,
                    cfg.model,
                    contents,
                    cfg.max_retries,
                    cfg.retry_backoff_seconds,
                )
            except EmbeddingFetchError as exc:
                if _is_context_length_error(exc):
                    _log_context_skip(user_ids, assistant_ids, hashes, exc)
                    processed += len(candidates)
                    continue
                raise
            upserted = upsert_embeddings(
                conn,
                cfg.provider,
                cfg.model,
                hashes,
                contents,
                used_summaries,
                embeddings,
                user_ids,
                assistant_ids,
            )
            conn.commit()

            stats.embedded += upserted
            stats.batches += 1
            processed += len(candidates)
            print(
                f"[embeddings] batch={stats.batches} embedded={upserted} "
                f"skipped_hash={batch_skipped} total_embedded={stats.embedded} "
                f"processed={processed}"
            )
    return stats

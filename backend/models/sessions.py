from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

MAX_CONTENT_LEN = 32_000


class SessionNotFound(Exception):
    """Raised when a session cannot be located."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _conversation_from_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[UUID]:
    if not metadata or not isinstance(metadata, dict):
        return None
    value = metadata.get("conversation_id")
    if not value:
        return None
    try:
        return UUID(str(value))
    except Exception:  # noqa: BLE001
        return None


def _ensure_conversation(conn: psycopg.Connection, conversation_id: UUID, title: Optional[str] = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversations (id, title, create_time, update_time, raw)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (conversation_id, title, utcnow(), utcnow(), Jsonb({"created_by": "sessions_api"})),
        )


def create_session(conn: psycopg.Connection, *, title: Optional[str] = None) -> Tuple[UUID, UUID]:
    conversation_id = uuid4()
    _ensure_conversation(conn, conversation_id, title=title)
    session_id = uuid4()
    metadata = {"conversation_id": str(conversation_id)}
    now = utcnow()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at, pinned, archived, metadata)
            VALUES (%s, %s, %s, %s, false, false, %s)
            """,
            (session_id, title, now, now, Jsonb(metadata)),
        )
    return session_id, conversation_id


def _fetch_session_row(conn: psycopg.Connection, session_id: UUID) -> Tuple:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, created_at, updated_at, pinned, archived, metadata
            FROM sessions
            WHERE id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()
    if not row:
        raise SessionNotFound(f"session {session_id} not found")
    return row


def _conversation_id_for_session(conn: psycopg.Connection, session_id: UUID, metadata: Optional[Dict[str, Any]]) -> UUID:
    from_meta = _conversation_from_metadata(metadata)
    if from_meta:
        _ensure_conversation(conn, from_meta)
        return from_meta

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.conversation_id
            FROM session_messages sm
            JOIN messages m ON sm.message_id = m.id
            WHERE sm.session_id = %s
            ORDER BY sm.idx ASC, sm.created_at ASC
            LIMIT 1
            """,
            (session_id,),
        )
        found = cur.fetchone()
    if found and found[0]:
        conversation_id = found[0]
        _ensure_conversation(conn, conversation_id)
        _persist_conversation_metadata(conn, session_id, metadata, conversation_id)
        return conversation_id

    conversation_id = uuid4()
    _ensure_conversation(conn, conversation_id)
    _persist_conversation_metadata(conn, session_id, metadata, conversation_id)
    return conversation_id


def _persist_conversation_metadata(
    conn: psycopg.Connection,
    session_id: UUID,
    metadata: Optional[Dict[str, Any]],
    conversation_id: UUID,
) -> None:
    updated_meta = dict(metadata or {})
    updated_meta["conversation_id"] = str(conversation_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sessions
            SET metadata = %s, updated_at = %s
            WHERE id = %s
            """,
            (Jsonb(updated_meta), utcnow(), session_id),
        )


def list_sessions(conn: psycopg.Connection, *, include_archived: bool = False) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                s.id,
                s.title,
                s.updated_at,
                s.pinned,
                s.archived,
                COALESCE(COUNT(sm.id), 0) AS message_count
            FROM sessions s
            LEFT JOIN session_messages sm ON sm.session_id = s.id
            WHERE %s OR s.archived = false
            GROUP BY s.id
            ORDER BY s.pinned DESC, s.updated_at DESC
            """,
            (include_archived,),
        )
        for row in cur.fetchall():
            rows.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "updated_at": row[2],
                    "pinned": row[3],
                    "archived": row[4],
                    "message_count": row[5],
                }
            )
    return rows


def fetch_session_details(conn: psycopg.Connection, session_id: UUID, *, include_archived: bool = False) -> Dict[str, Any]:
    session_row = _fetch_session_row(conn, session_id)
    session = {
        "id": session_row[0],
        "title": session_row[1],
        "created_at": session_row[2],
        "updated_at": session_row[3],
        "pinned": session_row[4],
        "archived": session_row[5],
        "metadata": session_row[6] if isinstance(session_row[6], dict) else None,
    }
    if session["archived"] and not include_archived:
        raise SessionNotFound(f"session {session_id} not found")

    conversation_id = _conversation_id_for_session(conn, session_id, session["metadata"])
    messages = _fetch_session_messages(conn, session_id)
    session["conversation_id"] = conversation_id
    session["messages"] = messages
    session["message_count"] = len(messages)
    return session


def patch_session(
    conn: psycopg.Connection,
    session_id: UUID,
    *,
    title: Optional[str] = None,
    pinned: Optional[bool] = None,
    archived: Optional[bool] = None,
) -> Dict[str, Any]:
    _fetch_session_row(conn, session_id)
    fields: List[str] = []
    params: List[Any] = []
    if title is not None:
        fields.append("title = %s")
        params.append(title)
    if pinned is not None:
        fields.append("pinned = %s")
        params.append(pinned)
    if archived is not None:
        fields.append("archived = %s")
        params.append(archived)
    fields.append("updated_at = %s")
    params.append(utcnow())
    params.append(session_id)

    set_clause = ", ".join(fields)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE sessions
            SET {set_clause}
            WHERE id = %s
            """,
            params,
        )
    return fetch_session_details(conn, session_id, include_archived=True)


def soft_archive_session(conn: psycopg.Connection, session_id: UUID) -> Dict[str, Any]:
    return patch_session(conn, session_id, archived=True)


def _next_idx_for_conversation(conn: psycopg.Connection, conversation_id: UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(idx_in_conv) + 1, 0) FROM messages WHERE conversation_id = %s",
            (conversation_id,),
        )
        row = cur.fetchone()
    return int(row[0] or 0)


def _next_idx_for_session(conn: psycopg.Connection, session_id: UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(idx) + 1, 0) FROM session_messages WHERE session_id = %s",
            (session_id,),
        )
        row = cur.fetchone()
    return int(row[0] or 0)


def _insert_message(
    conn: psycopg.Connection,
    conversation_id: UUID,
    *,
    role: str,
    content_text: str,
    idx_in_conv: int,
) -> UUID:
    message_id = uuid4()
    now = utcnow()
    content_trimmed = (content_text or "").strip()
    if content_trimmed and len(content_trimmed) > MAX_CONTENT_LEN:
        content_trimmed = content_trimmed[:MAX_CONTENT_LEN]
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (
                id, conversation_id, role, idx_in_conv, create_time, update_time, content_text, raw
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                conversation_id,
                role,
                idx_in_conv,
                now,
                now,
                content_trimmed,
                Jsonb({"created_by": "chat_api", "role": role}),
            ),
        )
    return message_id


def _link_session_message(conn: psycopg.Connection, session_id: UUID, message_id: UUID, idx: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO session_messages (session_id, message_id, idx)
            VALUES (%s, %s, %s)
            """,
            (session_id, message_id, idx),
        )


def append_turn(
    conn: psycopg.Connection,
    session_id: UUID,
    *,
    user_content: str,
    assistant_content: str,
) -> Dict[str, Any]:
    session_row = _fetch_session_row(conn, session_id)
    archived = bool(session_row[5])
    if archived:
        raise ValueError("Cannot append to an archived session")
    metadata = session_row[6] if isinstance(session_row[6], dict) else None
    conversation_id = _conversation_id_for_session(conn, session_id, metadata)

    base_idx_conv = _next_idx_for_conversation(conn, conversation_id)
    base_idx_session = _next_idx_for_session(conn, session_id)

    user_id = _insert_message(
        conn,
        conversation_id,
        role="user",
        content_text=user_content,
        idx_in_conv=base_idx_conv,
    )
    _link_session_message(conn, session_id, user_id, base_idx_session)

    assistant_id = _insert_message(
        conn,
        conversation_id,
        role="assistant",
        content_text=assistant_content,
        idx_in_conv=base_idx_conv + 1,
    )
    _link_session_message(conn, session_id, assistant_id, base_idx_session + 1)

    return {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "user_message_id": user_id,
        "assistant_message_id": assistant_id,
    }


def _fetch_session_messages(conn: psycopg.Connection, session_id: UUID) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                sm.idx,
                sm.created_at,
                m.id,
                m.role,
                m.content_text,
                m.create_time,
                m.conversation_id
            FROM session_messages sm
            JOIN messages m ON sm.message_id = m.id
            WHERE sm.session_id = %s
            ORDER BY sm.idx ASC, COALESCE(m.create_time, sm.created_at) ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    messages: List[Dict[str, Any]] = []
    for row in rows:
        messages.append(
            {
                "idx": row[0],
                "session_message_created_at": row[1],
                "id": row[2],
                "role": row[3],
                "content": row[4],
                "create_time": row[5],
                "conversation_id": row[6],
            }
        )
    return messages


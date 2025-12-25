from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Generator, List, Optional
from uuid import UUID

import httpx
import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

PROVIDER = "supermind"
MODEL = "text-embedding-3-large"
DEFAULT_TOP_K = 100
DEFAULT_TOP_N_SNIPPETS = 10
DEFAULT_BIN_DAYS = 1
MAX_TOP_K = 1000
MAX_TOP_N_SNIPPETS = 100
MAX_BIN_DAYS = 365
MAX_SNIPPET_LEN = 400

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class HistogramBucket(BaseModel):
    start: datetime
    end: datetime
    count: int


class Histogram(BaseModel):
    bin_days: int
    buckets: List[HistogramBucket]
    total: int


class Match(BaseModel):
    turn_id: UUID
    score: float = Field(..., description="Similarity score derived from vector distance.")
    distance: float
    user_message_id: UUID
    assistant_message_id: Optional[UUID]
    conversation_id: UUID
    create_time: Optional[datetime]
    user_snippet: str
    assistant_snippet: Optional[str]


class PeekResponse(BaseModel):
    histogram: Histogram
    matches: List[Match]


class TurnResponse(BaseModel):
    turn_id: UUID
    provider: str
    model: str
    user_message_id: UUID
    assistant_message_id: Optional[UUID]
    conversation_id: UUID
    create_time: Optional[datetime]
    user_content: Optional[str]
    assistant_content: Optional[str]
    used_turn_summary: bool
    embedding_created_at: datetime


def db_conn(request: Request) -> Generator[psycopg.Connection, None, None]:
    dsn = getattr(request.app.state, "dsn", None)
    if not dsn:
        raise HTTPException(status_code=500, detail="Database DSN not configured")
    conn = psycopg.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


def embedding_client(request: Request) -> httpx.Client:
    client = getattr(request.app.state, "embedding_client", None)
    if client is None:
        raise HTTPException(status_code=500, detail="Embedding client not configured")
    return client


def to_vector_literal(values: List[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def embed_query(client: httpx.Client, text: str) -> List[float]:
    try:
        resp = client.post("/embeddings", json={"model": MODEL, "input": [text]})
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or []
        embedding = data[0]["embedding"]
        if not isinstance(embedding, list):
            raise KeyError("embedding")
        return embedding
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Failed to fetch embedding") from exc


def score_from_distance(distance: float) -> float:
    return 1.0 / (1.0 + distance)


def trim_snippet(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = text.strip()
    if len(text) > MAX_SNIPPET_LEN:
        return text[:MAX_SNIPPET_LEN]
    return text


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def bin_timestamp(ts: datetime, bin_seconds: int) -> datetime:
    ts_utc = ts.astimezone(timezone.utc)
    bucket_start = int(ts_utc.timestamp()) // bin_seconds * bin_seconds
    return datetime.fromtimestamp(bucket_start, tz=timezone.utc)


@router.get("/peek", response_model=PeekResponse)
def peek(
    query: str = Query(..., min_length=1),
    top_k: int = Query(DEFAULT_TOP_K, gt=0, le=MAX_TOP_K),
    top_n_snippets: int = Query(DEFAULT_TOP_N_SNIPPETS, gt=0, le=MAX_TOP_N_SNIPPETS),
    bin_days: int = Query(DEFAULT_BIN_DAYS, gt=0, le=MAX_BIN_DAYS),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    conversation_id: Optional[UUID] = Query(None),
    conn: psycopg.Connection = Depends(db_conn),
    client: httpx.Client = Depends(embedding_client),
) -> PeekResponse:
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="start_time must be before end_time")

    start_time = ensure_utc(start_time)
    end_time = ensure_utc(end_time)

    embedding = embed_query(client, query)
    vector_literal = to_vector_literal(embedding)
    bin_seconds = bin_days * 86400

    filters = []
    params: List[object] = [vector_literal, PROVIDER, MODEL]
    if start_time:
        filters.append("u.create_time >= %s")
        params.append(start_time)
    if end_time:
        filters.append("u.create_time <= %s")
        params.append(end_time)
    if conversation_id:
        filters.append("u.conversation_id = %s")
        params.append(conversation_id)
    where_clause = ""
    if filters:
        where_clause = "AND " + " AND ".join(filters)

    params.extend([vector_literal, top_k])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                me.id AS turn_id,
                me.user_message_id,
                me.assistant_message_id,
                me.used_turn_summary,
                me.created_at,
                u.conversation_id,
                u.create_time AS user_create_time,
                u.content_text AS user_text,
                a.content_text AS assistant_text,
                a.turn_summary AS assistant_summary,
                (me.vector <-> %s::vector) AS distance
            FROM message_embeddings me
            JOIN messages u ON me.user_message_id = u.id
            LEFT JOIN messages a ON me.assistant_message_id = a.id
            WHERE me.provider = %s
              AND me.model = %s
              {where_clause}
            ORDER BY me.vector <-> %s::vector
            LIMIT %s
            """,
            params,
        )
        rows = cur.fetchall()

    buckets: dict[datetime, int] = {}
    matches: List[Match] = []
    max_matches = min(top_n_snippets, len(rows))

    for row in rows:
        (
            turn_id,
            user_message_id,
            assistant_message_id,
            used_turn_summary,
            _embedding_created_at,
            conv_id,
            user_create_time,
            user_text,
            assistant_text,
            assistant_summary,
            distance,
        ) = row

        user_create_time_utc = ensure_utc(user_create_time)

        if user_create_time_utc:
            bucket_start = bin_timestamp(user_create_time_utc, bin_seconds)
            buckets[bucket_start] = buckets.get(bucket_start, 0) + 1

        if len(matches) < max_matches:
            assistant_source = assistant_summary if used_turn_summary else assistant_text
            matches.append(
                Match(
                    turn_id=turn_id,
                    score=score_from_distance(distance),
                    distance=distance,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                    conversation_id=conv_id,
                    create_time=user_create_time_utc,
                    user_snippet=trim_snippet(user_text) or "",
                    assistant_snippet=trim_snippet(assistant_source),
                )
            )

    histogram_buckets = [
        HistogramBucket(
            start=start,
            end=start + timedelta(seconds=bin_seconds),
            count=count,
        )
        for start, count in sorted(buckets.items(), key=lambda item: item[0])
    ]

    return PeekResponse(
        histogram=Histogram(
            bin_days=bin_days,
            buckets=histogram_buckets,
            total=len(rows),
        ),
        matches=matches,
    )


@router.get("/turn/{turn_id}", response_model=TurnResponse)
def turn(
    turn_id: UUID,
    conn: psycopg.Connection = Depends(db_conn),
) -> TurnResponse:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                me.id,
                me.provider,
                me.model,
                me.user_message_id,
                me.assistant_message_id,
                me.used_turn_summary,
                me.created_at,
                u.conversation_id,
                u.create_time AS user_create_time,
                u.content_text AS user_text,
                a.content_text AS assistant_text,
                a.turn_summary AS assistant_summary
            FROM message_embeddings me
            JOIN messages u ON me.user_message_id = u.id
            LEFT JOIN messages a ON me.assistant_message_id = a.id
            WHERE me.id = %s
            """,
            (turn_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Turn not found")

    (
        emb_id,
        provider,
        model,
        user_message_id,
        assistant_message_id,
        used_turn_summary,
        embedding_created_at,
        conv_id,
        user_create_time,
        user_text,
        assistant_text,
        assistant_summary,
    ) = row

    assistant_content = assistant_summary if used_turn_summary else assistant_text

    return TurnResponse(
        turn_id=emb_id,
        provider=provider,
        model=model,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        conversation_id=conv_id,
        create_time=user_create_time,
        user_content=user_text,
        assistant_content=assistant_content,
        used_turn_summary=used_turn_summary,
        embedding_created_at=embedding_created_at,
    )


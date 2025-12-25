from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID, uuid4

import httpx
import psycopg

from fastapi import HTTPException

from backend.api import retrieval
from backend.models import sessions as session_store

logger = logging.getLogger(__name__)

# LLM + tool defaults
ORCHESTRATOR_MODEL = "gpt-5.1"
ORCHESTRATOR_BASE_URL_ENV = "OPENAI_BASE_URL"
ORCHESTRATOR_API_KEY_ENV = "OPENAI_API_KEY"
ORCHESTRATOR_DEFAULT_BASE_URL = "https://api.openai.com/v1/"
MAX_ROUNDS = 8
TEMPERATURE = 0.2

# Safety caps
MAX_HYDRATE_TURNS = 20
MAX_TURN_CHARS = 2000
MAX_CONTEXT_CHARS = 50000  # align to 50k token guidance
DEFAULT_TOP_K = retrieval.DEFAULT_TOP_K
DEFAULT_TOP_N_SNIPPETS = retrieval.DEFAULT_TOP_N_SNIPPETS
DEFAULT_BIN_DAYS = 7

SYSTEM_PROMPT = """
You are GPT-5 acting as Kaleidoscope's retrieval research orchestrator.

You are equipped with two tools:
1. kaleidoscope_peek — preview-only histogram + summaries (no evidence)
2. kaleidoscope_retrieve_by_id — hydrate specific user turns with verbatim evidence

Behave like an investigator, not a narrator.

Investigation protocol:
- Run multiple peeks before hydrating evidence.
- Vary probe framing, bin sizes, and optional time windows to map temporal structure.
- Use peeks to form hypotheses about phases, shifts, or tensions.
- Treat peek outputs as observations; cite only hydrated evidence.

Lineage discipline (NEW):
- Distinguish explicitly between:
  * exploratory ideas
  * debated alternatives
  * provisional conclusions
  * stable decisions
- Preserve uncertainty, disagreement, reversals, and abandoned paths.
- Avoid hindsight smoothing or narrative inevitability.

Concept tracking (NEW):
- Identify recurring concepts and note:
  * first appearance
  * refinement or re-framing points
  * points of rejection, dormancy, or stabilization
- When relevant, note concepts that appeared briefly and disappeared.

Evidence usage:
- Hydrate only representative turns needed to support claims.
- Every substantive claim must map to at least one cited turn.
- Negative findings (absence, lack of follow-up) should be stated explicitly when relevant.

Final answer requirements:
- Explicitly mention which time periods and which turns informed the reasoning.
- Structure the answer to reflect temporal phases, not just topics.
- Maintain a list of cited turns in academic citation form ([1] [2] [3] ...).
- Append the citation list to the end of the answer.

Remember:
You are producing an auditable cognitive trace, not a polished retrospective summary.

"""

PEEK_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "retrieval_peek",
        "description": "Probe the corpus to inspect histogram bins and preview snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Probe framing for preview."},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 300, "description": "Vector candidates."},
                "bin_days": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Histogram bin size (days)."},
                "top_n_snippets": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Max previews to return."},
                "start_time": {"type": "string", "description": "Optional ISO-8601 start window (UTC)."},
                "end_time": {"type": "string", "description": "Optional ISO-8601 end window (UTC)."},
                "conversation_id": {"type": "string", "description": "Optional conversation filter (UUID)."},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

TURN_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "retrieval_turn",
        "description": "Hydrate a specific turn_id with user + assistant content (summary when available).",
        "parameters": {
            "type": "object",
            "properties": {
                "turn_id": {"type": "string", "description": "Turn UUID from peek previews."},
            },
            "required": ["turn_id"],
            "additionalProperties": False,
        },
    },
}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _truncate(text: Optional[str], limit: int = MAX_TURN_CHARS) -> Optional[str]:
    if text is None:
        return None
    if len(text) > limit:
        return text[:limit]
    return text


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    try:
        parsed = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO datetime: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _build_chat_client() -> httpx.Client:
    base_url = os.environ.get(ORCHESTRATOR_BASE_URL_ENV, ORCHESTRATOR_DEFAULT_BASE_URL)
    api_key = os.environ.get(ORCHESTRATOR_API_KEY_ENV)
    if not api_key:
        raise HTTPException(status_code=502, detail="OPENAI_API_KEY is required for orchestrator runs")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # Ensure trailing slash is acceptable to httpx; caller passes relative paths.
    return httpx.Client(base_url=base_url, headers=headers, timeout=120.0)


@dataclass
class ToolRun:
    tool: str
    arguments: Dict[str, Any]
    response: Dict[str, Any]


@dataclass
class OrchestratorResult:
    intent: str
    final_answer: Optional[str]
    status: str
    rounds: int
    tool_runs: List[ToolRun] = field(default_factory=list)
    cited_turn_ids: List[str] = field(default_factory=list)
    histogram: Optional[Dict[str, Any]] = None


class RetrievalTools:
    """Adapter exposing peek + turn as LLM tools using our retrieval stack."""

    def __init__(self, dsn: str, client: httpx.Client):
        self._dsn = dsn
        self._client = client
        self._hydrated = 0

    def peek(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return {"ok": False, "error": "query is required"}

        try:
            top_k = int(arguments.get("top_k", DEFAULT_TOP_K))
            bin_days = int(arguments.get("bin_days", DEFAULT_BIN_DAYS))
            top_n_snippets = int(arguments.get("top_n_snippets", DEFAULT_TOP_N_SNIPPETS))
            start_time = _parse_iso_datetime(arguments.get("start_time"))
            end_time = _parse_iso_datetime(arguments.get("end_time"))
            conversation_id = arguments.get("conversation_id")
            conversation_uuid = UUID(conversation_id) if conversation_id else None
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"invalid arguments: {exc}"}

        embedding = retrieval.embed_query(self._client, query)
        vector_literal = retrieval.to_vector_literal(embedding)
        bin_seconds = bin_days * 86400

        filters: list[str] = []
        params: List[object] = [vector_literal, retrieval.PROVIDER, retrieval.MODEL]
        if start_time:
            filters.append("u.create_time >= %s")
            params.append(start_time)
        if end_time:
            filters.append("u.create_time <= %s")
            params.append(end_time)
        if conversation_uuid:
            filters.append("u.conversation_id = %s")
            params.append(conversation_uuid)
        where_clause = ""
        if filters:
            where_clause = "AND " + " AND ".join(filters)

        params.extend([vector_literal, top_k])

        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
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
        previews: List[Dict[str, Any]] = []
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

            user_create_time_utc = retrieval.ensure_utc(user_create_time)
            if user_create_time_utc:
                bucket_start = retrieval.bin_timestamp(user_create_time_utc, bin_seconds)
                buckets[bucket_start] = buckets.get(bucket_start, 0) + 1

            if len(previews) < max_matches:
                assistant_source = assistant_summary if used_turn_summary else assistant_text
                previews.append(
                    {
                        "turn_id": str(turn_id),
                        "conversation_id": str(conv_id),
                        "user_message_id": str(user_message_id),
                        "assistant_message_id": str(assistant_message_id) if assistant_message_id else None,
                        "create_time": _iso(user_create_time_utc),
                        "user_snippet": retrieval.trim_snippet(user_text) or "",
                        "assistant_snippet": retrieval.trim_snippet(assistant_source),
                        "score": retrieval.score_from_distance(distance),
                    }
                )

        histogram_buckets = [
            {
                "start": _iso(start),
                "end": _iso(start + timedelta(seconds=bin_seconds)),
                "count": count,
            }
            for start, count in sorted(buckets.items(), key=lambda item: item[0])
        ]

        histogram = {
            "bin_days": bin_days,
            "total": len(rows),
            "buckets": histogram_buckets,
        }

        return {
            "ok": True,
            "data": {
                "query": query,
                "top_k": top_k,
                "bin_days": bin_days,
                "top_n_snippets": top_n_snippets,
                "histogram": histogram,
                "previews": previews,
                "counts": {"total_candidates": len(rows), "preview_count": len(previews)},
                "notice": "Preview-only; hydrate with turn for evidence.",
            },
        }

    def turn(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if self._hydrated >= MAX_HYDRATE_TURNS:
            return {"ok": False, "error": "turn hydration cap reached"}
        turn_id_raw = arguments.get("turn_id")
        try:
            turn_uuid = UUID(str(turn_id_raw))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"invalid turn_id: {exc}"}

        with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
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
                (turn_uuid,),
            )
            row = cur.fetchone()

        if not row:
            return {"ok": False, "error": "turn not found"}

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
        user_trunc = _truncate(user_text)
        assistant_trunc = _truncate(assistant_content)
        truncated = (user_trunc != user_text) or (assistant_trunc != assistant_content)

        self._hydrated += 1

        return {
            "ok": True,
            "data": {
                "turn_id": str(emb_id),
                "provider": provider,
                "model": model,
                "conversation_id": str(conv_id),
                "user_message_id": str(user_message_id),
                "assistant_message_id": str(assistant_message_id) if assistant_message_id else None,
                "create_time": _iso(retrieval.ensure_utc(user_create_time)),
                "user_content": user_trunc,
                "assistant_content": assistant_trunc,
                "used_turn_summary": bool(used_turn_summary),
                "embedding_created_at": _iso(embedding_created_at),
                "truncated": truncated,
                "notice": "Evidence bundle; suitable for grounding/quoting.",
            },
        }


class LLMOrchestrator:
    """LLM-driven orchestrator that loops over peek + turn tool calls."""

    def __init__(self, *, client: httpx.Client, tools: RetrievalTools):
        self._client = client
        self._tools = tools

    def run(self, intent: str) -> OrchestratorResult:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": intent.strip()},
        ]
        tool_defs = [PEEK_TOOL_DEF, TURN_TOOL_DEF]
        tool_runs: List[ToolRun] = []
        histogram: Optional[Dict[str, Any]] = None

        for round_idx in range(1, MAX_ROUNDS + 1):
            completion = self._complete(messages=messages, tools=tool_defs)
            message = self._extract_message(completion)
            assistant_entry = {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
            }
            messages.append(assistant_entry)

            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                for call in tool_calls:
                    tool_name = call.get("function", {}).get("name")
                    tool_id = call.get("id")
                    raw_args = call.get("function", {}).get("arguments") or "{}"
                    try:
                        parsed_args = json.loads(raw_args)
                    except json.JSONDecodeError as exc:
                        response = {"ok": False, "error": f"Invalid JSON arguments: {exc}"}
                    else:
                        response = self._dispatch(tool_name, parsed_args)
                        if tool_name == "retrieval_peek" and response.get("ok"):
                            histogram = response["data"].get("histogram")
                    tool_runs.append(ToolRun(tool=tool_name or "unknown", arguments=parsed_args if isinstance(parsed_args, dict) else {}, response=response))
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": json.dumps(response),
                        }
                    )
                continue

            content = (message.get("content") or "").strip()
            if content:
                cited_turn_ids = [
                    tr.response["data"]["turn_id"]
                    for tr in tool_runs
                    if tr.tool == "retrieval_turn" and tr.response.get("ok") and tr.response.get("data")
                ]
                return OrchestratorResult(
                    intent=intent,
                    final_answer=content,
                    status="completed",
                    rounds=round_idx,
                    tool_runs=tool_runs,
                    cited_turn_ids=cited_turn_ids,
                    histogram=histogram,
                )

        return OrchestratorResult(
            intent=intent,
            final_answer=None,
            status="max_rounds_exceeded",
            rounds=MAX_ROUNDS,
            tool_runs=tool_runs,
            cited_turn_ids=[],
            histogram=histogram,
        )

    def _dispatch(self, tool_name: Optional[str], arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "retrieval_peek":
            return self._tools.peek(arguments)
        if tool_name == "retrieval_turn":
            return self._tools.turn(arguments)
        return {"ok": False, "error": f"Unknown tool '{tool_name}'"}

    def _complete(self, *, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload = {
            "model": ORCHESTRATOR_MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": TEMPERATURE,
            "stream": False,
        }
        try:
            resp = self._client.post("/chat/completions", json=payload, timeout=120.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:  # noqa: BLE001
            logger.exception("orchestrator_complete_failed")
            raise HTTPException(status_code=502, detail="Orchestrator LLM call failed") from exc

    def _extract_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        choices = payload.get("choices") or []
        if not choices:
            return {}
        return choices[0].get("message") or {}


class AgentService:
    """Runs the LLM orchestrator loop with peek/turn tools and returns answer + metadata."""

    def __init__(self, dsn: str, embedding_client: httpx.Client, chat_client: Optional[httpx.Client] = None):
        self._dsn = dsn
        self._embedding_client = embedding_client
        self._chat_client = chat_client

    def run(self, intent: str, *, session_id: Optional[UUID] = None) -> tuple[str, Dict[str, Any]]:
        tools = RetrievalTools(self._dsn, self._embedding_client)

        created_client = False
        chat_client = self._chat_client
        if chat_client is None:
            chat_client = _build_chat_client()
            created_client = True

        try:
            orchestrator = LLMOrchestrator(client=chat_client, tools=tools)
            result = orchestrator.run(intent)
            if not result.final_answer:
                raise HTTPException(status_code=502, detail="Orchestrator did not produce a response")

            histogram = result.histogram or {"bin_days": DEFAULT_BIN_DAYS, "buckets": [], "total": 0}
            persisted = self._persist_turn(session_id=session_id, user_text=intent, assistant_text=result.final_answer)
            metadata = {
                "cited_turn_ids": result.cited_turn_ids,
                "histogram": histogram,
                "session_id": str(persisted["session_id"]),
                "conversation_id": str(persisted["conversation_id"]),
                "user_message_id": str(persisted["user_message_id"]),
                "assistant_message_id": str(persisted["assistant_message_id"]),
            }
            return result.final_answer, metadata
        finally:
            if created_client:
                chat_client.close()

    def _persist_turn(
        self,
        *,
        session_id: Optional[UUID],
        user_text: str,
        assistant_text: str,
    ) -> Dict[str, Any]:
        user_clean = (user_text or "").strip()
        if not user_clean:
            raise HTTPException(status_code=400, detail="Cannot persist empty user message")
        assistant_clean = (assistant_text or "").strip()
        if not assistant_clean:
            raise HTTPException(status_code=502, detail="Assistant response was empty")

        with psycopg.connect(self._dsn) as conn:
            try:
                target_session_id = session_id
                if target_session_id is None:
                    target_session_id, _ = session_store.create_session(conn, title=None)
                result = session_store.append_turn(
                    conn,
                    target_session_id,
                    user_content=user_clean,
                    assistant_content=assistant_clean,
                )
                conn.commit()
            except session_store.SessionNotFound as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        return result


def stream_answer(text: str, metadata: Dict[str, Any]):
    """Yield OpenAI-style streaming chunks for the final answer plus metadata."""
    chunk_id = f"chatcmpl-{uuid4()}"
    lines = text.split(" ")
    for idx, token in enumerate(lines):
        delta = {"content": (token + (" " if idx < len(lines) - 1 else ""))}
        payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        yield "data: " + json.dumps(payload) + "\n\n"

    meta_payload = {
        "id": f"meta-{uuid4()}",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"metadata": metadata}, "finish_reason": "metadata"}],
    }
    yield "data: " + json.dumps(meta_payload) + "\n\n"
    yield "data: [DONE]\n\n"


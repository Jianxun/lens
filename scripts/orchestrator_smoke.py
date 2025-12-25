"""
Smoke test for the LLM orchestrator using peek/turn tools (no streaming).

Usage:
  # ensure .venv active and .env sourced (SUPER_MIND_API_KEY + OPENAI_API_KEY)
  python scripts/orchestrator_smoke.py "your query here"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

# Ensure repo root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import dsn_from_env, EMBEDDING_BASE_URL, EMBEDDING_API_KEY_ENV
from backend.services.agent import (
    AgentService,
    ORCHESTRATOR_API_KEY_ENV,
    ORCHESTRATOR_BASE_URL_ENV,
    ORCHESTRATOR_DEFAULT_BASE_URL,
)


def build_embedding_client() -> httpx.Client:
    key = os.environ.get(EMBEDDING_API_KEY_ENV)
    if not key:
        raise SystemExit(f"{EMBEDDING_API_KEY_ENV} is required")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return httpx.Client(base_url=EMBEDDING_BASE_URL, headers=headers, timeout=30.0)


def build_chat_client() -> httpx.Client:
    base = os.environ.get(ORCHESTRATOR_BASE_URL_ENV, ORCHESTRATOR_DEFAULT_BASE_URL)
    key = os.environ.get(ORCHESTRATOR_API_KEY_ENV)
    if not key:
        raise SystemExit(f"{ORCHESTRATOR_API_KEY_ENV} is required for orchestrator runs")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return httpx.Client(base_url=base, headers=headers, timeout=60.0)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/orchestrator_smoke.py \"query\"")
    query = sys.argv[1].strip()
    if not query:
        raise SystemExit("query must be non-empty")

    dsn = dsn_from_env()
    emb_client = build_embedding_client()
    chat_client = build_chat_client()

    svc = AgentService(dsn, embedding_client=emb_client, chat_client=chat_client)
    try:
        answer, meta = svc.run(query)
        print("status: ok")
        print("answer (prefix):", answer[:200])
        print("cited_turn_ids:", meta.get("cited_turn_ids"))
        print("histogram buckets:", len(meta.get("histogram", {}).get("buckets", [])))
    finally:
        emb_client.close()
        chat_client.close()


if __name__ == "__main__":
    main()


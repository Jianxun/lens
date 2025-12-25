# Handoff

## Current state
- T-004 still in progress: initial Postgres schema added (`migrations/0001_init.sql`), docker-compose for local Postgres + pgvector, README with setup/verify steps, pgweb UI, codebase_map updated. DB running on port 5433 (docker compose).
- T-005 done: ingestion pipeline implemented (`backend/ingest/pipeline.py`, `backend/__init__.py`), CLI `scripts/ingest_jsonl.py` (adds repo root to PYTHONPATH), requirements at `backend/ingest/requirements.txt`, README ingestion section. Pipeline scrubs null bytes, deterministic DFS ordering, content/summary truncation (32k/4k), role filter user/assistant, skips empty content_text, raw + stats persisted. Codebase map updated.

## Last verified
- 2025-12-25: Dropped tables, reapplied `migrations/0001_init.sql`, reran ingest on `data/chatgpt_dump/2025-12-23/conversations.jsonl` via `POSTGRES_PORT=5433 .venv/bin/python scripts/ingest_jsonl.py data/chatgpt_dump/2025-12-23/conversations.jsonl` → succeeded with stats `{'conversations_written': 2059, 'conversations_skipped': 0, 'messages_written': 27538, 'messages_role_skipped': 15020, 'messages_content_empty_skipped': 12827, 'messages_truncated': 25, 'turn_summary_truncated': 0, 'lines_processed': 2059}`.
- `docker compose exec -T db psql -U lens -d lens -c "\\dt"` shows expected tables. `select status, stats from ingest_runs order by started_at desc limit 1` -> latest row `status=succeeded` with stats above.
- Spot-check: `select id, conversation_id, idx_in_conv, role, create_time from messages order by create_time asc limit 5` shows sequential idx_in_conv and timestamptz.

## Next steps (1–3)
- Keep compose running or document stopping; if rerunning on default port, ensure 5432 is free or set POSTGRES_PORT. pgweb available on PGWEB_PORT (default 8081) via `docker compose up -d db pgweb`.
- If future embedding model <=2000 dims, add vector index (ivfflat/hnsw) via new migration.
- Proceed to T-006 retrieval API using ingested data; rerun ingest via `scripts/ingest_jsonl.py` if dataset changes (defaults to POSTGRES_* envs).

## Risks / unknowns
- No vector index for 3072-dim embeddings; retrieval perf will rely on seq scan unless model/dim change or alternative index is added.
- Ingest stats show 25 content truncations; null bytes are scrubbed from raw payloads before storage; empty content messages are skipped and counted.



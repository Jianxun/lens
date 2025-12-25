# Handoff

## Current state
- T-004 still in progress: initial Postgres schema added (`migrations/0001_init.sql`), docker-compose for local Postgres + pgvector, README with setup/verify steps, pgweb UI, codebase_map updated. DB running on port 5432 (docker compose).
- T-005 done: ingestion pipeline implemented (`backend/ingest/pipeline.py`, `backend/__init__.py`), CLI `scripts/ingest_jsonl.py` (adds repo root to PYTHONPATH), requirements at `backend/ingest/requirements.txt`, README ingestion section. Pipeline scrubs null bytes, deterministic DFS ordering, content/summary truncation (32k/4k), role filter user/assistant, skips empty content_text, raw + stats persisted. Codebase map updated.
- T-010 done: embedding pipeline added (`backend/embeddings/pipeline.py`, `backend/embeddings/requirements.txt`, `scripts/embed_messages.py`) using student portal embeddings (provider `supermind`, model `text-embedding-3-large`). Includes SHA256 content_hash skip, summary preference, truncation guard (32k), batching/retries, upsert into `message_embeddings`. README updated with embedding instructions.

## Last verified
- 2025-12-25: Dropped tables, reapplied `migrations/0001_init.sql`, reran ingest on `data/chatgpt_dump/2025-12-23/conversations.jsonl` via `POSTGRES_PORT=5433 .venv/bin/python scripts/ingest_jsonl.py data/chatgpt_dump/2025-12-23/conversations.jsonl` → succeeded with stats `{'conversations_written': 2059, 'conversations_skipped': 0, 'messages_written': 27538, 'messages_role_skipped': 15020, 'messages_content_empty_skipped': 12827, 'messages_truncated': 25, 'turn_summary_truncated': 0, 'lines_processed': 2059}`.
- `docker compose exec -T db psql -U lens -d lens -c "\\dt"` shows expected tables. `select status, stats from ingest_runs order by started_at desc limit 1` -> latest row `status=succeeded` with stats above.
- Spot-check: `select id, conversation_id, idx_in_conv, role, create_time from messages order by create_time asc limit 5` shows sequential idx_in_conv and timestamptz.
- 2025-12-25: Student portal embedding smoke test (text-embedding-3-large) returned HTTP 200, embedding length 3072. Sample job `POSTGRES_PORT=5433 .venv/bin/python scripts/embed_messages.py --batch-size 8 --limit 20` (env from `.env`) → `{'embedded': 8, 'skipped_existing_hash': 12, 'batches': 1}`. Re-run on port 5432 with force + paging `POSTGRES_PORT=5432 .venv/bin/python scripts/embed_messages.py --batch-size 8 --limit 100 --force` → `message_embeddings` rows=100 for provider/model `supermind`/`text-embedding-3-large`.

## Next steps (1–3)
- Keep compose running or document stopping; DB now mapped to host 5432. pgweb available on PGWEB_PORT (default 8081) via `docker compose up -d db pgweb`.
- Run embedding job after future ingests (no limit) with `SUPER_MIND_API_KEY` exported: `POSTGRES_PORT=5432 .venv/bin/python scripts/embed_messages.py --force` to refresh hashes if needed.
- If future embedding model <=2000 dims, add vector index (ivfflat/hnsw) via new migration. Proceed to T-006 retrieval API using ingested data.

## Risks / unknowns
- No vector index for 3072-dim embeddings; retrieval perf will rely on seq scan unless model/dim change or alternative index is added.
- Ingest stats show 25 content truncations; null bytes are scrubbed from raw payloads before storage; empty content messages are skipped and counted.
- Embedding pipeline depends on student portal availability and `SUPER_MIND_API_KEY`; retries are basic exponential, no circuit breaker.



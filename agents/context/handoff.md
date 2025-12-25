# Handoff

## Current state
- T-004 in progress: initial Postgres schema added (`migrations/0001_init.sql`), docker-compose for local Postgres + pgvector, README with setup/verify steps, pgweb UI, codebase_map updated.
- Migration applied successfully to local container (port 5433); tables present: conversations, messages, message_embeddings, sessions, session_messages, ingest_runs. Messages enforce role check, idx uniqueness, length guards; embeddings use vector(3072) with dim=3072; no vector index due to pgvector 2000-dim index limit.

## Last verified
- 2025-12-25: `cat migrations/0001_init.sql | POSTGRES_PORT=5433 docker compose exec -T db psql -U lens -d lens` → COMMIT. `\\dt` shows expected tables. `\\d messages` / `\\d message_embeddings` match constraints described.

## Next steps (1–3)
- Keep compose running or document stopping; if rerunning on default port, ensure 5432 is free or set POSTGRES_PORT. pgweb available on PGWEB_PORT (default 8081) via `docker compose up -d db pgweb`.
- If future embedding model <=2000 dims, add vector index (ivfflat/hnsw) via new migration.
- Proceed to subsequent tasks (ingest, API) using this schema.

## Risks / unknowns
- No vector index for 3072-dim embeddings; retrieval perf will rely on seq scan unless model/dim change or alternative index is added.



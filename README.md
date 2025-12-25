# Lens — Database Setup

Local Postgres (with pgvector) runs via Docker Compose and migrations live under `migrations/`.

## Prerequisites
- Docker + Docker Compose
- `psql` client (installed locally)

## Quick start
```bash
# Start Postgres (defaults: user=lens, password=lens, db=lens, port=5432)
# If 5432 is busy locally, override with POSTGRES_PORT=5433 (or another free port)
POSTGRES_PORT=5433 docker compose up -d db

# Apply initial schema (use same port as above)
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-lens}" -f migrations/0001_init.sql
```

If you prefer running `psql` inside the container:
```bash
cat migrations/0001_init.sql | POSTGRES_PORT=${POSTGRES_PORT:-5432} docker compose exec -T db psql -U ${POSTGRES_USER:-lens} -d ${POSTGRES_DB:-lens}
```

## Verify
```bash
# List tables
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-lens}" -c "\\dt"

# Spot-check schema (examples)
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-lens}" -c "\\d messages"
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-lens}" -c "\\d message_embeddings"
```

Expected tables after `migrations/0001_init.sql`: `conversations`, `messages`, `message_embeddings`, `sessions`, `session_messages`, `ingest_runs`.

## Ingestion (JSONL → Postgres)
- Install deps: `python3 -m venv .venv && .venv/bin/pip install -r backend/ingest/requirements.txt`
- Start Postgres (see above), then run ingest (defaults to `POSTGRES_*` env vars):
  ```bash
  POSTGRES_PORT=${POSTGRES_PORT:-5433} \
  .venv/bin/python scripts/ingest_jsonl.py data/chatgpt_dump/2025-12-23/conversations.jsonl
  ```
- Verify run + stats:
  ```bash
  psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-lens}" \
    -c "select status, stats from ingest_runs order by started_at desc limit 1"
  psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-lens}" \
    -c "select id, conversation_id, idx_in_conv, role, create_time from messages order by create_time asc limit 5"
  ```

## Notes & constraints
- Extensions enabled: `pgcrypto`, `pg_trgm`, `vector`.
- Roles enforced on `messages.role` (`user` | `assistant`); `idx_in_conv` unique per conversation.
- Length guards: `messages.content_text <= 32k` chars; `messages.turn_summary <= 4k` chars.
- Embeddings unique per `(user_message_id, provider, model)` with UUID PK and `vector_dims(vector) = dim` (column is `vector(3072)`; adjust via migration if the embedding model changes). No vector index included because pgvector indexes cap at 2000 dims; add an index if you switch to a <=2000-dim model.
- Session ordering via `session_messages.idx` with uniqueness per session.

## Web DB UI (pgweb)
- Start alongside Postgres (override ports if needed):  
  `POSTGRES_PORT=5433 PGWEB_PORT=8081 docker compose up -d db pgweb`
- Open: http://localhost:${PGWEB_PORT:-8081}
- Connect uses the internal URL (preset): `postgres://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@db:5432/${POSTGRES_DB:-lens}?sslmode=disable`
- If you change Postgres creds/DB name, restart pgweb so it picks up the new env.

## Stopping / resetting
```bash
docker compose down          # stop container
docker compose down -v       # stop and drop data volume (destructive)
```


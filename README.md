# Lens — Local Development

Lens ingests ChatGPT-style exports, stores them in Postgres + pgvector, computes embeddings, and exposes a FastAPI backend with a Vite/React frontend for exploration.

## Quick start (full stack)
1. **Database**  
   `POSTGRES_PORT=5433 docker compose up -d db`  
   `psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-lens}" -f migrations/0001_init.sql`
2. **Backend API**  
   `python3 -m venv .venv`  
   `.venv/bin/pip install -r backend/requirements.txt`  
   `.venv/bin/uvicorn backend.main:app`
3. **Frontend**  
   `cd frontend && npm install`  
   `npm run dev` and open http://localhost:5173

## Prerequisites
- Docker + Docker Compose (for Postgres/pgweb)
- Local `psql` client for running migrations/queries
- Python 3.11+ and `pip` (backend API, ingestion, embeddings)
- Node.js 20+ with `npm` (frontend)

## Database (Postgres + pgvector)

### Start & migrate
```bash
# Start Postgres (defaults: user=lens, password=lens, db=lens, port=5432)
# Override with POSTGRES_PORT when 5432 is busy.
POSTGRES_PORT=5433 docker compose up -d db

# Apply initial schema (use the same port)
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-lens}" -f migrations/0001_init.sql
```

Run migrations inside the container if you prefer:
```bash
cat migrations/0001_init.sql | POSTGRES_PORT=${POSTGRES_PORT:-5432} docker compose exec -T db psql -U ${POSTGRES_USER:-lens} -d ${POSTGRES_DB:-lens}
```

### Verify schema
```bash
# List tables
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-lens}" -c "\\dt"

# Spot-check schema (examples)
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-lens}" -c "\\d messages"
psql "postgresql://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@localhost:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-lens}" -c "\\d message_embeddings"
```

Expected tables after `migrations/0001_init.sql`: `conversations`, `messages`, `message_embeddings`, `sessions`, `session_messages`, `ingest_runs`.

### Web DB UI (pgweb)
- Start alongside Postgres (override ports as needed):  
  `POSTGRES_PORT=5433 PGWEB_PORT=8081 docker compose up -d db pgweb`
- Open: http://localhost:${PGWEB_PORT:-8081}
- Connection string (pre-configured in Docker env):  
  `postgres://${POSTGRES_USER:-lens}:${POSTGRES_PASSWORD:-lens}@db:5432/${POSTGRES_DB:-lens}?sslmode=disable`
- Restart pgweb after changing Postgres credentials/db name so env vars reload.

### Stopping / resetting
```bash
docker compose down          # stop the containers
docker compose down -v       # stop and drop the data volume (destructive)
```

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

## Embeddings job (student portal)
- Install deps: `python3 -m venv .venv && .venv/bin/pip install -r backend/embeddings/requirements.txt`
- Export `SUPER_MIND_API_KEY` (student portal token). Endpoint used: `POST https://space.ai-builders.com/backend/v1/embeddings` with model `text-embedding-3-large` (provider label `supermind`).
- Run embedding job (defaults to `POSTGRES_*` env vars):
  ```bash
  SUPER_MIND_API_KEY=... \
  POSTGRES_PORT=${POSTGRES_PORT:-5433} \
  .venv/bin/python scripts/embed_messages.py --batch-size 16 --limit 100
  ```
- Use `--force` to recompute even when `content_hash` matches an existing row.
- Output includes `embedded`, `skipped_existing_hash`, and `batches`. Upserts into `message_embeddings` with unique `(user_message_id, provider, model)` using SHA256 `content_hash` to skip unchanged turns.

## Backend API (FastAPI + Uvicorn)
- Create a virtualenv once: `python3 -m venv .venv`
- Install deps: `.venv/bin/pip install -r backend/requirements.txt`
- Environment:
  - `POSTGRES_*` (host/user/password/port/db) should match the database you started earlier.
  - Optional `SUPER_MIND_API_KEY` unlocks live embedding calls; without it, endpoints that need embeddings will skip remote calls.
  - Values placed in the repo-level `.env` file are auto-loaded on startup (existing shell env vars still win).
- Start the API:
  ```bash
  POSTGRES_PORT=${POSTGRES_PORT:-5433} \
  SUPER_MIND_API_KEY=... \  # optional
  .venv/bin/uvicorn backend.main:app --reload --port 8000
  ```
- Verify:
  - Docs/UI: http://localhost:8000/docs
  - Smoke queries:
    ```bash
    curl "http://localhost:8000/retrieval/peek?query=hello&bin_days=1&top_k=100&top_n_snippets=10"
    curl "http://localhost:8000/sessions?include_archived=false"
    ```
- `/retrieval/peek` uses fixed model `text-embedding-3-large`, computes histogram buckets in whole days over the `top_k` matches, and returns `top_n_snippets` snippets. `/sessions` + `/chat` power the frontend UI.

## Frontend (Vite + React 19)
- Install deps: `cd frontend && npm install`
- Dev server:
  ```bash
  cd frontend
  # Backend defaults to http://localhost:8000; override if needed.
  VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
  ```
  Open http://localhost:5173. Requests to `/api/*` proxy to `VITE_API_PROXY_TARGET`, so make sure the backend is running first.
- Environment knobs:
  - `VITE_API_PROXY_TARGET` (dev only) controls where `/api` requests are forwarded.
  - `VITE_API_BASE` (build-time) overrides the fetch base URL; default `/api` works when the frontend is reverse-proxied with the backend.
- Production build + preview:
  ```bash
  cd frontend
  VITE_API_BASE=https://your-api.example.com npm run build
  npm run preview   # serves the dist bundle for smoke testing
  ```

## Notes & constraints
- Extensions enabled: `pgcrypto`, `pg_trgm`, `vector`.
- Roles enforced on `messages.role` (`user` | `assistant`); `idx_in_conv` unique per conversation.
- Length guards: `messages.content_text <= 32k` chars; `messages.turn_summary <= 4k` chars.
- Embeddings unique per `(user_message_id, provider, model)` with UUID PK and `vector_dims(vector) = dim` (column is `vector(3072)`; adjust via migration if the embedding model changes). No vector index included because pgvector indexes cap at 2000 dims; add an index if you switch to a <=2000-dim model.
- Session ordering via `session_messages.idx` with uniqueness per session.

# Codebase Map

## Directories
- `agents/roles`: role briefs for Architect, Executor, and Explorer.
- `agents/context`: shared working memory (lessons, contract, tasks, handoff, tasks_archived, codebase_map).
- `agents/adr`: architecture decision records.
- `agents/scratchpads`: per-task scratchpads (T-004..T-010).
- `migrations`: SQL migrations (initial schema planned in 0001_init.sql).
- `backend/`:
  - `ingest/`: JSONL → Postgres pipeline (pipeline, helpers).
  - `embeddings/`: embedding jobs for turn-level vectors.
  - `api/`: FastAPI endpoints (`retrieval.py` for `/retrieval/peek` and `/retrieval/turn/{id}`).
  - `main.py`: FastAPI app wiring, DSN/env setup, embedding client bootstrap.
  - `services/`: agent orchestration, retrieval wiring (planned).
  - `models/`: DB models / queries (planned).
- `scripts/`: helper CLIs (`split_conversations_jsonl.py`, ingest helpers, embedding runners).
- `frontend/`: Vite + React TS chat UI with session list, streaming chat, and histogram panel. Key files:
  - `src/App.tsx`: main UI (sessions list, chat view, histogram toggle, composer).
  - `src/api.ts`: API helpers for sessions and streaming `/chat`.
  - `src/types.ts`: shared frontend types.
  - `vite.config.ts`: dev proxy `/api` → FastAPI (default http://localhost:8000).
- `data/chatgpt_dump/`: sample ChatGPT exports (JSON/JSONL) for ingestion tests.
- `docker-compose.yml`: local Postgres + pgvector container definition.

## Notes
- Embedding model is fixed to `text-embedding-3-large`; provider/model not exposed to clients.
- Retrieval under `/retrieval/`; chat under `/chat`; sessions under `/sessions`.



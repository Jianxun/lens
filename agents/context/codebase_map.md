# Codebase Map

## Directories
- `agents/roles`: role briefs for Architect, Executor, and Explorer.
- `agents/context`: shared working memory (lessons, contract, tasks, handoff, tasks_archived, codebase_map).
- `migrations`: SQL migrations (initial schema in 0001_init.sql).
- `backend/`: application code; `ingest/` holds the JSONL→Postgres pipeline (`pipeline.py`, `requirements.txt`).
- `scripts/`: helper CLIs (`split_conversations_jsonl.py`, `ingest_jsonl.py`).
- `data/chatgpt_dump/`: sample ChatGPT exports (JSON/JSONL) for ingestion tests.
- `docker-compose.yml`: local Postgres + pgvector container definition.

## Notes
- No product code exists yet; expand this map as new components are added or moved.



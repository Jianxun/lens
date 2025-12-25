# Tasks

## Active OKR(s)
- None yet; project bootstrap.

## Current Sprint
- T-004 — Database schema & migrations  
  - Status: In Progress  
  - Owner: Executor  
  - DoD:  
    - Create Postgres schema: conversations, messages, message_embeddings (UUID PK), sessions, session_messages, ingest_runs.  
    - Enforce roles (user/assistant), idx ordering, length truncation rules, and uniqueness constraints per ADRs.  
    - Provide initial migration SQL and a short README for setup.  
  - Verify:  
    - `psql -f migrations/0001_init.sql` succeeds on fresh DB  
    - `psql -c "\\dt"` shows expected tables  
  - Files allowed: `migrations/`, `README.md` (DB setup notes).

- T-005 — Ingestion pipeline  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Implement JSONL ingest into Postgres with deterministic idx, length truncation + warning, user/assistant filter, raw retention, and ingest_runs logging.  
    - CLI entrypoint to ingest a dump path.  
  - Verify:  
    - Ingest sample JSONL completes; ingest_runs row status=succeeded; stats reflect counts/truncations.  
    - Spot-check messages persisted with idx and timestamps.  
  - Files allowed: `backend/ingest/` (new), `scripts/` (helpers), `README.md` (ingest usage).

- T-006 — Retrieval API  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Implement FastAPI endpoints `/retrieval/peek` (top_k default 100, UTC bins, top_n_snippets) and `/retrieval/turn/{id}`.  
    - Fixed embedding model `text-embedding-3-large`; no provider/model inputs.  
    - Return histogram, matches, and hydrated turns per ADR-0004.  
  - Verify:  
    - `GET /retrieval/peek` returns histogram + snippets on seeded data.  
    - `GET /retrieval/turn/{id}` returns full turn content for a known id.  
  - Files allowed: `backend/api/retrieval.py`, `backend/main.py` (routing), `backend/models/` as needed.

- T-007 — Chat agent orchestration  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Implement streaming `/chat` endpoint using student portal `/v1/chat/completions`.  
    - Tool wiring to `/retrieval/peek`/`turn`, multi-pass with histograms, 50k token cap, cited turn_ids returned in response metadata.  
    - Enforce fixed embedding model, cap hydrated turns, truncate long texts.  
  - Verify:  
    - Live call returns streamed tokens; response metadata includes cited turn_ids and histogram.  
    - Logs show tool calls and capped hydration.  
  - Files allowed: `backend/api/chat.py`, `backend/main.py`, `backend/services/agent.py`.

- T-008 — Sessions API & persistence  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Implement `/sessions` list/get/create/patch/delete (soft archive) and link messages to sessions with linear ordering.  
    - Ensure only finalized messages are stored; no superseded drafts.  
  - Verify:  
    - CRUD works in manual tests; session_messages reflect message order; archived sessions hidden from default list.  
  - Files allowed: `backend/api/sessions.py`, `backend/models/`, `backend/main.py`.

- T-009 — Frontend MVP  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Implement chat UI (markdown assistant, user bubbles), session list panel, streaming `/chat` consumption, collapsible histogram display with cited turn_ids.  
    - Send full history by default to `/chat`.  
  - Verify:  
    - UI shows sessions, loads history, streams replies; histogram panel renders when provided.  
  - Files allowed: `frontend/` (Vite/React or similar), minimal config, no heavy theming.

## Backlog
- T-003 — Define initial application skeleton once scope is known  
  - Status: Backlog  
  - Owner: Architect  
  - DoD:  
    - Decide directories/namespaces for first code artifacts.  
    - Add entries to codebase_map and verification steps.  
    - Draft an ADR if multiple architecture options emerge.  
  - Verify:  
    - `test -f agents/context/codebase_map.md`  
  - Links: TBD

## Done
- T-001 — Bootstrap context scaffolding  
  - Status: Done (2025-12-24)  
  - Owner: Architect  
  - DoD:  
    - Create contract, tasks, handoff, tasks_archived, and codebase_map with required sections.  
    - Record current state and next steps in handoff.  
    - Add tasks board entry and verify files exist.  
  - Verify:  
    - `ls agents/context`  
  - Links: `agents/context/contract.md`, `agents/context/handoff.md`



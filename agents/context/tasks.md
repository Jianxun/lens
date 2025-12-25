# Tasks

## Active OKR(s)
- None yet; project bootstrap.

## Current Sprint
- T-011 — Embedding pipeline stall beyond 3k rows  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Reproduce the stall around 3k embeddings; capture batch offsets, DB row counts, and API responses to isolate the failure mode.  
    - Fix the root cause (e.g., resume cursor, constraint conflict, pagination/token limit) so a run progresses past 6k without manual intervention.  
    - Add durable progress logging + retry surface; reruns must be idempotent (no duplicate embeddings for provider/model/user_message_id).  
  - Verify:  
    - `. .venv/bin/activate && set -a && source .env && set +a && POSTGRES_PORT=5432 python scripts/embed_messages.py --batch-size 8 --limit 6000 --force` completes without halt and reports embeddings > 6000.  
    - `docker compose exec -T db psql -U lens -d lens -c "select count(*) from message_embeddings where provider='supermind' and model='text-embedding-3-large';"` shows the expected row growth beyond prior 3k ceiling.  
  - Files allowed: `backend/embeddings/pipeline.py`, `scripts/embed_messages.py`, `backend/main.py` (env wiring).  
  - Links: TBD  

- T-012 — Orchestrator tool trace UX (histogram + peek query strings)  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Emit structured trace of every tool call (peek/turn) with inputs and timing; persist per-chat run for frontend consumption.  
    - Frontend: add right-side collapsible panel showing all peek traces (histogram + query string) without overlapping main chat; provide histogram plot + trace list.  
    - Ensure traces load lazily/toggle without blocking chat; keep layout responsive.  
  - Verify:  
    - `python scripts/orchestrator_smoke.py "test trace"` logs tool-call traces with queries and histogram payloads.  
    - `cd frontend && npm run dev` → manual chat shows collapsible right panel with histogram + peek query list; toggle hides/shows without shifting chat input.  
  - Files allowed: `backend/services/agent.py`, `backend/api/chat.py`, `frontend/src/App.tsx`, `frontend/src/components/*`, `frontend/src/api.ts`.  
  - Links: TBD  

- T-013 — Streaming UI not updating during SSE  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Identify why UI stops updating while backend streams events (SSE parsing/backpressure/state updates).  
    - Fix frontend stream handling so tokens render incrementally and final chunk commits metadata.  
    - Add guardrails (abort handling, error surface) and a lightweight testable repro.  
  - Verify:  
    - Backend running with `.venv` + `.env`; `cd frontend && npm run dev` streaming chat shows incremental token updates in the UI.  
    - Optionally validate via `python scripts/orchestrator_smoke.py --stream "hello"` to confirm event cadence is consumed client-side.  
  - Files allowed: `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/components/*`, `backend/api/chat.py` (if needed for streaming framing).  
  - Links: TBD  

- T-014 — System prompt tuning (hydration + style)  
  - Status: Ready  
  - Owner: Executor  
  - DoD:  
    - Adjust orchestrator system prompt to allow more turn candidates to hydrate while respecting cap limits.  
    - Reduce bullet usage; prefer concise sentences with citation-style `[n]` markers over dated bullet callouts.  
    - Ensure prompt changes are reflected in tests/smokes; document limits in code comments.  
  - Verify:  
    - `python scripts/orchestrator_smoke.py "summarize recent progress"` shows updated style (fewer bullets, citations) and higher hydrated turn cap applied.  
    - If applicable, unit/prompt tests updated to match new prompt text.  
  - Files allowed: `backend/services/agent.py`, `backend/api/chat.py`, `agents/adr/` (if new decision warranted).  
  - Links: TBD  

- T-004 — Database schema & migrations  
  - Status: Done (2025-12-25)  
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
  - Status: Done (2025-12-25)  
  - Owner: Executor  
  - DoD:  
    - Implement JSONL ingest into Postgres with deterministic idx, length truncation + warning, user/assistant filter, raw retention, and ingest_runs logging.  
    - CLI entrypoint to ingest a dump path.  
  - Verify:  
    - Ingest sample JSONL completes; ingest_runs row status=succeeded; stats reflect counts/truncations.  
    - Spot-check messages persisted with idx and timestamps.  
  - Files allowed: `backend/ingest/` (new), `scripts/` (helpers), `README.md` (ingest usage).
  - Links: `agents/scratchpads/T-005.md`

- T-006 — Retrieval API  
  - Status: Done (2025-12-25)  
  - Owner: Executor  
  - DoD:  
    - Implement FastAPI endpoints `/retrieval/peek` (top_k default 100, UTC bins, top_n_snippets) and `/retrieval/turn/{id}`.  
    - Fixed embedding model `text-embedding-3-large`; no provider/model inputs.  
    - Return histogram, matches, and hydrated turns per ADR-0004.  
  - Verify:  
    - `GET /retrieval/peek` returns histogram + snippets on seeded data.  
    - `GET /retrieval/turn/{id}` returns full turn content for a known id.  
  - Files allowed: `backend/api/retrieval.py`, `backend/main.py` (routing), `backend/models/` as needed.
  - Links: `agents/scratchpads/T-006.md`

- T-007 — Chat agent orchestration  
  - Status: Done (2025-12-25)  
  - Owner: Executor  
  - DoD:  
    - Implement streaming `/chat` endpoint using student portal `/v1/chat/completions`.  
    - Tool wiring to `/retrieval/peek`/`turn`, multi-pass with histograms, 50k token cap, cited turn_ids returned in response metadata.  
    - Enforce fixed embedding model, cap hydrated turns, truncate long texts.  
  - Verify:  
    - Live call returns streamed tokens; response metadata includes cited turn_ids and histogram.  
    - Logs show tool calls and capped hydration.  
  - Files allowed: `backend/api/chat.py`, `backend/main.py`, `backend/services/agent.py`.  
  - Links: `agents/scratchpads/T-007.md`

- T-008 — Sessions API & persistence  
  - Status: Done (2025-12-25)  
  - Owner: Executor  
  - DoD:  
    - Implement `/sessions` list/get/create/patch/delete (soft archive) and link messages to sessions with linear ordering.  
    - Ensure only finalized messages are stored; no superseded drafts.  
  - Verify:  
    - CRUD works in manual tests; session_messages reflect message order; archived sessions hidden from default list.  
  - Files allowed: `backend/api/sessions.py`, `backend/models/`, `backend/main.py`.
  - Links: `agents/scratchpads/T-008.md`
  - PR: https://github.com/Jianxun/lens/pull/6

- T-009 — Frontend MVP  
  - Status: Done (2025-12-25)  
  - Owner: Executor  
  - DoD:  
    - Implement chat UI (markdown assistant, user bubbles), session list panel, streaming `/chat` consumption, collapsible histogram display with cited turn_ids.  
    - Send full history by default to `/chat`.  
  - Verify:  
    - UI shows sessions, loads history, streams replies; histogram panel renders when provided.  
  - Files allowed: `frontend/` (Vite/React or similar), minimal config, no heavy theming.  
  - Links: `agents/scratchpads/T-009.md`  
  - PR: https://github.com/Jianxun/lens/pull/7

- T-010 — Embedding creation pipeline  
  - Status: Done (2025-12-25)  
  - Owner: Executor  
  - DoD:  
    - Implement embedding job to generate turn-level embeddings (user anchor, assistant linked) using fixed `text-embedding-3-large`.  
    - Respect truncation limits; store `content_used`, `used_turn_summary`, `content_hash`; upsert into `message_embeddings` with unique (user_message_id, provider, model).  
    - CLI/runner to process new messages incrementally; skip already-hashed content.  
  - Verify:  
    - Run on sample data completes; embeddings table populated with expected rows and vectors; duplicates avoided via unique constraint.  
    - Spot-check summary preference: when turn_summary exists, it is used.  
  - Files allowed: `backend/embeddings/` (new), `scripts/` (helper CLI), `README.md` (embedding usage).  
  - Links: `agents/scratchpads/T-010.md`

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



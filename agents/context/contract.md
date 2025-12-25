# Contract

## Project overview
- Lens currently hosts coordination artifacts for multi-agent work. The goal is to keep shared context coherent while the application scope is defined and code is added.

## System boundaries / components
- `agents/context`: canonical working memory (lessons, contract, tasks, handoff, codebase_map, tasks_archived).
- `agents/roles`: authority and responsibilities for Architect, Executor, and Explorer.
- Future application code is not present yet; until added, scope is limited to documentation and planning.

## Interfaces & data contracts
- `agents/context/contract.md` keeps this structure: Project overview; System boundaries/components; Interfaces & data contracts; Invariants; Verification protocol; Decision log.
- `agents/context/tasks.md` tracks tasks with IDs `T-00X`, status, owner, DoD, verify commands, and links; maintains sections Active OKR(s), Current Sprint, Backlog, Done.
- `agents/context/handoff.md` captures current state, last verified status, next steps (1–3), and risks/unknowns; keep it succinct and actionable.
- `agents/context/codebase_map.md` lists directory references and must be updated when files move or new subsystems appear.
- `agents/context/lessons.md` stores user-wide rules; always consult and obey (e.g., obtain current date via `date`).
- ADRs live under `agents/adr/` when needed; reference active ADR IDs in this contract once created.

## Invariants
- Do not edit lessons unless the user explicitly changes a rule.
- Keep contract, tasks, handoff, and codebase_map consistent with the repository’s actual state; update them after merges or completed tasks.
- Prefer minimal, enforceable rules; record non-trivial decisions via ADR entries referenced here.
- Avoid adding project code without updating the map/contract as needed.

## Verification protocol
- `ls agents/context` shows: lessons.md, contract.md, tasks.md, handoff.md, tasks_archived.md, codebase_map.md.
- Manual review confirms each file retains its required sections; no automated tests exist yet.

## Decision log
- 2025-12-24: Initialized context scaffolding with minimal contract/tasks/handoff/codebase_map to bootstrap the repository.
- 2025-12-25 (ADR-0001): Chose PostgreSQL + pgvector with normalized conversations/messages schema, raw JSON retention, and embeddings table.
- 2025-12-25 (ADR-0002): Defined ingestion pipeline from ChatGPT JSON/JSONL to Postgres, keeping only user/assistant messages, stable ordering, and ingest run audit.
- 2025-12-25 (ADR-0003): Defined turn-level embedding strategy anchored on user message IDs with assistant linkage, summary-first text selection, and UUID-keyed embeddings table.
- 2025-12-25 (ADR-0004): Defined retrieval API under `/retrieval/` with `peek` (histogram + top matches) and `turn` hydration by embedding ID.
- 2025-12-25 (ADR-0005): Defined agent orchestration and streaming `/chat` API; fixed embedding model; multi-pass peek/turn tool usage with temporal zooming and capped hydration.
- 2025-12-25 (ADR-0006): Defined sessions model/API (sessions list, history, soft archive/pin, linking messages to sessions).
- 2025-12-25 (ADR-0007): Defined frontend UX (ChatGPT-like layout, markdown assistant bubbles, session list, streaming chat, full-history default).



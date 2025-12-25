# ADR-0006: Sessions model and API
Status: Accepted  
Date: 2025-12-25

## Context
- The frontend shows a list of past sessions (ChatGPT-style left panel).
- Each session corresponds to a conversation_id and its messages.
- `/chat` already streams answers; we need lightweight session CRUD and history retrieval.

## Decision
- Tables:
  - `sessions(id uuid pk default gen_random_uuid(), title text, created_at timestamptz default now(), updated_at timestamptz default now(), pinned bool default false, archived bool default false, metadata jsonb)`.
  - `session_messages(id uuid pk default gen_random_uuid(), session_id uuid fk sessions(id), message_id uuid fk messages(id), idx int, created_at timestamptz default now(), unique(session_id, message_id))`.
    - `idx` stores presentation order; messages table remains canonical; messages belong to exactly one session with strictly linear ordering by creation time.
- APIs (FastAPI):
  - `GET /sessions`: list sessions `{id, title, updated_at, pinned, archived, message_count?}`.
  - `GET /sessions/{id}`: returns session metadata and full message history (ordered by idx or messages.create_time).
  - `POST /sessions`: create a new session; optionally accept `title`.
  - `PATCH /sessions/{id}`: update `title`, `pinned`, `archived`.
  - `DELETE /sessions/{id}`: soft delete (set `archived=true`).
- `/chat` accepts `session_id`; if absent, create a session and return it in the response. Each user/assistant turn inserted into `messages` and linked via `session_messages`.
- Defaults:
  - Full history is sent from frontend to `/chat` by default (no truncation).
  - Backend may cap only if needed later; not part of the default behavior.
  - Only messages that are finally displayed are persisted; if a user edits/resubmits before finalizing, superseded drafts are not stored.

## Consequences
- Sessions are explicit; message provenance remains in `messages`.
- `session_messages` preserves ordering and allows future features (pinning, replay).
- Session list is lightweight to render; renaming/pinning supported via PATCH.

## Alternatives
- No session table: rely solely on conversation_id in messages; harder to manage metadata like title/pin/archive.
- Store history in a JSON blob: simpler but loses relational integrity and reuse of `messages`.


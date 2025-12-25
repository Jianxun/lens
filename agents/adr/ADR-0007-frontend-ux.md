# ADR-0007: Frontend UX for Lens chat
Status: Accepted  
Date: 2025-12-25

## Context
- The UI should mirror a simple ChatGPT experience: left panel sessions, main chat thread, markdown for assistant messages, user bubbles on the right.
- The frontend assembles full conversation history by default when calling `/chat`.
- Streaming responses should render incrementally.

## Decision
- Layout:
  - Left panel: sessions list (title, updated_at, pinned indicator). Click to open a session; new session button.
  - Main pane: chat thread with bubbles; assistant messages rendered as markdown (code blocks supported), user messages as plain text.
  - Composer: textarea with send button; Shift+Enter for newline.
- Data flow:
  - Load sessions via `GET /sessions`; load history via `GET /sessions/{id}`.
  - On send: POST to `/chat` with `session_id` and full history (default untruncated) plus the new user message; stream the assistant reply.
  - Maintain local cache of session metadata; optionally persist minimal session list in localStorage for quick render.
- Streaming:
  - Use fetch streaming/SSE to append tokens to the current assistant bubble; finalize on stream end.
  - Show “thinking” indicator while `/chat` runs.
- Rendering rules:
  - User bubble: align right.
  - Assistant bubble: align left, markdown-rendered; support code blocks and inline links.
  - Hide internal IDs; keep turn_id in message metadata for debugging if needed.
- Results metadata:
  - Display a collapsible panel containing the retrieval histogram returned by `/chat` (for user awareness).
  - The `/chat` response should also include cited turn_ids; keep them available in the UI (can be hidden or shown in the collapsible).
- Error handling:
  - If stream fails, show retry; keep partial assistant text if useful.
  - Allow renaming sessions via `PATCH /sessions/{id}` from UI.
- History:
  - Default: send full session history to `/chat` (no truncation). A future cap can be added but is not default.

## Consequences
- Minimal, familiar UX; small surface area for maintenance.
- Streaming improves responsiveness; full history preserves context fidelity.
- Sessions panel enables quick navigation across past chats.

## Alternatives
- Paginated history send: reduces payload but risks context loss; rejected for default.
- More complex UI (threading, citations): can be added later; start simple.


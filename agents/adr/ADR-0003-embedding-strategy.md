# ADR-0003: Embedding strategy and schema
Status: Accepted  
Date: 2025-12-25

## Context
- Retrieval will use semantic search over turns. We want stable IDs, auditability, and flexibility to experiment with embedding providers/models.
- `turn_summary` is often better than raw assistant text; when absent we fall back to the assistant message.
- Summaries live in metadata on the user message, so anchoring on the user message keeps provenance aligned.

## Decision
- Embedding unit: one vector per turn (user + assistant reply). Build text as:
  - `User: <user content>\nAssistant: <turn_summary if present else assistant content>`.
  - Skip if assistant or user text is missing/empty.
- Anchor on the user message ID; keep the assistant message ID for linkage.
- Table `message_embeddings`:
  - `id uuid pk default gen_random_uuid()`
  - `user_message_id uuid fk messages(id) not null`
  - `assistant_message_id uuid fk messages(id)`
  - `provider` text
  - `model` text
  - `dim` int
  - `content_used` text            -- exact text embedded (summary or verbatim)
  - `content_hash` text            -- optional, to skip recompute
  - `used_turn_summary` bool       -- true if summary was used
  - `vector` vector
  - `created_at timestamptz default now()`
- Constraints / indexes:
  - Unique on `(user_message_id, provider, model)` to prevent duplicates.
  - Btree on `assistant_message_id` for joins.
  - Vector index on `vector`.
  - Optional btree on `(provider, model)`.
- Embedding pipeline:
  1) For each assistant message, find its parent user message; if none, skip.
  2) Build content as above, choosing `turn_summary` if present.
  3) Upsert into `message_embeddings` using the unique constraint; store `used_turn_summary`, `content_used`, and hashes when available.
- Retrieval: search over `message_embeddings.vector`; join to messages to display user + assistant (or summary). Hybrid FTS remains available on `messages.content_text` and `messages.turn_summary`.

## Consequences
- User-anchored embeddings align with where summaries reside; assistant linkage is preserved for display.
- The unique constraint ensures deterministic refresh per provider/model.
- Storing `content_used` enables audit and change detection; `content_hash` can reduce recompute.
- Skipping empty turns prevents noisy vectors.

## Alternatives
- Anchor on assistant ID: makes sense if summaries were stored on assistants, but conflicts with current metadata location.
- Embed assistant-only or user-only: loses turn context and typically weakens retrieval quality.
- Store embeddings without UUID PK: workable, but a UUID PK simplifies references and tooling.


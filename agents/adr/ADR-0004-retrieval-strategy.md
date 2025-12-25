# ADR-0004: Retrieval strategy and API
Status: Accepted  
Date: 2025-12-25

## Context
- Lens is an introspective instrument over ChatGPT dumps; time-aware exploration (histograms) is first-class.
- We already decided: Postgres + pgvector (ADR-0001), ingestion (ADR-0002), and turn-level embeddings anchored on user messages (ADR-0003).
- We need simple, low-latency endpoints to probe the vector space and to hydrate selected turns.

## Decision
- Namespace retrieval under `/retrieval/`.

Endpoints
- `GET /retrieval/peek`
  - Input: query text; optional `top_k` (default 100), time range, bin size, conversation_id filter, `top_n_snippets` (default 10).
  - Behavior:
    - Embed query using a fixed model `text-embedding-3-large` (provider/model are not exposed to clients).
    - Vector search `message_embeddings.vector` (joins to `messages` for timestamps and snippets).
    - Return:
      - `histogram`: time-bucketed counts over the matched set (computed over all `top_k`).
      - `matches`: top `top_n_snippets` turns with `{turn_id (embedding id), score, user_message_id, assistant_message_id, user_snippet, assistant_snippet (summary if used), create_time}`.
    - Defaults favor broad coverage (top_k=100) for better histograms; snippets remain small for latency.
    - Time binning uses UTC and a fixed origin (epoch) to avoid bin drift.

- `GET /retrieval/turn/{turn_id}`
  - Input: `turn_id` (embedding/message_embeddings.id).
  - Behavior:
    - Fetch `message_embeddings` by id.
    - Join `messages` to return full user + assistant content; if `used_turn_summary` is true, surface summary for assistant-side display; otherwise assistant text.
    - Return metadata: created_at, user_message_id, assistant_message_id, conversation_id, create_time, and fixed embedding model identifier.
  - Purpose: hydrate context when a turn is selected for RAG answers; no vector search here.

Schema notes (reused)
- `message_embeddings` has UUID PK `id`, `user_message_id` anchor, `assistant_message_id`, `provider`, `model`, `dim`, `content_used`, `used_turn_summary`, `vector`, `created_at`, unique `(user_message_id, provider, model)`.
- Snippets in `peek` are derived from `content_used` (assistant/summary) and `messages.content_text` for the user.

Filtering & scoring
- Time filters apply to `messages.create_time` (user anchor).
- Optional conversation_id filter to narrow the search.
- Hybrid prefilter via FTS on `messages.content_text`/`turn_summary` is allowed but not required; keep `peek` low-latency.

Consequences
- Clear separation: `peek` (search + histogram + top matches) vs `turn` (full hydration by ID).
- Temporal profiles are first-class and computed over a broad candidate set (top_k default 100).
- Using the embedding ID as `turn_id` keeps hydration stable and auditable.
- Clients cannot change embedding provider/model; server enforces `text-embedding-3-large`.

Alternatives
- Flatten under `/search`: less explicit; loses the “retrieval” namespace clarity.
- Return full texts in `peek`: heavier and slower; we keep snippets for speed and use `turn` to hydrate.***


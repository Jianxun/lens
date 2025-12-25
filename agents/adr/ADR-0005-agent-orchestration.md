# ADR-0005: Agent orchestration and chat API
Status: Accepted  
Date: 2025-12-25

## Context
- The end-user interface is chat-like. The agent must autonomously orchestrate retrieval across multiple passes (peek → histogram → zoom → turn hydration) before synthesizing an answer.
- Retrieval stack and embeddings are defined (ADR-0001, ADR-0003, ADR-0004). The embedding model is fixed to `text-embedding-3-large`.
- LLM endpoint: student portal OpenAI-compatible chat (`/v1/chat/completions`) with streaming; secrets via `.env`.

## Decision
- Expose a streaming chat API: `POST /chat` (FastAPI).
  - Input: conversation_id (optional), user message(s).
  - Output: streamed assistant response (SSE or chunked).
- Agent tool palette (server-internal, available to the model):
  - `retrieval/peek(query, top_k=100, time_range, bin, conversation_id, top_n_snippets=10)` → histogram over all hits, snippets for top few.
  - `retrieval/turn(turn_id)` → full turn (user + assistant/summary).
- Orchestration guidance (system prompt to the model):
  - You may call `peek` multiple times. Start broad (top_k=100), read histogram, then zoom into interesting time ranges with another `peek`.
  - Hydrate only promising turn_ids via `turn`; prefer summaries (`content_used`) when available.
  - Limit hydrated turns (e.g., ≤20) and truncate long texts before synthesis; enforce a hard context token budget (50k) when constructing the final prompt.
  - The embedding model is fixed; do not change provider/model.
  - Cite turn_ids (and optionally timestamps) used in the final answer; return cited turn_ids in the `/chat` response metadata. If context is weak, say so.
- LLM backend:
  - Base URL: `SUPER_MIND_BASE_URL` (`https://space.ai-builders.com/backend`).
  - Key: `SUPER_MIND_API_KEY` from `.env`.
  - Endpoint: `/v1/chat/completions` with `stream=true`.
- Guardrails:
  - Cap total `turn` hydrations per request; cap max tokens and context length.
  - Do not expose provider/model knobs to clients.
  - Log which turn_ids were used for observability.

## Consequences
- The agent can iteratively explore the semantic/time space, improving recall without extra embedding calls (one embed per user query).
- Streaming UX is preserved; retrieval chatter stays internal, final answer cites sources by turn_id.
- Fixed embedding model simplifies API and avoids client-induced drift.

## Alternatives
- Single-pass retrieval: simpler but weaker recall and poorer temporal navigation.
- Allow client-specified provider/model: increases complexity and risk; rejected to keep consistency and cost control.


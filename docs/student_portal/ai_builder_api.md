## AI Builder Student Portal API (summary)

- Base URL: `https://space.ai-builders.com/backend/v1`
- Auth: `Authorization: Bearer <token>`
- Format: OpenAI-compatible JSON; most endpoints mirror OpenAI shapes.

### Environment
- Load `SUPER_MIND_API_KEY=<portal_token>` and personal `OPENAI_API_KEY=<key>` via `.env` (already gitignored); export both for requests.

### Chat Completions `POST /v1/chat/completions`
- Models: `supermind-agent-v1` (multi-tool orchestrator with web search + Gemini handoff), `deepseek`, `gemini-2.5-pro`, `gpt-5` (temp fixed 1.0; `max_tokens` mapped to `max_completion_tokens`), `grok-4-fast`.
- Supports messages/tools/tool_choice/stream; `debug=true` query returns orchestrator trace; single choice + usage returned.

### Embeddings `POST /v1/embeddings`
- Models: `text-embedding-3-large` (preferred default), `text-embedding-3-small`, `text-embedding-ada-002`.
- Options: `encoding_format` (`float`|`base64`), `dimensions` (for text-embedding-3-*), `user`.

### Audio Transcriptions `POST /v1/audio/transcriptions`
- Form-data: `audio_file` (binary) or `audio_url`; optional `language`.
- Returns transcript, optional segments (timestamps), detected language, confidence, billing info.

### Search `POST /v1/search/`
- Tavily-backed; accepts multiple `keywords`, optional `max_results` (default 6, max 20).
- Returns per-keyword results, optional combined answer, per-keyword errors.

### Usage Summary `GET /v1/usage/summary`
- Lifetime and recent window aggregates: requests, tokens, tool calls, cost ceiling flag.

### Models `GET /v1/models`
- Lists available chat completion models with metadata.

### Deployments
- `GET /v1/deployments`: lists your deployments + limits.
- `POST /v1/deployments`: queue deploy to Koyeb (single process/port; honors `PORT`; 256 MB nano). Payload: `repo_url`, `service_name`, `branch`; optional `port` (default 8000), `env_vars` (not stored; pass each deploy).
- `GET /v1/deployments/{service_name}`: status/details; includes `deployment_prompt_url`, suggested actions.

### Health `GET /health`
- Basic health check.


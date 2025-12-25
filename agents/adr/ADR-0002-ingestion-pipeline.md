# ADR-0002: Ingestion pipeline for ChatGPT dumps
Status: Accepted  
Date: 2025-12-25

## Context
- Source files are ChatGPT exports in JSON array form; we split them to JSONL for streaming ingest.
- We only care about `user` and `assistant` messages; system/tool messages should be skipped but raw preserved for audit.
- Message threading is provided by the `mapping` tree; timestamps are float epochs; IDs are UUIDs.
- `turn_summary` is a key retrieval field for the downstream pipeline.

## Decision
- Ingestion flow:
  1) Input: JSONL where each line is a conversation object (as produced by `scripts/split_conversations_jsonl.py`).
  2) For each conversation, upsert into `conversations` using its `conversation_id` as `id`; store `title`, `create_time`, `update_time`, `current_node`, flags (`is_archived`, `is_starred`), provenance fields, and `raw`.
  3) Traverse `mapping` to collect messages; compute `idx_in_conv` as a stable order (e.g., DFS topological with deterministic sort) for reproducible retrieval.
  4) Insert only `role in ('user','assistant')`; skip others but keep the conversation `raw`.
  5) For each kept message: store IDs, parent_id, timestamps (epoch → timestamptz), content (`content.parts` joined into `content_text`, plus `content_parts`, `content_type`), `turn_summary` (if present), model/finish metadata, `weight`, `end_turn`, `recipient`, `channel`, `request_id`, `turn_exchange_id`, `metadata`, and `raw`.
  6) Enforce max length on `content_text`; truncate overly long messages and record a warning in ingestion logs/`ingest_runs.stats`.
  6) Enforce idempotency: primary key on message id; do nothing on conflict (or update metadata/timestamps if desired).
  7) Record ingestion runs in `ingest_runs(id uuid pk default gen_random_uuid(), source_path text, started_at timestamptz, completed_at timestamptz, status text check in ('running','succeeded','failed'), stats jsonb, error text)`.
- Fail fast on malformed JSON; log and continue on per-message errors; surface counts of inserted/updated/skipped.

## Consequences
- Requires a deterministic traversal to keep `idx_in_conv` stable across re-ingests.
- Skipping non-user/assistant roles reduces noise; downstream retrieval relies on `turn_summary` being present when available.
- Keeping `raw` at both conversation and message levels increases storage but preserves fidelity for future schema evolution.
- Ingest runs enable observability and retries.

## Alternatives
- Ingest all roles: increases storage and retrieval noise.
- Drop raw blobs: lighter storage but harder to rehydrate or migrate.
- Store as documents only: simpler ingest, but loses relational guarantees and threading.


# ADR-0001: Database stack and schema boundaries
Status: Accepted  
Date: 2025-12-25

## Context
- Lens will store ChatGPT conversation dumps and serve RAG-style retrieval.
- We need relational integrity for conversation/message threading, plus vector similarity for embeddings.
- Data size is moderate; strong consistency and ease of ops matter more than extreme scale.

## Decision
- Use PostgreSQL as the primary datastore with the `pgvector` extension for similarity search.
- Core tables:
  - `conversations(id uuid pk, title text, create_time timestamptz, update_time timestamptz, current_node uuid null, is_archived bool, is_starred bool, origin text null, default_model_slug text null, memory_scope text null, raw jsonb)`.
  - `messages(id uuid pk, conversation_id fk, role text check in ('user','assistant'), parent_id uuid null fk, idx_in_conv int, create_time timestamptz, update_time timestamptz, content_text text, content_parts jsonb, content_type text, turn_summary text null, model_slug text null, finish_type text null, finish_stop text null, weight double precision null, end_turn bool, recipient text null, channel text null, request_id text null, turn_exchange_id text null, metadata jsonb null, raw jsonb).
  - `message_embeddings(message_id fk, provider text, model text, dim int, vector vector, created_at timestamptz default now(), primary key(message_id, provider, model))`.
  - Optional `conversation_stats` materialized view for counts and timestamps.
- Indexes: btree on `(conversation_id, idx_in_conv)`, `(parent_id)`, and trgm/GIN on `content_text` and `turn_summary`; vector index on `message_embeddings.vector`.
- Store full raw JSON blobs (`raw`) for auditability and future migrations.

## Consequences
- Requires PostgreSQL with `pgvector` installed and enabled.
- Migrations must keep schema and constraints in sync with ingestion assumptions (role filter, idx ordering, timestamp conversion).
- Vector index maintenance is needed when embeddings are added or refreshed.
- Keeping `raw` increases storage but simplifies downstream recovery and reprocessing.

## Alternatives
- SQLite + FAISS: simpler to embed but weaker concurrency and migration story.
- Document store only (e.g., Mongo/Elastic): easier schemaless ingest but worse for relational threading and constraints.
- Pure file-based embeddings: simpler initial setup but brittle for joins and audit trails.


BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id uuid PRIMARY KEY,
    title text,
    create_time timestamptz,
    update_time timestamptz,
    current_node uuid,
    is_archived boolean DEFAULT false,
    is_starred boolean DEFAULT false,
    origin text,
    default_model_slug text,
    memory_scope text,
    raw jsonb
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id uuid PRIMARY KEY,
    conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    parent_id uuid REFERENCES messages(id),
    idx_in_conv integer NOT NULL,
    create_time timestamptz,
    update_time timestamptz,
    content_text text,
    content_parts jsonb,
    content_type text,
    turn_summary text,
    model_slug text,
    finish_type text,
    finish_stop text,
    weight double precision,
    end_turn boolean,
    recipient text,
    channel text,
    request_id text,
    turn_exchange_id text,
    metadata jsonb,
    raw jsonb,
    CHECK (idx_in_conv >= 0),
    CHECK (content_text IS NULL OR char_length(content_text) <= 32000),
    CHECK (turn_summary IS NULL OR char_length(turn_summary) <= 4000)
);

CREATE UNIQUE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, idx_in_conv);
CREATE INDEX IF NOT EXISTS messages_parent_idx ON messages (parent_id);
CREATE INDEX IF NOT EXISTS messages_turn_summary_trgm_idx ON messages USING gin (turn_summary gin_trgm_ops);
CREATE INDEX IF NOT EXISTS messages_content_text_trgm_idx ON messages USING gin (content_text gin_trgm_ops);

CREATE TABLE IF NOT EXISTS message_embeddings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    assistant_message_id uuid REFERENCES messages(id) ON DELETE CASCADE,
    provider text NOT NULL,
    model text NOT NULL,
    dim integer NOT NULL DEFAULT 3072,
    content_used text NOT NULL,
    content_hash text,
    used_turn_summary boolean DEFAULT false,
    vector vector(3072) NOT NULL,
    created_at timestamptz DEFAULT now(),
    UNIQUE (user_message_id, provider, model),
    CHECK (vector_dims(vector) = dim)
);

CREATE INDEX IF NOT EXISTS message_embeddings_assistant_idx ON message_embeddings (assistant_message_id);
CREATE INDEX IF NOT EXISTS message_embeddings_provider_model_idx ON message_embeddings (provider, model);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    pinned boolean DEFAULT false,
    archived boolean DEFAULT false,
    metadata jsonb
);

-- Session messages
CREATE TABLE IF NOT EXISTS session_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    idx integer NOT NULL,
    created_at timestamptz DEFAULT now(),
    UNIQUE (session_id, message_id),
    UNIQUE (session_id, idx)
);

CREATE INDEX IF NOT EXISTS session_messages_session_idx ON session_messages (session_id, idx);

-- Ingest runs
CREATE TABLE IF NOT EXISTS ingest_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_path text,
    started_at timestamptz,
    completed_at timestamptz,
    status text CHECK (status IN ('running', 'succeeded', 'failed')),
    stats jsonb,
    error text
);

COMMIT;


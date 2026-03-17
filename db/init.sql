-- Pro Agent Database Initialization
-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Sessions (E-02)
CREATE TABLE IF NOT EXISTS sessions (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         varchar(255) NOT NULL,
    agent_id        varchar(255) NOT NULL DEFAULT 'pro-agent',
    thread_id       varchar(255) UNIQUE NOT NULL,
    metadata        jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_active_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions (last_active_at DESC);

-- Conversation Turns (E-01)
CREATE TABLE IF NOT EXISTS conversation_turns (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id     varchar(255) NOT NULL,
    role        varchar(20) NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content     text NOT NULL,
    embedding   vector(1536),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_turns_session_id ON conversation_turns (session_id);
CREATE INDEX IF NOT EXISTS idx_turns_user_id ON conversation_turns (user_id);
CREATE INDEX IF NOT EXISTS idx_turns_created_at ON conversation_turns (created_at DESC);

-- User Facts (E-03)
CREATE TABLE IF NOT EXISTS user_facts (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     varchar(255) NOT NULL,
    fact        text NOT NULL,
    embedding   vector(1536),
    source      varchar(50) NOT NULL DEFAULT 'chat',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_facts_user_id ON user_facts (user_id);

-- Tool Call Logs (E-04)
CREATE TABLE IF NOT EXISTS tool_call_logs (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    turn_id     uuid NOT NULL REFERENCES conversation_turns(id) ON DELETE CASCADE,
    tool_name   varchar(100) NOT NULL,
    parameters  jsonb NOT NULL DEFAULT '{}',
    result      jsonb NOT NULL DEFAULT '{}',
    success     boolean NOT NULL,
    duration_ms integer NOT NULL,
    cost        numeric(10,6) DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_logs_turn_id ON tool_call_logs (turn_id);
CREATE INDEX IF NOT EXISTS idx_tool_logs_tool_name ON tool_call_logs (tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_logs_created_at ON tool_call_logs (created_at DESC);

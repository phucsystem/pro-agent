import logging
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)
_pool: AsyncConnectionPool | None = None


async def _ensure_tables(pool: AsyncConnectionPool) -> None:
    from app.db.tables import SESSIONS, CONVERSATION_TURNS, USER_FACTS, TOOL_CALL_LOGS
    async with pool.connection() as conn:
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SESSIONS} (
                id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id         varchar(255) NOT NULL,
                agent_id        varchar(255) NOT NULL DEFAULT 'pro-agent',
                thread_id       varchar(255) UNIQUE NOT NULL,
                metadata        jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                created_at      timestamptz NOT NULL DEFAULT now(),
                last_active_at  timestamptz NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_{SESSIONS}_user_id ON {SESSIONS} (user_id);
            CREATE INDEX IF NOT EXISTS idx_{SESSIONS}_last_active ON {SESSIONS} (last_active_at DESC);

            CREATE TABLE IF NOT EXISTS {CONVERSATION_TURNS} (
                id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
                session_id  uuid NOT NULL REFERENCES {SESSIONS}(id) ON DELETE CASCADE,
                user_id     varchar(255) NOT NULL,
                role        varchar(20) NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
                content     text NOT NULL,
                embedding   vector(1536),
                created_at  timestamptz NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_{CONVERSATION_TURNS}_session ON {CONVERSATION_TURNS} (session_id);
            CREATE INDEX IF NOT EXISTS idx_{CONVERSATION_TURNS}_user ON {CONVERSATION_TURNS} (user_id);
            CREATE INDEX IF NOT EXISTS idx_{CONVERSATION_TURNS}_created ON {CONVERSATION_TURNS} (created_at DESC);

            CREATE TABLE IF NOT EXISTS {USER_FACTS} (
                id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id     varchar(255) NOT NULL,
                fact        text NOT NULL,
                embedding   vector(1536),
                source      varchar(50) NOT NULL DEFAULT 'chat',
                created_at  timestamptz NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_{USER_FACTS}_user ON {USER_FACTS} (user_id);

            CREATE TABLE IF NOT EXISTS {TOOL_CALL_LOGS} (
                id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
                turn_id     uuid NOT NULL REFERENCES {CONVERSATION_TURNS}(id) ON DELETE CASCADE,
                tool_name   varchar(100) NOT NULL,
                parameters  jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                result      jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                success     boolean NOT NULL,
                duration_ms integer NOT NULL,
                cost        numeric(10,6) DEFAULT 0,
                created_at  timestamptz NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_{TOOL_CALL_LOGS}_turn ON {TOOL_CALL_LOGS} (turn_id);
            CREATE INDEX IF NOT EXISTS idx_{TOOL_CALL_LOGS}_tool ON {TOOL_CALL_LOGS} (tool_name);
            CREATE INDEX IF NOT EXISTS idx_{TOOL_CALL_LOGS}_created ON {TOOL_CALL_LOGS} (created_at DESC);
        """)
    logger.info(f"Tables ensured (prefix={SESSIONS.replace('sessions', '')!r})")


async def init_pool(postgres_url: str) -> None:
    global _pool
    conninfo = postgres_url.replace("postgres://", "postgresql://", 1)
    _pool = AsyncConnectionPool(conninfo=conninfo, min_size=2, max_size=10, open=False)
    await _pool.open(wait=True, timeout=10)
    logger.info("DB pool opened")
    await _ensure_tables(_pool)


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool

import logging
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)
_pool: AsyncConnectionPool | None = None


async def init_pool(postgres_url: str) -> None:
    global _pool
    # psycopg3 uses conninfo string, convert postgres:// → postgresql://
    conninfo = postgres_url.replace("postgres://", "postgresql://", 1)
    _pool = AsyncConnectionPool(conninfo=conninfo, min_size=2, max_size=10, open=False)
    await _pool.open(wait=True, timeout=10)
    logger.info("DB pool opened")


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool

import logging
import asyncio
from app.db.pool import get_pool
from app.db.tables import SESSIONS, CONVERSATION_TURNS, USER_FACTS
from app.memory.embeddings import generate_embedding

logger = logging.getLogger(__name__)


async def _get_or_create_session(conn, user_id: str, thread_id: str) -> str:
    row = await conn.fetchrow(
        f"""
        INSERT INTO {SESSIONS} (user_id, thread_id)
        VALUES ($1, $2)
        ON CONFLICT (thread_id) DO UPDATE SET last_active_at = now()
        RETURNING id
        """,
        user_id, thread_id,
    )
    return str(row["id"])


async def store_turn(
    thread_id: str,
    user_id: str,
    role: str,
    content: str,
    embedding: list[float] | None = None,
) -> str:
    """Store a single conversation turn. Returns the turn UUID."""
    async with get_pool().connection() as conn:
        session_id = await _get_or_create_session(conn, user_id, thread_id)
        row = await conn.fetchrow(
            f"""
            INSERT INTO {CONVERSATION_TURNS} (session_id, user_id, role, content, embedding)
            VALUES ($1, $2, $3, $4, $5::vector)
            RETURNING id
            """,
            session_id, user_id, role, content,
            f"[{','.join(str(v) for v in embedding)}]" if embedding else None,
        )
        return str(row["id"])


async def store_turn_pair(
    thread_id: str,
    user_id: str,
    user_content: str,
    assistant_content: str,
) -> None:
    """Store user + assistant turns with embeddings (embeddings generated async)."""
    try:
        user_emb, asst_emb = await asyncio.gather(
            generate_embedding(user_content),
            generate_embedding(assistant_content),
        )
        await store_turn(thread_id, user_id, "user", user_content, user_emb)
        await store_turn(thread_id, user_id, "assistant", assistant_content, asst_emb)
    except Exception as exc:
        logger.warning(f"store_turn_pair failed: {exc}")


async def store_user_fact(user_id: str, fact: str, source: str = "chat") -> None:
    """Store a user fact with embedding."""
    embedding = await generate_embedding(fact)
    async with get_pool().connection() as conn:
        await conn.execute(
            f"""
            INSERT INTO {USER_FACTS} (user_id, fact, embedding, source)
            VALUES ($1, $2, $3::vector, $4)
            """,
            user_id, fact,
            f"[{','.join(str(v) for v in embedding)}]" if embedding else None,
            source,
        )

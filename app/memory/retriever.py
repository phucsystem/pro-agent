import logging
from app.db.pool import get_pool
from app.db.tables import CONVERSATION_TURNS, USER_FACTS
from app.memory.embeddings import generate_embedding
from app.config import settings

logger = logging.getLogger(__name__)


async def retrieve_relevant_turns(
    embedding: list[float],
    user_id: str,
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[dict]:
    k = top_k or settings.memory_top_k_turns
    thresh = threshold or settings.memory_similarity_threshold
    emb_str = f"[{','.join(str(v) for v in embedding)}]"

    async with get_pool().connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT role, content, created_at,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM {CONVERSATION_TURNS}
            WHERE user_id = $2
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> $1::vector) > $3
            ORDER BY embedding <=> $1::vector
            LIMIT $4
            """,
            emb_str, user_id, thresh, k,
        )
    return [dict(row) for row in rows]


async def retrieve_user_facts(
    embedding: list[float],
    user_id: str,
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[str]:
    k = top_k or settings.memory_top_k_facts
    thresh = threshold or settings.memory_similarity_threshold
    emb_str = f"[{','.join(str(v) for v in embedding)}]"

    async with get_pool().connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT fact
            FROM {USER_FACTS}
            WHERE user_id = $1
              AND embedding IS NOT NULL
              AND 1 - (embedding <=> $2::vector) > $3
            ORDER BY embedding <=> $2::vector
            LIMIT $4
            """,
            user_id, emb_str, thresh, k,
        )
    return [row["fact"] for row in rows]


async def build_memory_context(message: str, user_id: str) -> str:
    """Generate embedding for message, retrieve relevant turns + facts, format for prompt."""
    embedding = await generate_embedding(message)
    if not embedding:
        return ""

    turns = await retrieve_relevant_turns(embedding, user_id)
    facts = await retrieve_user_facts(embedding, user_id)

    parts = []
    if turns:
        turn_lines = [f"[{t['role']}]: {t['content'][:200]}" for t in turns]
        parts.append("## Relevant past conversations:\n" + "\n".join(turn_lines))
    if facts:
        parts.append("## Known about this user:\n" + "\n".join(f"- {f}" for f in facts))

    return "\n\n".join(parts)

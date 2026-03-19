import logging
import litellm
from app.config import settings

logger = logging.getLogger(__name__)


def format_embedding(embedding: list[float]) -> str:
    """Format embedding vector as pgvector-compatible string."""
    return f"[{','.join(str(v) for v in embedding)}]"


async def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding via LiteLLM using configured model."""
    try:
        kwargs = dict(model=settings.embedding_model, input=text)
        if settings.embedding_api_key:
            kwargs["api_key"] = settings.embedding_api_key
        if settings.embedding_api_base:
            kwargs["api_base"] = settings.embedding_api_base
        response = await litellm.aembedding(**kwargs)
        embedding = response.data[0]["embedding"]
        if len(embedding) != settings.embedding_dimension:
            logger.warning(
                f"Embedding dimension mismatch: got {len(embedding)}, "
                f"expected {settings.embedding_dimension}"
            )
            return None
        return embedding
    except Exception as exc:
        logger.warning(f"Embedding generation failed: {exc}")
        return None

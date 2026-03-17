import logging
import litellm
from app.config import settings

logger = logging.getLogger(__name__)


async def generate_embedding(text: str) -> list[float] | None:
    """Generate embedding via LiteLLM using configured model."""
    try:
        kwargs = dict(model=settings.embedding_model, input=text)
        if settings.embedding_api_key:
            kwargs["api_key"] = settings.embedding_api_key
        if settings.embedding_api_base:
            kwargs["api_base"] = settings.embedding_api_base
        response = await litellm.aembedding(**kwargs)
        return response.data[0]["embedding"]
    except Exception as exc:
        logger.warning(f"Embedding generation failed: {exc}")
        return None

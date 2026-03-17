import logging

logger = logging.getLogger(__name__)

_langfuse = None


def init_langfuse(public_key: str, secret_key: str, host: str) -> None:
    global _langfuse
    if not public_key or not secret_key:
        logger.info("Langfuse not configured — tracing disabled")
        return
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        logger.info("Langfuse initialized")
    except Exception as exc:
        logger.warning(f"Langfuse init failed: {exc}")


def get_langfuse():
    return _langfuse


def create_trace(name: str, user_id: str | None = None, session_id: str | None = None):
    """Create a Langfuse trace. Returns trace or None if Langfuse not configured."""
    if not _langfuse:
        return None
    try:
        return _langfuse.trace(name=name, user_id=user_id, session_id=session_id)
    except Exception:
        return None

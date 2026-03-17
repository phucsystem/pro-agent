from pathlib import Path
from functools import lru_cache

_FALLBACK_SOUL = "You are a helpful assistant. Be concise and direct."


@lru_cache(maxsize=1)
def load_identity() -> str:
    soul_path = Path("SOUL.md")
    soul_content = ""
    if soul_path.exists():
        soul_content = soul_path.read_text().strip()
    else:
        import logging
        logging.warning("SOUL.md not found, using fallback")

    from app.config import settings
    identity_parts = []
    if settings.agent_name or settings.agent_role or settings.agent_style:
        identity_parts.append(
            f"# Identity\n\n"
            f"**Name:** {settings.agent_name}\n"
            f"**Role:** {settings.agent_role}\n"
            f"**Style:** {settings.agent_style}"
        )
    if soul_content:
        identity_parts.append(soul_content)

    return "\n\n".join(identity_parts) if identity_parts else _FALLBACK_SOUL

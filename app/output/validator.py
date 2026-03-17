import json
import logging
from pydantic import BaseModel, ValidationError
from typing import Type

logger = logging.getLogger(__name__)


def validate_output(raw_text: str, schema_class: Type[BaseModel] | None = None) -> tuple[dict, bool]:
    """Validate LLM output against Pydantic schema.
    Returns (result_dict, is_structured).
    Falls back to {"content": raw_text} on failure — never raises.
    """
    if not schema_class:
        return {"content": raw_text}, False

    try:
        parsed = json.loads(raw_text)
        validated = schema_class.model_validate(parsed)
        return validated.model_dump(), True
    except (json.JSONDecodeError, ValidationError, Exception) as exc:
        logger.debug(f"Output validation failed ({schema_class.__name__}): {exc}")
        return {"content": raw_text}, False

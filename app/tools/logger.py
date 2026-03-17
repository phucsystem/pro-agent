import json
import logging
from app.observability.langfuse import get_langfuse

logger = logging.getLogger(__name__)


async def log_tool_call(
    turn_id: str | None,
    tool_name: str,
    parameters: dict,
    result: dict | str,
    success: bool,
    duration_ms: int,
    cost: float = 0.0,
) -> None:
    """Log tool call to database and Langfuse."""
    # DB logging
    if turn_id:
        try:
            from app.db.pool import get_pool
            result_json = result if isinstance(result, dict) else {"output": str(result)[:2000]}
            async with get_pool().connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO tool_call_logs
                        (turn_id, tool_name, parameters, result, success, duration_ms, cost)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    turn_id, tool_name,
                    json.dumps(parameters),
                    json.dumps(result_json),
                    success, duration_ms, cost,
                )
        except Exception as exc:
            logger.warning(f"tool_call_logs DB write failed: {exc}")

    # Langfuse span
    lf = get_langfuse()
    if lf:
        try:
            lf.span(
                name=f"tool:{tool_name}",
                metadata={
                    "tool": tool_name,
                    "success": success,
                    "duration_ms": duration_ms,
                    "cost": cost,
                },
            )
        except Exception:
            pass

import logging
from app.identity import load_identity
from app.models.responses import ToolCallSummary

logger = logging.getLogger(__name__)


async def run_agent(content: str, sender: str, thread_id: str) -> tuple[str, list | None]:
    """Shared pipeline for /chat and /webhook."""
    from app.agent.graph import get_graph

    system_prompt = load_identity()

    # Memory retrieval (graceful degradation)
    memory_context = ""
    try:
        from app.memory.retriever import build_memory_context
        memory_context = await build_memory_context(content, sender)
    except Exception as exc:
        logger.warning(f"Memory retrieval failed (degraded): {exc}")

    if memory_context:
        system_prompt = f"{system_prompt}\n\n{memory_context}"

    graph = get_graph()
    result = await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": content}],
            "system_prompt": system_prompt,
            "sender": sender,
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    last_message = result["messages"][-1]
    reply_content = last_message.content
    if not reply_content:
        raise ValueError("LLM returned empty response")
    reply = reply_content if isinstance(reply_content, str) else str(reply_content)

    # Store turns (fire-and-forget)
    try:
        from app.memory.store import store_turn_pair
        await store_turn_pair(
            thread_id=thread_id,
            user_id=sender,
            user_content=content,
            assistant_content=reply,
        )
    except Exception as exc:
        logger.warning(f"Memory store failed: {exc}")

    tool_calls_summary = _extract_tool_calls(result["messages"])
    return reply, tool_calls_summary or None


def _extract_tool_calls(messages: list) -> list[dict]:
    summaries = []
    tool_results: dict[str, str] = {}

    for msg in messages:
        if hasattr(msg, "type") and msg.type == "tool":
            tool_results[getattr(msg, "tool_call_id", "")] = str(msg.content)[:200]

    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                result_text = tool_results.get(tc.get("id", ""), "")
                summaries.append(ToolCallSummary(
                    tool=tc.get("name", "unknown"),
                    result=result_text,
                    success=bool(result_text) and not result_text.startswith("Error:"),
                ))
    return summaries

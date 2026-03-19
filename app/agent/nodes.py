import json
import litellm
from langchain_core.messages import AIMessage
from app.config import settings
from app.agent.state import AgentState


async def agent_node(state: AgentState) -> dict:
    """Build full prompt and invoke LLM via LiteLLM."""
    system_content = state.get("system_prompt", "")

    # Convert LangGraph messages to LiteLLM format
    lc_messages = state["messages"]
    litellm_messages = [{"role": "system", "content": system_content}]
    for msg in lc_messages:
        role = getattr(msg, "type", None)
        if role == "human":
            litellm_messages.append({"role": "user", "content": str(msg.content)})
        elif role == "ai":
            litellm_messages.append({"role": "assistant", "content": str(msg.content)})
        elif role == "tool":
            litellm_messages.append({
                "role": "tool",
                "content": str(msg.content),
                "tool_call_id": getattr(msg, "tool_call_id", ""),
            })

    # Get registered tools if any
    tools = None
    try:
        from app.tools.registry import get_registered_tools
        registered = get_registered_tools()
        if registered:
            # Convert LangChain tools to OpenAI tool format via LiteLLM
            tools = [t.get_openai_schema() if hasattr(t, "get_openai_schema") else None for t in registered]
            tools = [t for t in tools if t]
    except Exception:
        pass

    # Build LiteLLM model string: provider/model (e.g. deepseek/deepseek-chat)
    # LiteLLM requires the provider prefix for proper routing
    provider = settings.llm_provider.lower()
    model_name = settings.llm_model
    if "/" not in model_name:
        litellm_model = f"{provider}/{model_name}"
    else:
        litellm_model = model_name  # already prefixed (e.g. openrouter/deepseek/deepseek-chat)

    kwargs = dict(
        model=litellm_model,
        messages=litellm_messages,
        api_key=settings.llm_api_key,
        api_base=settings.llm_base_url or None,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.llm_timeout,
    )
    if tools:
        kwargs["tools"] = tools

    response = await litellm.acompletion(**kwargs)
    msg = response.choices[0].message

    # Handle DeepSeek R1 reasoning_content (deepseek-reasoner model)
    reasoning = getattr(msg, "reasoning_content", None)
    if reasoning:
        msg.content = f"<think>\n{reasoning}\n</think>\n\n{msg.content or ''}"

    # Enforce tool call limit per turn
    tool_call_count = state.get("tool_call_count", 0)
    allow_tools = (
        msg.tool_calls is not None
        and tool_call_count < settings.tools_max_calls_per_turn
    )

    # Convert back to LangChain AIMessage
    if allow_tools:
        tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "args": json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
            }
            for tc in msg.tool_calls
        ]
        new_count = tool_call_count + len(tool_calls)
    else:
        tool_calls = []
        new_count = tool_call_count

    ai_message = AIMessage(content=msg.content or "", tool_calls=tool_calls)
    return {"messages": [ai_message], "tool_call_count": new_count}

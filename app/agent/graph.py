from functools import lru_cache
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.state import AgentState
from app.agent.nodes import agent_node


def create_graph():
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")

    # Tool routing (wired but inactive until Phase 3 registers tools)
    try:
        from app.tools.registry import get_registered_tools
        tools = get_registered_tools()
        if tools:
            from langgraph.prebuilt import ToolNode, tools_condition
            builder.add_node("tools", ToolNode(tools))
            builder.add_conditional_edges("agent", tools_condition, {
                "tools": "tools",
                "__end__": END,
            })
            builder.add_edge("tools", "agent")
        else:
            builder.add_edge("agent", END)
    except Exception:
        builder.add_edge("agent", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


@lru_cache(maxsize=1)
def get_graph():
    return create_graph()

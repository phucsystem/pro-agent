import operator
from typing import Annotated
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    system_prompt: str
    sender: str
    tool_call_count: Annotated[int, operator.add] = 0

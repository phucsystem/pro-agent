from pydantic import BaseModel
from typing import Any


class ToolCallSummary(BaseModel):
    tool: str
    result: str
    success: bool


class ChatResponse(BaseModel):
    reply: str
    agent: str = "pro-agent"
    timestamp: str
    tool_calls: list[ToolCallSummary] | None = None


class WebhookResponse(BaseModel):
    reply: str
    agent: str = "pro-agent"
    conversation_id: str
    timestamp: str


class WebhookSkippedResponse(BaseModel):
    skipped: bool = True
    reason: str = "ignoring agent messages"


class MemoryStats(BaseModel):
    total_turns: int = 0
    total_sessions: int = 0
    total_user_facts: int = 0
    pgai_connected: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"
    agent: str = "pro-agent"
    version: str = "1.0.0"
    provider: str
    model: str
    uptime: int
    memory_stats: MemoryStats
    tools_available: list[str] = []

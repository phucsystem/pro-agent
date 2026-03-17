# Phase 3: MCP Tool Use + Guardrails + Logging

## Context Links
- [SRD.md](../../docs/SRD.md) — FR-09 to FR-14
- [API_SPEC.md](../../docs/API_SPEC.md) — §4.4 MCP Tool Executor, §4.5 Langfuse Tracer
- [Dumb Agent tools.js](https://github.com/phucsystem/a-dumb-agent) — Empty tools array, but graph wired for ToolNode

## Overview
- **Priority:** P2
- **Status:** ✅ Complete
- **Effort:** 6h
- **FRs:** FR-09 (MCP Integration), FR-10 (Web Search), FR-11 (GitHub), FR-12 (File I/O), FR-13 (Guardrails), FR-14 (Logging)

Add MCP tool layer to the agent graph. Agent can now call external tools (web search, GitHub, file I/O) during response generation. Tool calls guarded by max-calls-per-turn and timeout limits. All tool invocations logged to Langfuse and tool_call_logs table.

## Key Insights
- Dumb Agent graph already has conditional tool routing (toolsCondition) — just no tools registered
- `langchain-mcp-adapters` bridges MCP servers → LangChain tools → LangGraph ToolNode
- Guardrails: intercept before each tool call, check counter + elapsed time
- Langfuse Python SDK integrates natively with LangChain callbacks
- tool_calls array only returned in /chat response, NOT /webhook (keep webhook simple)

## Requirements

**Functional:**
- FR-09: MCP tool layer via langchain-mcp-adapters, tool results fed back to agent loop
- FR-10: Web search tool — search queries, return summaries
- FR-11: GitHub tool — read repos, list/create issues
- FR-12: File I/O tool — read/write within sandboxed directory
- FR-13: Max 5 tool calls/turn (configurable), 30s timeout/call, partial response on limit
- FR-14: Every tool call → Langfuse trace + tool_call_logs table

**Non-Functional:**
- NFR-01: < 15s response latency with tool calls
- NFR-02: Tool call success > 90%, graceful failure (agent responds without tool result)
- NFR-04: File I/O sandboxed to configured directory

## Architecture

```
app/
├── agent/
│   ├── graph.py         # MODIFY: add ToolNode + conditional edges
│   └── nodes.py         # MODIFY: bind tools to LLM
├── tools/
│   ├── __init__.py
│   ├── registry.py      # Load + register MCP tools from config
│   ├── guardrails.py    # Max calls, timeout, cost limits
│   └── logger.py        # Log tool calls to Langfuse + DB
└── observability/
    ├── __init__.py
    └── langfuse.py      # Langfuse client setup, trace/span helpers
```

## Related Code Files

**Create:**
- `app/tools/__init__.py`
- `app/tools/registry.py` — MCP tool loading + registration
- `app/tools/guardrails.py` — call counter, timeout, cost guard
- `app/tools/logger.py` — tool call logging (Langfuse + DB)
- `app/observability/__init__.py`
- `app/observability/langfuse.py` — Langfuse client, trace context

**Modify:**
- `app/agent/graph.py` — add ToolNode, conditional edges (agent → tools → agent)
- `app/agent/nodes.py` — bind tools to LLM model
- `app/main.py` — add tool_calls to /chat response, init Langfuse on startup
- `requirements.txt` — add `langchain-mcp-adapters`, `langfuse`, `mcp`

## Implementation Steps

### 1. Create app/observability/langfuse.py

```python
from langfuse import Langfuse
from langfuse.callback import CallbackHandler

langfuse_client: Langfuse | None = None

def init_langfuse(public_key, secret_key, host):
    global langfuse_client
    if public_key and secret_key:
        langfuse_client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

def get_langfuse_handler(trace_name, user_id=None, session_id=None):
    """Create CallbackHandler for LangChain integration."""
    if not langfuse_client:
        return None
    return CallbackHandler(
        trace_name=trace_name,
        user_id=user_id,
        session_id=session_id,
    )
```

Register init in FastAPI lifespan. If LANGFUSE env vars not set → skip (no-op).

### 2. Create app/tools/registry.py

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

async def load_mcp_tools(config) -> list:
    """Load tools from MCP servers based on agent.yaml config."""
    tools = []

    if "web_search" in config.tools.enabled:
        # Connect to web search MCP server
        pass

    if "github" in config.tools.enabled:
        # Connect to GitHub MCP server
        pass

    if "file_io" in config.tools.enabled:
        # Create file I/O tools with sandbox restriction
        pass

    return tools
```

**Approach:** Start with LangChain native tools (simpler), migrate to full MCP servers later if needed:
- `web_search`: Use `TavilySearchResults` or `DuckDuckGoSearchResults` tool
- `github`: Use custom tool wrapping `gh` CLI or PyGithub
- `file_io`: Custom tool with path validation (sandbox check)

### 3. Create app/tools/guardrails.py

```python
class ToolGuardrails:
    def __init__(self, max_calls_per_turn: int = 5, timeout_seconds: int = 30):
        self.max_calls = max_calls_per_turn
        self.timeout = timeout_seconds
        self.call_count = 0
        self.start_time = None

    def reset(self):
        self.call_count = 0
        self.start_time = time.time()

    def check(self) -> tuple[bool, str | None]:
        """Return (allowed, reason_if_blocked)."""
        if self.call_count >= self.max_calls:
            return False, f"Tool call limit reached ({self.max_calls})"
        elapsed = time.time() - self.start_time
        if elapsed > self.timeout * self.max_calls:
            return False, "Total tool execution timeout"
        self.call_count += 1
        return True, None
```

### 4. Create app/tools/logger.py

```python
async def log_tool_call(turn_id, tool_name, parameters, result, success, duration_ms, cost=0):
    """Write to tool_call_logs table + Langfuse span."""
    # INSERT INTO tool_call_logs ... (see DB_DESIGN.md)
    # Also create Langfuse span under current trace
```

### 5. Modify app/agent/graph.py — add tool routing

Port Dumb Agent's conditional tool routing:
```python
from langgraph.prebuilt import ToolNode, tools_condition

def create_graph(tools=None):
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")

    if tools:
        tool_node = ToolNode(tools)
        builder.add_node("tools", tool_node)
        builder.add_conditional_edges("agent", tools_condition, {
            "tools": "tools",
            "__end__": END,
        })
        builder.add_edge("tools", "agent")
    else:
        builder.add_edge("agent", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
```

### 6. Modify app/agent/nodes.py — bind tools to LLM

```python
async def agent_node(state: AgentState, tools=None):
    # ... existing prompt building ...
    model = get_llm()  # via LiteLLM
    if tools:
        model = model.bind_tools(tools)
    response = await model.ainvoke(messages)
    return {"messages": [response]}
```

### 7. Modify app/main.py — tool_calls in /chat response

```python
# After graph invocation, extract tool call info from message history
tool_calls_summary = []
for msg in result["messages"]:
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        for tc in msg.tool_calls:
            tool_calls_summary.append({
                "tool": tc["name"],
                "result": "...",  # from corresponding ToolMessage
                "success": True
            })

# Include in /chat response only (not /webhook)
response = {"reply": reply, "agent": "pro-agent", "timestamp": timestamp}
if tool_calls_summary:
    response["tool_calls"] = tool_calls_summary
```

### 8. Update /health to include tools_available

```python
# In health endpoint
tools_available = [tool.name for tool in registered_tools]
```

### 9. Test tool use end-to-end

- Send message requiring web search → agent uses tool, returns result
- Send message requiring multiple tools → agent chains tools
- Send 6+ tool-requiring tasks → guardrails kick in at 5
- Verify tool_call_logs table populated
- Verify Langfuse traces show tool spans
- Verify /webhook does NOT return tool_calls array
- Test tool timeout → agent responds without tool result

## Todo List

- [ ] Create app/observability/langfuse.py — client setup
- [ ] Create app/tools/registry.py — MCP/LangChain tool loading
- [ ] Create app/tools/guardrails.py — call limits + timeout
- [ ] Create app/tools/logger.py — DB + Langfuse logging
- [ ] Modify app/agent/graph.py — add ToolNode + conditional edges
- [ ] Modify app/agent/nodes.py — bind tools to LLM
- [ ] Modify app/main.py — tool_calls in /chat response
- [ ] Implement web_search tool
- [ ] Implement github tool
- [ ] Implement file_io tool (with sandbox validation)
- [ ] Update /health to list available tools
- [ ] Test: tool execution end-to-end
- [ ] Test: guardrails (max calls, timeout)
- [ ] Test: Langfuse traces with tool spans

## Success Criteria

- Agent successfully calls web search and returns relevant results
- Agent reads GitHub repos/issues via tool
- File I/O restricted to sandbox directory (path traversal blocked)
- Guardrails stop tool execution at configured limit
- tool_call_logs table records all invocations
- Langfuse shows complete trace with tool spans
- /chat response includes tool_calls array when tools used
- /webhook response does NOT include tool_calls
- Tool call success rate > 90% on test tasks

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| langchain-mcp-adapters unstable | Tool integration breaks | Start with native LangChain tools, add MCP layer incrementally |
| Tool calls hallucinate parameters | Failed executions | Strict Pydantic schemas on tool inputs, validation before execution |
| Langfuse adds latency | Slower responses | Async logging (fire-and-forget), don't block response on Langfuse |
| File I/O sandbox escape | Security vulnerability | Resolve all paths, check prefix match against sandbox dir, reject symlinks |

## Security Considerations
- File I/O tool MUST validate paths against sandbox directory (no `../` traversal)
- GitHub token scoped to minimum permissions needed
- Tool parameters logged but sensitive values (tokens, keys) redacted
- Langfuse traces may contain PII — document in privacy policy

## Next Steps
- Phase 4: Structured output schemas, LiteLLM multi-model routing, cost tracking

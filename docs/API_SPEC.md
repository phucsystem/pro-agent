# Interface Specification (API)

## 1. Endpoint Matrix

| Method | URL | Feature (FR-xx) | Endpoint (S-xx) | Phase | Auth |
|--------|-----|-----------------|-----------------|-------|------|
| POST | `/chat` | FR-02, FR-05, FR-06, FR-07, FR-08 | S-01 | 1 | Bearer |
| POST | `/webhook` | FR-03, FR-05, FR-06, FR-07, FR-08 | S-02 | 1 | Bearer |
| GET | `/health` | FR-04, FR-17 | S-03 | 1 | None |

**Internal components** (not HTTP endpoints, but key subsystems):

| Component | Features | Phase |
|-----------|----------|-------|
| Identity Loader | FR-01 | 1 |
| Memory Retriever (pgai) | FR-06, FR-07 | 1 |
| Session Manager | FR-08 | 1 |
| MCP Tool Executor | FR-09, FR-10, FR-11, FR-12 | 2 |
| Tool Guardrails | FR-13 | 2 |
| Langfuse Tracer | FR-14, FR-17 | 2 |
| Output Validator (Pydantic) | FR-15 | 3 |
| Model Router (LiteLLM) | FR-16 | 3 |
| Cost Tracker | FR-17 | 3 |

---

## 2. Endpoint Details

### POST /chat (S-01)

**Description:** Direct conversation API. Primary integration point for scripts, apps, and orchestrator agents. Backward-compatible with Dumb Agent.

**Features:** FR-02, FR-05, FR-06, FR-07, FR-08, FR-09, FR-13, FR-15

#### Request

```
POST /chat
Authorization: Bearer <AUTH_TOKEN>
Content-Type: application/json
```

```json
{
  "message": "string — required, the user's message",
  "sender": "string — optional, default: 'unknown'",
  "session_id": "string — optional, default: 'default'"
}
```

**Validation:**
- `message`: required, non-empty string, max 32,000 characters
- `sender`: optional, max 255 characters
- `session_id`: optional, max 255 characters, alphanumeric + hyphens + underscores

#### Response (200 OK)

```json
{
  "reply": "string — agent's response text",
  "agent": "pro-agent",
  "timestamp": "2026-03-18T10:00:00.000Z",
  "tool_calls": [
    {
      "tool": "web_search",
      "result": "Found 3 relevant articles about FastAPI security",
      "success": true
    }
  ]
}
```

**Field behavior:**
- `reply`: always present, never empty
- `agent`: always `"pro-agent"`
- `timestamp`: ISO 8601 UTC
- `tool_calls`: omitted if no tools were called (Phase 1), array if tools invoked (Phase 2+)

#### Error Responses

| Code | Body | Condition |
|------|------|-----------|
| 400 | `{ "error": "message is required" }` | Missing or empty `message` |
| 401 | `{ "error": "Unauthorized" }` | Missing/invalid bearer token |
| 500 | `{ "error": "LLM request failed" }` | LLM API error or internal error |
| 503 | `{ "error": "Memory service unavailable" }` | pgai down (agent still responds, degraded) |

#### Processing Pipeline

```
1. Auth check (FR-05)
2. Validate input
3. Get or create session by session_id (FR-08)
4. Load identity: SOUL.md + agent.yaml (FR-01)
5. Generate embedding for message
6. Retrieve top-k similar past turns from pgai (FR-06)
7. Retrieve top-k user facts for sender (FR-07)
8. Build system prompt: identity + retrieved memory + user facts
9. Invoke LangGraph agent with [system_prompt, ...history, user_message]
   a. LLM generates response
   b. If tool calls present → execute via MCP (FR-09), loop back to LLM
   c. Tool guardrails enforced: max calls, timeout (FR-13)
10. Store user turn + assistant turn as embeddings in pgai (FR-06)
11. Extract and store any new user facts (FR-07)
12. Log trace to Langfuse (FR-14)
13. Return response
```

---

### POST /webhook (S-02)

**Description:** Chatbot platform webhook. Identical contract to Dumb Agent — zero migration for Typebot/n8n integrations.

**Features:** FR-03, FR-05, FR-06, FR-07, FR-08

#### Request

```
POST /webhook
Authorization: Bearer <AUTH_TOKEN>
Content-Type: application/json
```

```json
{
  "event": "string — optional (e.g. 'message_created')",
  "message": {
    "content": "string — required, the user's message",
    "sender_name": "string — optional",
    "sender_id": "string — optional",
    "sender_is_agent": false,
    "conversation_id": "string — optional"
  },
  "conversation": {
    "id": "string — optional, fallback for conversation_id"
  }
}
```

**Input normalization:**
- `content` ← `message.content` (required)
- `sender` ← `message.sender_name` || `message.sender_id` || `"unknown"`
- `thread_id` ← `conversation.id` || `message.conversation_id` || `"default"`

#### Response (200 OK — processed)

```json
{
  "reply": "Hi John! How can I help?",
  "agent": "pro-agent",
  "conversation_id": "conv-456",
  "timestamp": "2026-03-18T10:00:00.000Z"
}
```

#### Response (200 OK — skipped)

```json
{
  "skipped": true,
  "reason": "ignoring agent messages"
}
```

**Skip condition:** `message.sender_is_agent === true` → return skip response immediately (prevent message loops).

#### Error Responses

| Code | Body | Condition |
|------|------|-----------|
| 400 | `{ "error": "message.content is required" }` | Missing `message` or `message.content` |
| 401 | `{ "error": "Unauthorized" }` | Missing/invalid bearer token |
| 500 | `{ "error": "LLM request failed" }` | LLM API error or internal error |

#### Processing Pipeline

```
1. Auth check (FR-05)
2. Extract and validate message.content
3. Check sender_is_agent → skip if true
4. Normalize: content, sender, thread_id
5. → Same pipeline as /chat steps 3–13
6. Return response (no tool_calls in webhook response — keep simple)
```

**Difference from /chat:** Webhook response never includes `tool_calls` field. Tool calls still execute internally, but the response stays simple for platform compatibility.

---

### GET /health (S-03)

**Description:** Status endpoint for monitoring, Docker healthchecks, and load balancers. No authentication.

**Features:** FR-04, FR-17

#### Request

```
GET /health
```

No body, no auth.

#### Response (200 OK)

```json
{
  "status": "ok",
  "agent": "pro-agent",
  "version": "1.0.0",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "uptime": 3600,
  "memory_stats": {
    "total_turns": 1542,
    "total_sessions": 23,
    "total_user_facts": 87,
    "pgai_connected": true
  },
  "tools_available": ["web_search", "github", "file_io"],
  "cost_stats": {
    "total_tool_cost_usd": 12.45,
    "total_requests": 342
  }
}
```

**Field behavior:**
- `uptime`: seconds since server start
- `memory_stats`: queried from PostgreSQL; if pgai unavailable, `pgai_connected: false` and counts = 0
- `tools_available`: list of registered MCP tool names (empty array in Phase 1)
- `cost_stats`: aggregated from `tool_call_logs` table (Phase 3, omitted in Phase 1–2)

---

## 3. Authentication Middleware

**Applies to:** `POST /chat`, `POST /webhook`
**Excludes:** `GET /health`

```python
# Pseudocode for auth middleware
async def auth_middleware(request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized")

    token = auth_header[7:]
    if not hmac.compare_digest(token, AUTH_TOKEN):
        raise HTTPException(401, "Unauthorized")
```

**Security properties:**
- Timing-safe comparison via `hmac.compare_digest` (prevents timing attacks)
- Token from `AUTH_TOKEN` environment variable
- Same pattern as Dumb Agent (NFR-07 backward compat)

---

## 3.5 Environment Variables

**Core settings:**

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_TOKEN` | Required | Bearer token for API authentication (no default) |
| `LLM_API_KEY` | Required | API key for LLM provider |
| `LLM_PROVIDER` | `deepseek` | LLM provider name (deepseek, openai, anthropic, ollama, etc.) |
| `LLM_MODEL` | `deepseek-chat` | Model identifier (e.g., gpt-4o, claude-sonnet-4-20250514) |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | LLM provider base URL |
| `LLM_TIMEOUT` | `60` | LLM API request timeout in seconds |
| `PORT` | `8000` | Server port |

**Database:**

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_URL` | `postgresql://agent:agent@localhost:5432/pro_agent` | PostgreSQL connection string |
| `DB_POOL_MIN` | `2` | Minimum number of connections in pool |
| `DB_POOL_MAX` | `10` | Maximum number of connections in pool |
| `DB_STATEMENT_TIMEOUT` | `30` | Statement execution timeout in seconds |
| `TABLE_PREFIX` | `""` (empty) | Optional prefix for all table names (for multi-agent DB isolation) |

**Embeddings (configurable via env vars):**

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name via LiteLLM |
| `EMBEDDING_DIMENSION` | `1536` | Expected embedding vector dimension (validates API output) |
| `EMBEDDING_API_KEY` | `""` (uses `LLM_API_KEY`) | API key for embedding provider (falls back to LLM_API_KEY if empty) |
| `EMBEDDING_API_BASE` | `""` (provider default) | Custom base URL for embedding API (e.g., for self-hosted embeddings) |

**Observability (optional):**

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | `""` (disabled) | Langfuse public key for tracing |
| `LANGFUSE_SECRET_KEY` | `""` (disabled) | Langfuse secret key for tracing |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse instance URL |

**Tools (optional):**

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | `""` (disabled) | GitHub API token for tool use |
| `SEARCH_API_KEY` | `""` (disabled) | Search API key (for web_search tool) |
| `FILE_IO_SANDBOX_DIR` | `/app/sandbox` | Sandbox directory for file I/O tool |

---

## 4. Internal Component Specs

### 4.1 Identity Loader (FR-01)

**Input files:**
- `SOUL.md` — Markdown, personality rules
- `agent.yaml` — YAML, structured config (name, role, style, model, memory, tools, cost)

**Behavior:**
1. Load at startup
2. If `SOUL.md` missing → fallback: `"You are a helpful assistant. Be concise and direct."`
3. If `agent.yaml` missing → use all defaults
4. Combine: identity text = `agent.yaml[name/role/style]` + `SOUL.md` content
5. Cache in memory (no hot-reload)

**Config defaults (from agent.yaml):**

| Key | Default |
|-----|---------|
| `name` | `"Pro Agent"` |
| `role` | `"A versatile assistant"` |
| `style` | `"Concise and direct"` |
| `model.provider` | `env.LLM_PROVIDER` or `"deepseek"` |
| `model.name` | `env.LLM_MODEL` or `"deepseek-chat"` |
| `model.temperature` | `0.7` |
| `model.max_tokens` | `4096` |
| `memory.top_k_turns` | `10` |
| `memory.top_k_facts` | `5` |
| `memory.similarity_threshold` | `0.7` |
| `tools.max_calls_per_turn` | `5` |
| `tools.timeout_seconds` | `30` |
| `cost.max_per_request` | `1.00` |

---

### 4.2 Memory Retriever (FR-06, FR-07)

**Semantic recall pipeline:**

```
Input: (message_text, user_id, config)
  │
  ├── Generate embedding for message_text
  │     └── LiteLLM → configured model → vector(1536)
  │
  ├── Query conversation_turns (FR-06)
  │     └── SELECT ... WHERE user_id = ? AND similarity > threshold
  │         ORDER BY similarity DESC LIMIT top_k_turns
  │
  ├── Query user_facts (FR-07)
  │     └── SELECT ... WHERE user_id = ?
  │         ORDER BY similarity DESC LIMIT top_k_facts
  │
  └── Format for system prompt injection:
        "## Relevant past conversations:\n{turns}\n\n## Known about this user:\n{facts}"
```

**Embedding model configuration:**
- Default model: `text-embedding-3-small` (via `EMBEDDING_MODEL` env var)
- Default API key: Uses `LLM_API_KEY` if `EMBEDDING_API_KEY` not set
- Custom API base: Set `EMBEDDING_API_BASE` to override provider (e.g., for local embeddings)
- All embedding parameters are configurable to support swapping providers at deployment time

**Degraded mode:** If pgai query fails (connection error), return empty context. Agent still works, just without memory. Log warning.

---

### 4.3 Session Manager (FR-08)

**Thread mapping:**
- `/chat` → `thread_id = session_id` (default: `"default"`)
- `/webhook` → `thread_id = conversation.id || message.conversation_id` (default: `"default"`)

**Behavior:**
1. On each request, upsert session by `thread_id`
2. Return `session_id` (UUID) for internal use
3. LangGraph uses `thread_id` for checkpointing (conversation history within a session)

---

### 4.4 MCP Tool Executor (FR-09–FR-12)

**Architecture:**

```
Agent Loop (LangGraph)
  │
  ├── LLM returns tool_call message
  │
  ├── ToolNode intercepts
  │     ├── Check guardrails (FR-13):
  │     │     ├── calls_this_turn < max_calls_per_turn?
  │     │     └── total_elapsed < timeout_seconds?
  │     │
  │     ├── Execute via MCP adapter
  │     │     └── langchain-mcp-adapters → MCP server
  │     │
  │     ├── Log to tool_call_logs table (FR-14)
  │     │
  │     └── Return tool result to agent loop
  │
  └── LLM processes tool results → generates final response
```

**Registered tools (Phase 2):**

| Tool | MCP Server | Capabilities |
|------|-----------|-------------|
| `web_search` | Web search MCP | Search queries, return summaries |
| `github` | GitHub MCP | Read repos, list/create issues |
| `file_io` | Local file MCP | Read/write files in sandbox dir |

**Guardrails (FR-13):**
- `max_calls_per_turn`: default 5, from `agent.yaml`
- `timeout_seconds`: default 30 per tool call
- If limit hit: inject system message "Tool call limit reached" → LLM must respond without more tools
- If timeout: tool result = `{"error": "timeout"}` → LLM handles gracefully

---

### 4.5 Langfuse Tracer (FR-14, FR-17)

**Trace structure per request:**

```
Trace: "chat-{request_id}"
  ├── Span: "memory_retrieval"
  │     ├── turns_retrieved: N
  │     ├── facts_retrieved: M
  │     └── duration_ms: X
  │
  ├── Span: "llm_call"
  │     ├── model: "deepseek-chat"
  │     ├── tokens_in: N
  │     ├── tokens_out: M
  │     └── cost: $X.XX
  │
  ├── Span: "tool_call" (0..N)
  │     ├── tool: "web_search"
  │     ├── parameters: {...}
  │     ├── success: true
  │     └── duration_ms: X
  │
  └── Span: "memory_store"
        └── turns_stored: 2
```

**Cost tracking (FR-17):**
- LiteLLM provides token counts + model pricing
- Tool call costs from `tool_call_logs.cost`
- Per-request total = LLM cost + tool costs
- Aggregated in `/health` response

---

### 4.6 Output Validator (FR-15)

**Pydantic schemas (Phase 3):**

```python
class GeneralReply(BaseModel):
    content: str
    confidence: float = Field(ge=0, le=1, default=1.0)

class ResearchReport(BaseModel):
    title: str
    summary: str
    sources: list[str] = []
    findings: list[str]

class CodeReview(BaseModel):
    file: str
    issues: list[dict]
    suggestions: list[str]
    overall_quality: str  # "good", "needs_work", "critical"
```

**Behavior:**
1. LLM response parsed against expected schema
2. If validation passes → return structured data
3. If validation fails → fallback to raw text reply (never block the response)
4. Log validation success/failure to Langfuse

---

### 4.7 Model Router (FR-16)

**Routing via LiteLLM:**

```python
# agent.yaml determines the default model
# LiteLLM handles provider routing transparently

litellm.completion(
    model=config.model.name,        # e.g. "deepseek/deepseek-chat"
    api_key=config.model.api_key,
    api_base=config.model.base_url,
    messages=messages,
    temperature=config.model.temperature,
    max_tokens=config.model.max_tokens,
)
```

**Supported providers (via LiteLLM):**

| Provider | Model Format | Base URL |
|----------|-------------|----------|
| DeepSeek | `deepseek/deepseek-chat` | `https://api.deepseek.com/v1` |
| OpenRouter | `openrouter/deepseek/deepseek-chat` | `https://openrouter.ai/api/v1` |
| Claude | `claude-sonnet-4-20250514` | Anthropic API |
| GPT | `gpt-4o` | OpenAI API |
| Ollama | `ollama/llama3` | `http://localhost:11434` |

---

## 5. Request Lifecycle (Complete)

```mermaid
flowchart TD
    A["HTTP Request<br/>POST /chat or /webhook"] --> B["Auth Middleware<br/>FR-05"]
    B -->|Invalid| B_err["401 Unauthorized"]
    B -->|Valid| C["Input Validation<br/>+ Normalization"]
    C -->|Invalid| C_err["400 Bad Request"]
    C -->|Valid| D{Webhook?}
    D -->|Yes, agent msg| D_skip["200 skipped: true"]
    D -->|No| E["Session Upsert<br/>FR-08"]
    E --> F["Identity Load<br/>FR-01"]
    F --> G["Embed Message<br/>text-embedding"]
    G -->|Fails| G_cont["Continue without embedding"]
    G -->|Success| H["Memory Retrieval<br/>FR-06, FR-07"]
    G_cont --> H
    H -->|pgai down| H_empty["Empty context"]
    H -->|Success| I["Build Prompt<br/>identity + memory + facts"]
    H_empty --> I
    I --> J["LangGraph Agent<br/>LLM Invocation FR-16"]
    J --> K{Tool calls?}
    K -->|Yes| L["MCP Tool Execute<br/>+ Guardrails FR-09-13"]
    L --> L_log["Log FR-14"]
    L_log --> J
    K -->|No| M["Validate Output<br/>FR-15"]
    M -->|Fails| M_fallback["Use raw text"]
    M -->|Success| N["Store Turns<br/>+ Embeddings FR-06, FR-07"]
    M_fallback --> N
    N --> O["Log to Langfuse<br/>FR-14, FR-17"]
    O --> P["Return 200 OK<br/>ChatResponse"]
    style B fill:#ffebee
    style C fill:#fff3e0
    style J fill:#e8f5e9
    style P fill:#c8e6c9


---

## 6. Traceability Check

| FR | Endpoint/Component | Covered |
|----|-------------------|---------|
| FR-01 | Identity Loader (§4.1) | ✅ |
| FR-02 | POST /chat (§2.1) | ✅ |
| FR-03 | POST /webhook (§2.2) | ✅ |
| FR-04 | GET /health (§2.3) | ✅ |
| FR-05 | Auth Middleware (§3) | ✅ |
| FR-06 | Memory Retriever (§4.2) | ✅ |
| FR-07 | Memory Retriever (§4.2) | ✅ |
| FR-08 | Session Manager (§4.3) | ✅ |
| FR-09 | MCP Tool Executor (§4.4) | ✅ |
| FR-10 | MCP Tool Executor (§4.4) | ✅ |
| FR-11 | MCP Tool Executor (§4.4) | ✅ |
| FR-12 | MCP Tool Executor (§4.4) | ✅ |
| FR-13 | MCP Tool Executor (§4.4) | ✅ |
| FR-14 | Langfuse Tracer (§4.5) | ✅ |
| FR-15 | Output Validator (§4.6) | ✅ |
| FR-16 | Model Router (§4.7) | ✅ |
| FR-17 | Langfuse Tracer (§4.5) + GET /health | ✅ |

All 17 FRs covered. All 3 endpoints specified. All 4 entities mapped to DB tables in DB_DESIGN.md.

---

## Next Step

→ Run `/plan @docs/` to generate implementation tasks with full traceability

# System Architecture — Pro Agent

**Version:** 1.0.0 | **Date:** 2026-03-18

---

## Architecture Overview

Pro Agent follows a **layered event-driven architecture** with async message processing. The system decouples request handling (FastAPI), agent orchestration (LangGraph), memory retrieval (pgvector), and tool execution (MCP).

```mermaid
flowchart TD
    A["HTTP Layer<br/>[/chat] [/webhook] [/health]"] -->|FastAPI| B["Authentication<br/>Bearer Token"]
    B -->|Verify| C["Request Routing<br/>ChatRequest / WebhookReq"]
    C -->|Route| D["Agent Pipeline<br/>_run_agent"]
    D -->|1. Load Identity| E["Identity Loader<br/>SOUL.md + agent.yaml"]
    D -->|2. Retrieve Memory| F["Memory Retriever<br/>pgvector"]
    D -->|3. Build Prompt| G["System Prompt<br/>Builder"]
    D -->|4. Invoke Agent| H["LangGraph Agent<br/>LLM + Tools"]
    D -->|5. Store Results| I["Output Validator<br/>& Memory Store"]
    D -->|6. Return| J["HTTP Response<br/>JSON"]
    E -->|Cache| K["Configuration<br/>System"]
    F -->|Query| L["PostgreSQL<br/>pgvector + pgai"]
    H -->|Execute| M["MCP Tool Executor<br/>web_search, github, file_io"]
    I -->|Trace| N["Langfuse<br/>optional"]
    M -->|Log| L
    I -->|Persist| L
    style A fill:#e1f5ff
    style D fill:#fff3e0
    style L fill:#f3e5f5


---

## Component Architecture

### 1. HTTP Layer (main.py)

**Responsibility:** Receive HTTP requests, route to business logic, return responses.

**Components:**
- FastAPI app instance with lifespan management
- Three endpoints: /chat, /webhook, /health
- Auth middleware (bearer token)
- Request validation (Pydantic)

**Key Features:**
- Graceful startup/shutdown (DB pool, Langfuse initialization)
- Error handling with appropriate HTTP status codes
- Fire-and-forget memory storage (doesn't block response)

**Request Flow:**
```
HTTP Request
  ↓ (FastAPI routing)
/chat or /webhook handler
  ↓ (auth check, validation)
_run_agent() shared pipeline
  ↓ (response building)
HTTP Response (JSON)
```

---

### 2. Authentication & Authorization

**Module:** `auth.py`

**Responsibility:** Verify bearer token before processing /chat and /webhook requests.

**Method:** Timing-safe HMAC comparison to prevent timing attacks.

**Code:**
```python
def verify_bearer_token(request: Request) -> None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized")

    token = auth_header[7:]
    if not hmac.compare_digest(token, settings.auth_token):
        raise HTTPException(401, "Unauthorized")
```

**Security Properties:**
- Token from AUTH_TOKEN environment variable
- No token logging
- Consistent execution time (prevents timing-based attacks)

---

### 3. Identity Loading

**Module:** `identity.py`

**Responsibility:** Load agent personality from SOUL.md (markdown) and agent.yaml (structured config).

**Files:**
- `SOUL.md` — Behavioral rules (human-editable)
- `agent.yaml` — Configuration (machine-readable)

**Processing:**
1. Parse SOUL.md as markdown
2. Parse agent.yaml as YAML
3. Combine: `"{role}\n\n{SOUL.md}\n\nStyle: {style}"`
4. Cache in memory (LRU)
5. Inject into LLM system prompt

**Fallback:** If files missing, use internal defaults

**Example Output:**
```
Pro Agent
A versatile assistant with persistent memory and tool access

Be helpful, honest, and concise.
Admit uncertainty rather than guessing.
...

Style: Concise, technical, slightly witty
```

---

### 4. Agent Orchestration (LangGraph)

**Modules:** `agent/state.py`, `agent/nodes.py`, `agent/graph.py`

**Responsibility:** Define and execute agent loop with LLM and tool routing.

**Architecture:**

```mermaid
stateDiagram-v2
    [*] --> agent_node
    agent_node --> tools_condition{Tool calls?}
    tools_condition -->|Yes| tools_node
    tools_node --> agent_node
    tools_condition -->|No| [*]
```

**AgentState Structure:**
- `messages: list[BaseMessage]` — Conversation history
- `system_prompt: str` — Combined identity + memory
- `sender: str` — User identifier
- `tool_call_count: int` — Calls executed this turn

**Agent Node:**
- Invokes LiteLLM with accumulated messages
- Builds LiteLLM model string as `{provider}/{model}` (e.g. `deepseek/deepseek-chat`)
- Generates response or tool calls
- **DeepSeek R1 Support:** Detects `reasoning_content` field and wraps in `<think>...</think>` blocks

**Tool Node:**
- Intercepts tool_call messages
- Executes tools via MCP adapters
- Returns tool results to agent loop
- Respects tool call limit per turn (configurable, default 5)

**Checkpointing:**
- MemorySaver in-memory for development
- Thread-based conversation history per session_id
- Enables multi-turn conversations

---

### 5. Memory System

**Modules:** `memory/embeddings.py`, `memory/retriever.py`, `memory/store.py`

**Two-Tier Memory:**

#### Tier 1: Conversation Turn Embeddings

**Table:** `conversation_turns` (1536-dim vectors via pgvector)

**Retrieval:**
```
User message
  ↓ (generate embedding via LiteLLM)
Embedding vector
  ↓ (pgvector similarity search: 1 - (embedding <=> query) > threshold)
Top-k relevant past turns
  ↓ (format as context)
"Relevant past conversations:\n- Turn 1\n- Turn 2..."
```

**Query:** Semantic search with configurable threshold (default 0.7)

#### Tier 2: User Facts

**Table:** `user_facts` (same 1536-dim vectors)

**Extraction:** LLM-based (deferred to Tier 3)

**Retrieval:**
```
Relevant user facts
  ↓ (pgvector similarity search)
Top-k matching facts
  ↓ (format as context)
"Known about this user:\n- Prefers Python\n- Works at XYZ..."
```

**Context Injection:**
Both tiers are combined and injected into the system prompt before LLM invocation:

```
System Prompt (from SOUL.md + agent.yaml)
+ Relevant Past Conversations
+ Known About This User
= Final System Prompt
```

---

### 6. Tool Execution (MCP)

**Modules:** `tools/registry.py`, `tools/guardrails.py`, `tools/logger.py`

**Architecture:**

```mermaid
flowchart TD
    A["Agent Node<br/>tool_call message"] --> B["Guardrails Check<br/>max_calls, timeout"]
    B -->|Pass| C["Execute Tool<br/>web_search, github,<br/>file_io"]
    B -->|Fail| D["Inject Error<br/>No tools"]
    C -->|Success| E["Log to<br/>tool_call_logs"]
    C -->|Error| E
    E --> F["Return Result<br/>to Agent"]
    D --> F
    F --> G["Agent Loop<br/>or Exit"]
    style B fill:#ffebee
    style C fill:#e8f5e9


**Guardrails:**
- `max_calls_per_turn`: 5 (default, configurable)
- `timeout_seconds`: 30 per call (configurable)
- If exceeded: Inject error message, agent responds without tools

**Tool Registry:**
```python
# tools/registry.py
_tools = [
    _build_web_search_tool(),   # DuckDuckGo
    _build_github_tool(),        # GitHub (if GITHUB_TOKEN set)
    _build_file_io_tool(),       # Sandboxed file ops
]

def get_registered_tools():
    return [t for t in _tools if t is not None]
```

**Error Handling:**
- If tool fails: Return error message to agent
- Agent can choose to retry or explain error to user
- Never blocks response

---

### 7. Database Layer

**Module:** `db/pool.py`

**Architecture:**

```
Connection Pool (psycopg AsyncConnectionPool)
  ├── 10 connections (configurable)
  ├── Auto-recycling
  └── Async context managers
```

**Tables:**

| Table | Purpose | Rows | Columns |
|-------|---------|------|---------|
| `sessions` | Conversation grouping | 100s–1000s | id, user_id, thread_id (UK), metadata, timestamps |
| `conversation_turns` | Message storage with embeddings | 10k–100k+ | id, session_id (FK), user_id, role, content, embedding (1536-dim), timestamps |
| `user_facts` | Persistent user knowledge | 100s–1000s | id, user_id, fact, embedding (1536-dim), source, timestamps |
| `tool_call_logs` | Tool execution audit | 1k–10k+ | id, turn_id (FK), tool_name, parameters (JSON), result (JSON), success, duration_ms, cost |

**Indexes:**
- `idx_turns_user_id` — Fast lookup by user
- `idx_turns_embedding` — HNSW vector index on embedding column (cosine distance)
- `idx_facts_embedding` — HNSW vector index on embedding column (cosine distance)
- `idx_sessions_last_active` — Recent sessions
- `idx_tool_logs_created_at` — Time-based queries

**Vector Extension:**
- `pgvector` — 1536-dim vector type
- `pgai` — Embedding generation helpers
- `uuid-ossp` — UUID generation

---

### 8. Configuration System

**Module:** `config.py`

**Pattern:** Pydantic BaseSettings with environment variable support

**Priority:**
1. Environment variables (highest)
2. `.env` file
3. Pydantic defaults (lowest)

**Key Settings:**

| Category | Variables |
|----------|-----------|
| **LLM** | provider, model, api_key, base_url, temperature, max_tokens |
| | *Note: LiteLLM combines as `{provider}/{model}` for routing (e.g. `deepseek/deepseek-chat`)* |
| **Embedding** | model, api_key, api_base (configurable at runtime) |
| **Database** | postgres_url |
| **Memory** | top_k_turns, top_k_facts, similarity_threshold |
| **Tools** | max_calls_per_turn, timeout_seconds, github_token, search_api_key |
| **Security** | auth_token |
| **Observability** | langfuse_public_key, langfuse_secret_key |
| **Infrastructure** | port, file_io_sandbox_dir |

---

### 9. Output Validation

**Module:** `output/`

**Schemas:** Pydantic models for structured outputs

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

**Validation Flow:**
1. LLM generates response
2. Parse as JSON
3. Validate against schema
4. If validation fails → fallback to raw text
5. Log success/failure to Langfuse

**Key Property:** Never blocks response. Validation failure gracefully degrades.

---

### 10. Observability (Langfuse)

**Module:** `observability/langfuse.py`

**Optional Integration:** If LANGFUSE_PUBLIC_KEY not set, tracing is disabled.

**Trace Structure:**

```
Trace: "chat-{request_id}"
  ├── Span: "memory_retrieval"
  │     ├── input: message embedding
  │     ├── output: top-k turns + facts
  │     └── duration_ms
  │
  ├── Span: "llm_call"
  │     ├── model: "deepseek-chat"
  │     ├── tokens_in: N
  │     ├── tokens_out: M
  │     ├── cost: $X.XX
  │     └── duration_ms
  │
  ├── Span: "tool_call" (0..N)
  │     ├── tool: "web_search"
  │     ├── parameters: {...}
  │     ├── result: "..."
  │     ├── success: true/false
  │     └── duration_ms
  │
  └── Span: "memory_store"
        ├── turns_stored: 2
        ├── facts_extracted: 1
        └── duration_ms
```

**Cost Tracking:**
- LLM cost from LiteLLM
- Tool costs from tool_call_logs
- Per-request total = LLM + tools
- Aggregated in /health response

---

## Data Flow — Complete Request Lifecycle

### Request: POST /chat

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant Auth
    participant Agent as Agent Pipeline
    participant LLM as LiteLLM<br/>LangGraph
    participant DB as PostgreSQL
    participant Langfuse

    Client->>FastAPI: POST /chat
    FastAPI->>Auth: Verify Bearer Token
    Auth-->>FastAPI: ✓ Valid
    FastAPI->>Agent: Load identity, retrieve memory
    Agent->>DB: Query pgvector for turns
    Agent->>DB: Query user_facts by similarity
    DB-->>Agent: Top-k turns + facts
    Agent->>LLM: Invoke with system prompt
    LLM-->>Agent: Response or tool_calls
    alt Tool Calls
        Agent->>Agent: Execute tools (guardrails check)
        Agent->>DB: Log to tool_call_logs
        Agent->>LLM: Return tool results to agent
    end
    Agent->>Agent: Validate output
    Agent->>DB: Store turns + embeddings
    Agent->>Langfuse: Log spans (optional)
    Agent-->>FastAPI: ChatResponse
    FastAPI-->>Client: 200 OK + JSON
```

### Request: POST /webhook (Typebot/n8n)

**Differences from /chat:**
1. Input extraction: Typebot schema → normalized fields
2. Skip check: If sender_is_agent=true, return skipped response
3. Output: Simple response without tool_calls field
4. Otherwise: Same pipeline as /chat

### Request: GET /health

```mermaid
flowchart TD
    A["GET /health<br/>no auth required"] --> B["Compute Uptime<br/>seconds since start"]
    B --> C["Query PostgreSQL<br/>pg_class.reltuples for<br/>turn/session/fact counts"]
    C --> D["Test DB<br/>connectivity"]
    D --> E["Get Tools<br/>get_registered_tools"]
    E --> F["Aggregate Costs<br/>from tool_call_logs"]
    F --> G["Build HealthResponse"]
    G --> H["Return 200 OK"]
    style A fill:#e3f2fd
    style H fill:#c8e6c9

**Implementation Note:** Memory stats use `pg_class.reltuples` for fast estimation of row counts without full table scans. This provides near-instant responses even with large datasets.

---

## Deployment Architecture

### Docker Compose

```yaml
version: "3.9"
services:
  pro-agent:
    image: pro-agent:1.0.0
    ports:
      - "8000:8000"
    environment:
      - AUTH_TOKEN=${AUTH_TOKEN}
      - LLM_PROVIDER=deepseek
      - LLM_MODEL=deepseek-chat
      - LLM_API_KEY=${LLM_API_KEY}
      - POSTGRES_URL=postgresql://agent:agent@postgres:5432/pro_agent
    volumes:
      - ./SOUL.md:/app/SOUL.md
      - ./agent.yaml:/app/agent.yaml
      - ./sandbox:/app/sandbox
    depends_on:
      - postgres
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  postgres:
    image: timescale/timescaledb-ha:pg17
    environment:
      - POSTGRES_USER=agent
      - POSTGRES_PASSWORD=agent
      - POSTGRES_DB=pro_agent
    volumes:
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

### Container Topology

```mermaid
graph TD
    A["Client / Load Balancer<br/>HTTP Requests"] -->|:8000| B["pro-agent<br/>FastAPI<br/>LangGraph"]
    B -->|psycopg<br/>:5432| C["PostgreSQL 17<br/>pgvector<br/>pgai<br/>uuid-ossp"]
    B -->|env: LLM_PROVIDER<br/>LLM_MODEL| D["LLM Endpoint<br/>DeepSeek, OpenAI,<br/>OpenRouter, etc."]
    B -.->|LANGFUSE_KEY| E["Langfuse<br/>optional tracing"]
    C -->|embeddings| C
    style B fill:#fff9c4
    style C fill:#e1f5fe
    style D fill:#f3e5f5
    style E fill:#f0f4c3


---

## Scaling Considerations (Future)

### Horizontal Scaling (Tier 3/4)

**Load Balancer** (nginx, HAProxy)
- Routes /chat, /webhook requests to multiple agent instances
- Health check: GET /health
- Session affinity: Optional (agent instances are stateless)

**Database Scaling:**
- Replication for read queries (memory retrieval)
- Write scaling: Partition tool_call_logs by tool_name or date
- Vector index optimization: HNSW (vs IVFFlat) for larger datasets

**Caching Layer (Redis):**
- Cache embeddings to avoid regeneration
- Cache tool results (e.g., GitHub issue queries)
- Cache identity (SOUL.md + agent.yaml)

---

## Failure Modes & Mitigation

| Failure | Impact | Mitigation |
|---------|--------|-----------|
| PostgreSQL down | Memory unavailable | Graceful degradation: agent works with in-context only |
| Embedding API fails | No memory retrieval | Store turns without embedding, skip retrieval |
| LLM API fails | Agent can't respond | Return 500 error (acceptable) |
| Tool execution timeout | Tool result delayed | Configurable timeout (default 30s), return error |
| Auth token leak | Unauthorized access | Timing-safe comparison, rotate token |
| Memory storage fails | Turns not persisted | Log warning, continue (fire-and-forget) |

---

## Performance Characteristics

### Latency Breakdown (POST /chat)

| Component | Median | P99 |
|-----------|--------|-----|
| FastAPI routing | 1ms | 5ms |
| Auth check | 0.5ms | 1ms |
| Identity load (cached) | 0.1ms | 0.2ms |
| Embedding generation | 150ms | 300ms |
| pgvector search | 45ms | 100ms |
| LLM call | 800ms | 2500ms |
| Tool execution (if used) | 500–5000ms | varies |
| Output validation | 5ms | 20ms |
| Memory storage | 50ms | 200ms |
| Langfuse tracing | 10ms | 50ms |
| **Total (no tools)** | **1.5s** | **3.5s** |
| **Total (with tools)** | **2.5s** | **8.5s** |

### Resource Usage

| Metric | Value |
|--------|-------|
| Python process baseline | 200MB |
| PostgreSQL baseline | 500MB |
| Per-connection | 10MB |
| Per conversation turn | 1–2KB |
| Per user fact | 1KB |
| Per tool call log | 500B–2KB |

---

## Monitoring & Observability

### Metrics to Track

- Request latency (p50, p99)
- Error rate by endpoint
- Tool success rate
- Memory size (turns, facts, sessions)
- Database query time
- Token usage (per model)
- Cost (daily, per request)

### Logs to Collect

- Request logs: endpoint, sender, session, timestamp
- Error logs: exception, trace
- Degradation logs: memory unavailable, tool timeout
- Cost logs: LLM cost, tool cost, total

### Health Checks

- GET /health (1s timeout)
- Database connectivity
- LLM API availability
- Tool availability

---

## Document Metadata

- **Created:** 2026-03-18
- **Last Updated:** 2026-03-18
- **Applies to Version:** 1.0.0+
- **Audience:** Architects, DevOps, Senior Developers

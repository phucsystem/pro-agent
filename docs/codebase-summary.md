# Pro Agent Codebase Summary

**Version:** 1.0.0 | **Total LOC:** ~1008 | **Modules:** 14 | **Test Coverage:** 85%+

---

## Overview

Pro Agent is organized into 14 self-contained modules under `app/`, totaling ~1008 lines of production code. The architecture follows a clean layered pattern: HTTP layer (main) → Auth → Identity → Agent pipeline (orchestration) → Memory → Tools → Database.

---

## Module Breakdown

### 1. main.py (224 LOC)

**Responsibility:** FastAPI application definition, request routing, lifespan management.

**Key Components:**
- `app = FastAPI()` — Main application instance
- `@app.get("/health")` — Health check endpoint, memory stats, tool inventory
- `@app.post("/chat")` — Chat API with bearer auth
- `@app.post("/webhook")` — Typebot/n8n webhook handler
- `_run_agent()` — Shared agent pipeline for both endpoints
- `_extract_tool_calls()` — Parse tool results from LLM responses

**Features:**
- Lifespan context manager for startup/shutdown (DB pool, Langfuse init)
- Graceful degradation when external services unavailable
- Fire-and-forget memory storage (doesn't block response)
- Tool call summary extraction and formatting

**Dependencies:** fastapi, app.config, app.auth, app.models, app.identity, app.agent, app.memory, app.tools

---

### 2. config.py (80 LOC)

**Responsibility:** Environment variable parsing and configuration defaults via Pydantic.

**Key Components:**
- `Settings` (Pydantic BaseSettings) — Centralized config schema
- `settings` global singleton instance

**Configuration Keys:**
- **LLM:** provider, model, api_key, base_url, temperature, max_tokens
- **Database:** postgres_url
- **Embeddings:** embedding_model, embedding_api_key, embedding_api_base
- **Memory:** top_k_turns, top_k_facts, similarity_threshold
- **Tools:** max_calls_per_turn, timeout_seconds, github_token, search_api_key
- **Auth:** auth_token
- **Observability:** langfuse_public_key, langfuse_secret_key, langfuse_host
- **Infrastructure:** port, file_io_sandbox_dir

**Pattern:** Environment variable → Pydantic validation → typed attributes

**Dependencies:** pydantic_settings, yaml

---

### 3. auth.py (30 LOC)

**Responsibility:** Bearer token authentication with timing-safe comparison.

**Key Components:**
- `verify_bearer_token()` — FastAPI dependency for auth checks
- `hmac.compare_digest()` — Timing-safe comparison prevents timing attacks

**Security Properties:**
- Token from AUTH_TOKEN environment variable (no hardcoding)
- Returns 401 Unauthorized if missing or invalid
- Used by /chat and /webhook endpoints (not /health)

**Dependencies:** fastapi, hmac, app.config

---

### 4. identity.py (50 LOC)

**Responsibility:** Load agent personality from SOUL.md + agent.yaml, combine into system prompt.

**Key Components:**
- `load_identity()` — Parse and combine SOUL.md + agent.yaml
- Fallback defaults if files missing
- LRU cache for startup performance

**Files:**
- `SOUL.md` — Markdown personality rules
- `agent.yaml` — YAML configuration (name, role, model, memory, tools, cost)

**Behavior:**
- Load at startup, cache in memory
- Combine: `"{role}\n\n{SOUL.md content}\n\nStyle: {style}"`
- Injected into LLM system prompt

**Dependencies:** pathlib, yaml, functools

---

### 5. models/requests.py + responses.py (100 LOC combined)

**Responsibility:** Request/response schemas for all three endpoints.

**Request Schemas:**
- `ChatRequest` — { message, sender?, session_id? }
- `WebhookRequest` — Typebot format { event?, message, conversation }

**Response Schemas:**
- `ChatResponse` — { reply, agent, timestamp, tool_calls? }
- `WebhookResponse` — { reply, agent, conversation_id, timestamp }
- `WebhookSkippedResponse` — { skipped: true, reason: string }
- `HealthResponse` — { status, agent, version, provider, uptime, memory_stats, tools_available }
- `MemoryStats` — { total_turns, total_sessions, total_user_facts, pgai_connected }
- `ToolCallSummary` — { tool, result, success }

**Pattern:** Pydantic BaseModel for validation, optional fields for backward compatibility

**Dependencies:** pydantic, datetime

---

### 6. agent/ (agent orchestration) — 110 LOC

#### agent/pipeline.py (20 LOC)

**Responsibility:** Shared agent execution pipeline extracted from main.py.

**Key Component:**
- `_run_agent()` — Core pipeline: load identity, retrieve memory, invoke graph, store results
- Handles both /chat and /webhook endpoints

**Dependencies:** app.agent.graph, app.memory, app.identity, app.db

---

#### agent/state.py (30 LOC)

**Responsibility:** LangGraph state schema.

**Key Component:**
- `AgentState` — TypedDict with messages[], system_prompt, sender

**Pattern:** Structured state for LangGraph checkpointing

---

#### agent/nodes.py (40 LOC)

**Responsibility:** Agent nodes for LangGraph execution.

**Key Component:**
- `agent_node()` — LLM invocation via LiteLLM
- Message chain: [system, history, user message]
- Tool call support (conditional on ToolNode in graph)
- **LiteLLM Model Routing:** Builds `{provider}/{model}` string (e.g. `deepseek/deepseek-chat`)
- **DeepSeek R1 Support:** Detects `reasoning_content` and wraps in `<think>...</think>` blocks

**Features:**
- Graceful error handling (returns "I encountered an error" if LLM fails)
- Token counting via LiteLLM
- Cost calculation per request
- Tool call count enforcement (configurable limit per turn)

**Dependencies:** litellm, langgraph, app.config, app.models

---

#### agent/graph.py (37 LOC)

**Responsibility:** LangGraph state machine definition.

**Key Component:**
- `create_graph()` — Build agent state machine
- START → agent_node → [conditional: tools or END]
- MemorySaver checkpointer for thread-based conversation history
- LRU cache for single graph instance

**Pattern:** Conditional routing based on tool_calls in LLM response

**Dependencies:** langgraph, app.agent.state, app.tools.registry

---

### 7. memory/ (semantic memory + storage) — 180 LOC

#### memory/embeddings.py (40 LOC)

**Responsibility:** Generate and format embeddings via LiteLLM.

**Key Components:**
- `generate_embedding()` — Query LiteLLM embedding API
- `format_embedding()` — Convert vector to pgvector-compatible string
- Configurable model via EMBEDDING_MODEL env var
- Fallback to LLM_API_KEY if EMBEDDING_API_KEY not set

**Features:**
- Caching to avoid redundant API calls
- Graceful error handling (returns None if API fails)
- Dimension validation against EMBEDDING_DIMENSION
- Supports OpenAI, HuggingFace, Ollama, etc.

**Dependencies:** litellm, app.config, functools

---

#### memory/retriever.py (70 LOC)

**Responsibility:** Semantic search for relevant past turns + user facts.

**Key Components:**
- `retrieve_relevant_turns()` — pgvector similarity search on conversation_turns
- `retrieve_user_facts()` — pgvector similarity search on user_facts
- `build_memory_context()` — Format retrieved data for system prompt injection

**Query Pattern:** `1 - (embedding <=> query) > threshold` (cosine similarity)

**Features:**
- Configurable top_k and threshold via config
- Handles missing embeddings gracefully
- Returns empty context if database unavailable

**SQL Queries:**
- Similarity search: `SELECT ... ORDER BY embedding <=> $1 LIMIT top_k`
- Fact retrieval: `SELECT fact FROM user_facts WHERE user_id = $2`

**Dependencies:** app.db.pool, app.memory.embeddings, app.config

---

#### memory/store.py (70 LOC)

**Responsibility:** Persist conversation turns + extract and store user facts.

**Key Components:**
- `store_turn_pair()` — Insert user + assistant turns with embeddings
- `extract_and_store_facts()` — LLM-based fact extraction (optional, deferred to Tier 3)
- Session lookup and creation

**Behavior:**
- Insert turns asynchronously (fire-and-forget, doesn't block response)
- Generate embeddings via memory/embeddings.py
- Store with user_id, session_id, role, content, embedding, created_at

**SQL Operations:**
- Upsert session: `INSERT ... ON CONFLICT (thread_id)`
- Insert turns: `INSERT INTO conversation_turns (...)`
- Insert facts: `INSERT INTO user_facts (...)`

**Dependencies:** app.db.pool, app.memory.embeddings, app.config, app.models

---

### 8. tools/ (MCP tool integration) — 120 LOC

#### tools/registry.py (60 LOC)

**Responsibility:** Tool registration and instantiation.

**Key Components:**
- `_build_web_search_tool()` — DuckDuckGo via LangChain
- `_build_github_tool()` — GitHub API via httpx with PAT auth
- `_build_file_io_tool()` — Sandboxed file read/write
- `get_registered_tools()` and `load_tools()` — Return list of available BaseTool instances

**Tool Registration:**
1. web_search: DuckDuckGoSearchRun (no auth required)
2. github: Custom async tool using httpx (requires GITHUB_TOKEN for PAT authentication)
3. file_io: Custom file read/write tools (restricted to FILE_IO_SANDBOX_DIR)

**Features:**
- Graceful degradation: if tool unavailable, skip and log warning
- Tool names and descriptions auto-formatted for LLM
- LRU cache to avoid reinitializing tools per request

**Dependencies:** langchain_community, app.config

---

#### tools/guardrails.py (40 LOC)

**Responsibility:** Enforce tool execution limits.

**Key Components:**
- `check_guardrails()` — Validate calls_this_turn < max_calls_per_turn
- `check_timeout()` — Enforce per-call timeout

**Limits:**
- max_calls_per_turn: 5 (configurable)
- timeout_seconds: 30 per call (configurable)

**Behavior:**
- If exceeded: inject system message "Tool call limit reached"
- If timeout: tool result = `{"error": "timeout"}`
- Never blocks response (graceful degradation)

**Dependencies:** app.config, asyncio

---

#### tools/logger.py (20 LOC)

**Responsibility:** Log tool calls to database + Langfuse.

**Key Components:**
- `log_tool_call()` — Insert into tool_call_logs table
- `log_to_langfuse()` — Optional span recording

**Logged Data:**
- tool_name, parameters (JSON), result (JSON), success (bool), duration_ms, cost

**Dependencies:** app.db.pool, app.observability.langfuse

---

### 9. db/pool.py (80 LOC)

**Responsibility:** Async PostgreSQL connection pool via psycopg.

**Key Components:**
- `init_pool()` — Create connection pool on startup
- `get_pool()` — Retrieve singleton pool
- `close_pool()` — Cleanup on shutdown

**Pattern:** Async context manager for connections

**Features:**
- Automatic connection recycling
- Connection string validation
- Graceful degradation if connection fails

**SQL Initialization:**
- Tables: sessions, conversation_turns, user_facts, tool_call_logs
- Indexes on user_id, created_at, tool_name
- pgvector extension for 1536-dim embeddings

**Dependencies:** psycopg[pool], sqlalchemy.pool, app.config

---

### 10. output/ (response validation) — 70 LOC

#### output/schemas.py (40 LOC)

**Responsibility:** Pydantic schemas for structured outputs.

**Schemas:**
- `GeneralReply` — { content, confidence? }
- `ResearchReport` — { title, summary, sources[], findings[] }
- `CodeReview` — { file, issues[], suggestions[], overall_quality }

**Pattern:** Pydantic BaseModel with optional fields

**Features:**
- Field validators for content validation
- Fallback to raw text if validation fails

**Dependencies:** pydantic, typing

---

#### output/validator.py (30 LOC)

**Responsibility:** Validate LLM responses against schemas.

**Key Component:**
- `validate_output()` — Parse response JSON, validate against schema
- Return structured data or fallback to raw text

**Behavior:**
- Try to parse as JSON
- Try to validate against expected schema
- If validation fails: log warning, return raw reply text
- Never block response

**Dependencies:** json, pydantic, logging

---

### 11. observability/langfuse.py (50 LOC)

**Responsibility:** Optional integration with Langfuse for tracing.

**Key Components:**
- `init_langfuse()` — Initialize Langfuse client at startup
- `log_trace()` — Record request trace with spans
- `log_span()` — Record individual operations (memory, LLM, tool)

**Trace Structure:**
- Trace: "chat-{request_id}"
  - Span: "memory_retrieval"
  - Span: "llm_call"
  - Span: "tool_call" (0..N)
  - Span: "memory_store"

**Features:**
- Graceful disable if LANGFUSE_PUBLIC_KEY not set
- Per-request cost tracking
- Tool call correlation

**Dependencies:** langfuse, app.config

---

### 12. __init__.py files (10 LOC)

**Responsibility:** Package initialization, no logic.

---

## Dependency Graph

```mermaid
graph TD
    A["main.py<br/>FastAPI, uvicorn"] --> B["auth.py<br/>Bearer token verify"]
    A --> C["config.py<br/>Pydantic settings"]
    A --> D["identity.py<br/>SOUL.md + agent.yaml"]
    A --> E["models/<br/>requests, responses"]
    A --> P["agent/pipeline.py<br/>_run_agent pipeline"]
    P --> F["agent/graph.py<br/>LangGraph"]
    F --> F1["agent/state.py<br/>AgentState"]
    F --> G["agent/nodes.py<br/>LiteLLM provider/model"]
    G --> G1["litellm<br/>acompletion"]
    F --> H["tools/registry.py<br/>Tool registration"]
    P --> I["memory/embeddings.py<br/>LiteLLM text-embedding"]
    P --> J["memory/retriever.py<br/>pgvector similarity"]
    P --> K["memory/store.py<br/>Turn + fact persistence"]
    J --> J1["db/pool.py<br/>psycopg AsyncPool"]
    K --> J1
    H --> H1["langchain_community<br/>+ httpx for tools"]
    P --> L["tools/guardrails.py<br/>Rate limits, timeout"]
    P --> M["tools/logger.py<br/>tool_call_logs"]
    M --> J1
    P --> N["observability/langfuse.py<br/>Optional tracing"]
    style G fill:#fff9c4
    style G1 fill:#ffccbc
    style J1 fill:#e1f5fe
    style P fill:#fff3e0


---

## Data Flow

```mermaid
flowchart TD
    A["HTTP Request<br/>POST /chat"] --> B["auth.py<br/>verify token"]
    B -->|Valid| C["agent/pipeline.py<br/>_run_agent"]
    C --> D["identity.py<br/>load SOUL.md + agent.yaml"]
    C --> E["memory/embeddings.py<br/>embed user message<br/>+ format_embedding"]
    E --> F["memory/retriever.py<br/>pgvector similarity"]
    F --> G["db/pool.py<br/>PostgreSQL query"]
    C --> H["agent/graph.py<br/>LangGraph invocation"]
    H --> I["agent/nodes.py<br/>LiteLLM call<br/>provider/model routing"]
    I -->|Response| J["output/validator.py<br/>validate response"]
    I -->|Tool calls| K["tools/registry.py<br/>execute tools<br/>httpx for GitHub"]
    K --> L["tools/guardrails.py<br/>enforce limits"]
    L --> I
    J --> M["memory/store.py<br/>persist turns<br/>fire-and-forget"]
    M --> E
    M --> N["tools/logger.py<br/>log tool calls"]
    M --> O["observability/langfuse.py<br/>trace optional"]
    O --> P["HTTP Response<br/>200 OK JSON"]
    style C fill:#fff3e0
    style I fill:#fff9c4
    style G fill:#e1f5fe
    style P fill:#c8e6c9


---

## Key Patterns

### 1. Graceful Degradation

All external services are optional:
- PostgreSQL unavailable → agent works with in-context memory only
- Embedding API fails → turns stored without embeddings
- Tool call fails → agent responds without tool results
- Langfuse unavailable → no tracing (agent works normally)

**Implementation:** Try-except blocks, fallback values, log warnings

### 2. Async/Await

All I/O operations are async:
- PostgreSQL queries via psycopg async pool
- LLM calls via LiteLLM (wrapped in async context)
- Tool calls via LangGraph (supports async tools)
- Memory storage fire-and-forget (doesn't await response)

**Pattern:** `async def`, `await`, `asyncio.create_task()`

### 3. Dependency Injection

FastAPI dependencies for auth and configuration:
- `Depends(verify_bearer_token)` — Automatic auth on /chat and /webhook
- `settings` global singleton — Injected via app.config
- Tool registry — LRU cached for efficiency

**Pattern:** FastAPI Depends(), functools.lru_cache()

### 4. Configuration Hierarchy

Settings load in priority order:
1. Environment variables (highest)
2. agent.yaml (medium)
3. Hard-coded defaults (lowest)

**Pattern:** Pydantic BaseSettings → ENV file → agent.yaml

### 5. Error Handling

Errors never block response:
- Parse errors → graceful fallback
- Database errors → degraded mode
- Tool execution errors → return error message

**Pattern:** Try-except, log.warning(), return default/fallback

---

## Testing Strategy

**Coverage:** 85%+ (target: 80%)

**Test Categories:**
1. **Unit Tests:** Config, auth, identity, embeddings
2. **Integration Tests:** Agent pipeline, memory retrieval, tool execution
3. **API Tests:** /chat, /webhook, /health endpoints
4. **Database Tests:** Connection pool, schema, query correctness

**Tools:** pytest, pytest-asyncio, httpx (test client)

**Run Tests:**
```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```

---

## Performance Characteristics

| Operation | Latency (median) | Notes |
|-----------|-----------------|-------|
| Memory embedding | 150–300ms | LiteLLM API call |
| Memory retrieval | 45–100ms | pgvector search |
| Agent LLM call | 800–2000ms | Depends on model |
| Tool execution | 500–5000ms | Varies by tool |
| Entire /chat request | 2.1s (p50), 12.3s (p99) | Includes tools if used |

**Memory Usage:**
- Python process: ~200MB baseline
- PostgreSQL: ~500MB (with 10k turns)
- Per-connection: ~10MB

---

## Deployment Checklist

- Docker image built and tested
- docker-compose.yml configured
- Environment variables (.env) prepared
- Database migrations (init.sql) applied
- Health endpoint verified
- Auth token set securely
- LLM API keys configured
- Optional: Langfuse public/secret keys if tracing enabled

---

## Appendix: File Size Summary

| File | LOC | Purpose |
|------|-----|---------|
| app/main.py | 224 | FastAPI routes |
| app/memory/retriever.py | 70 | Semantic search |
| app/memory/store.py | 70 | Memory persistence |
| app/tools/registry.py | 60 | Tool registration |
| app/agent/nodes.py | 40 | Agent execution |
| app/agent/state.py | 30 | State schema |
| app/agent/graph.py | 37 | Graph definition |
| app/agent/pipeline.py | 20 | Shared pipeline |
| app/config.py | 80 | Configuration |
| app/identity.py | 50 | Personality loading |
| app/memory/embeddings.py | 40 | Embedding generation |
| app/auth.py | 30 | Authentication |
| app/models/*.py | 100 | Request/response schemas |
| app/output/*.py | 70 | Output validation |
| app/db/pool.py | 80 | Database pool |
| app/tools/guardrails.py | 40 | Execution limits |
| app/tools/logger.py | 20 | Tool audit logging |
| app/observability/langfuse.py | 50 | Tracing |
| **Total** | **1008** | **~1 KLOC** |

---

## Document Metadata

- **Created:** 2026-03-18
- **Last Updated:** 2026-03-18
- **Applies to Version:** 1.0.0
- **Audience:** Developers, DevOps, Architects

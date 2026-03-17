# System Requirement Definition (SRD)

## 1. System Overview

**Project:** Pro Agent (Tier 2)
**Version:** 1.0.0
**Context:** Second prototype in the agent4startup tier ladder. Adds long-term memory (pgai) and tool use (MCP) on top of the Dumb Agent's identity + short-term memory baseline. Must be a drop-in replacement for the Dumb Agent — same API contract, same integrations (Typebot, n8n), same Docker deployment pattern.

**Goals:**
- Validate that semantic memory retrieval improves agent response quality
- Validate that MCP tool use is reliable (>90% success rate)
- Maintain full backward compatibility with Dumb Agent API consumers
- Establish patterns reusable by Tier 3 (Pro Max) and domain agents

**Stack:** Python · FastAPI · LangGraph · PostgreSQL + pgai · LiteLLM · Langfuse · Docker

---

## 2. Actors (User Roles)

| ID | Actor | Description |
|----|-------|-------------|
| A-01 | **API Consumer** | External client calling POST /chat directly (scripts, apps, other agents) |
| A-02 | **Chatbot Platform** | Typebot, n8n, or similar webhook-based platform calling POST /webhook |
| A-03 | **Agent Developer** | Configures identity (SOUL.md, agent.yaml), deploys, monitors via Langfuse |
| A-04 | **Orchestrator Agent** | Future Tier 4 agent that delegates tasks to Pro Agent via API |

---

## 3. Functional Requirements (FR-xx)

### Phase 1 — Core + Memory (P1)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| FR-01 | Identity Loading | P1 | Load agent personality from `SOUL.md` (behavioral rules) + `agent.yaml` (name, role, style, model config). Fallback to defaults if files missing. Hot-reload not required — load at startup. |
| FR-02 | Chat Endpoint | P1 | `POST /chat` accepts `{ message, sender, session_id? }`, returns `{ reply, agent, timestamp }`. Backward-compatible with Dumb Agent contract. Optional `session_id` defaults to `"default"`. |
| FR-03 | Webhook Endpoint | P1 | `POST /webhook` accepts Typebot/n8n payload `{ event, message: { content, sender_name, sender_id, sender_is_agent, conversation_id }, conversation: { id } }`. Returns `{ reply, agent, conversation_id, timestamp }`. Skips messages where `sender_is_agent=true`. |
| FR-04 | Health Endpoint | P1 | `GET /health` returns `{ status, agent, provider, uptime, memory_stats, tools_available }`. No auth required. |
| FR-05 | Bearer Token Auth | P1 | All endpoints except `/health` require `Authorization: Bearer <token>`. Timing-safe comparison. Reject with 401 if missing/invalid. |
| FR-06 | Long-Term Memory | P1 | Store every conversation turn as an embedding in pgai. On each new message, retrieve top-k (default 10) semantically similar past turns. Inject retrieved context into system prompt. |
| FR-07 | User Facts Memory | P1 | Store and retrieve per-user facts (extracted from conversations). Upgrade Dumb Agent's InMemoryStore to pgai-backed persistent storage. |
| FR-08 | Session Management | P1 | Track conversations by `session_id` (from /chat) or `conversation_id` (from /webhook). Each session maintains its own LangGraph thread. Sessions isolated per user. |

### Phase 2 — Tool Use (P2)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| FR-09 | MCP Tool Integration | P2 | Integrate MCP tool layer via `langchain-mcp-adapters`. Agent can invoke external tools during response generation. Tool results injected back into the agent loop. |
| FR-10 | Web Search Tool | P2 | Agent can search the web for real-time information. Uses MCP web search provider. |
| FR-11 | GitHub Tool | P2 | Agent can read repositories, list issues, create issues via GitHub MCP server. |
| FR-12 | File I/O Tool | P2 | Agent can read/write local files within a sandboxed directory. |
| FR-13 | Tool Call Guardrails | P2 | Max tool calls per turn (default 5, configurable). Timeout per tool call (default 30s). If limits exceeded, agent returns partial response with warning. |
| FR-14 | Tool Call Logging | P2 | Every tool invocation logged to Langfuse: tool name, parameters, result, duration, success/failure. Linked to the parent conversation trace. |

### Phase 3 — Structured Output + Routing (P3)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| FR-15 | Structured Output | P3 | Define Pydantic output schemas for common response types (general reply, research report, code review). Agent's raw output validated against schema. Fallback to raw text if validation fails. |
| FR-16 | Multi-Model Routing | P3 | LiteLLM routes requests to different models based on configuration: Claude, GPT, DeepSeek, Ollama. Model selected via `agent.yaml` config or per-request override. |
| FR-17 | Cost Tracking | P3 | Track tokens in/out per request. Calculate cost based on model pricing. Log per-request cost to Langfuse. Expose aggregate stats via `/health`. |

---

## 4. Endpoint List (S-xx)

| ID | Endpoint | Method | Auth | Description |
|----|----------|--------|------|-------------|
| S-01 | `/chat` | POST | Bearer | Direct conversation API — primary integration point |
| S-02 | `/webhook` | POST | Bearer | Chatbot platform webhook (Typebot, n8n) |
| S-03 | `/health` | GET | None | Status, uptime, memory stats, available tools |

---

## 5. Entity List (E-xx)

| ID | Entity | Description | Key Fields |
|----|--------|-------------|------------|
| E-01 | **ConversationTurn** | Single message in a conversation | `id` (UUID), `session_id`, `user_id`, `role` (user/assistant/tool), `content` (text), `embedding` (vector), `created_at` (timestamp) |
| E-02 | **Session** | Conversation session grouping turns | `id` (UUID), `user_id`, `agent_id`, `thread_id` (LangGraph), `created_at`, `last_active_at`, `metadata` (JSON) |
| E-03 | **UserFact** | Persistent fact about a user | `id` (UUID), `user_id`, `fact` (text), `embedding` (vector), `source` (chat/tool), `created_at` |
| E-04 | **ToolCallLog** | Record of a tool invocation | `id` (UUID), `turn_id` (FK→E-01), `tool_name`, `parameters` (JSON), `result` (JSON), `success` (bool), `duration_ms` (int), `cost` (decimal), `created_at` |

---

## 6. Non-Functional Requirements

### NFR-01: Performance
- Response latency < 5s for non-tool tasks
- Response latency < 15s for tasks with tool calls
- pgai semantic search < 200ms on 10k+ stored turns
- Health endpoint < 50ms

### NFR-02: Reliability
- Tool call success rate > 90%
- Structured output schema validation > 95%
- Graceful degradation: if pgai unavailable, agent works with in-context memory only
- If tool call fails, agent responds without tool results (not a 500)

### NFR-03: Cost
- Average cost per medium task < $0.50
- Cost tracking accurate to ±5%
- Hard cost cap per request (configurable, default $1.00)

### NFR-04: Security
- Bearer token auth with timing-safe comparison
- Tool calls sandboxed (file I/O restricted to configured directory)
- No secrets in logs or API responses
- pgai credentials via environment variables only

### NFR-05: Observability
- Every request traced in Langfuse (conversation + tool calls)
- Health endpoint exposes: uptime, turn count, session count, tool stats
- Structured logging (JSON) to stdout

### NFR-06: Deployment
- Single `docker-compose up` brings up agent + PostgreSQL
- Configuration via `.env` file (same pattern as Dumb Agent)
- Volume mounts for `SOUL.md` and `agent.yaml`
- PostgreSQL data persisted via Docker volume

### NFR-07: Backward Compatibility
- All Dumb Agent API consumers work without changes
- `/chat` request/response contract is a superset (new fields optional)
- `/webhook` contract identical to Dumb Agent
- Same environment variable names where applicable

---

## 7. Key Decisions (D-xx)

| ID | Decision | Chosen | Rationale |
|----|----------|--------|-----------|
| D-01 | Language | Python | LangChain/CrewAI ecosystem, ML libs, Tier 3 alignment |
| D-02 | Web Framework | FastAPI | Async, auto-docs, Pydantic native |
| D-03 | Agent Framework | LangGraph (Python) | Same pattern as Dumb Agent (LangGraph.js), state machine with checkpointing |
| D-04 | Memory Store | PostgreSQL + pgai | Single DB for structured data + vector search, pgai handles embeddings |
| D-05 | Tool Protocol | MCP via langchain-mcp-adapters | Standard protocol, reusable across tiers |
| D-06 | Model Access | LiteLLM | Unified API for Claude/GPT/DeepSeek/Ollama, built-in cost tracking |
| D-07 | Observability | Langfuse | Open-source, LLM-native tracing, LangChain integration |
| D-08 | Identity Format | SOUL.md + agent.yaml | SOUL.md for personality (markdown, human-editable), agent.yaml for config (structured, machine-readable) |

---

## 8. Traceability Matrix

| FR | Endpoint | Entity | Decision | Phase |
|----|----------|--------|----------|-------|
| FR-01 | — | — | D-08 | 1 |
| FR-02 | S-01 | E-01, E-02 | D-02 | 1 |
| FR-03 | S-02 | E-01, E-02 | D-02 | 1 |
| FR-04 | S-03 | — | D-02 | 1 |
| FR-05 | S-01, S-02 | — | D-02 | 1 |
| FR-06 | S-01, S-02 | E-01 | D-04 | 1 |
| FR-07 | S-01, S-02 | E-03 | D-04 | 1 |
| FR-08 | S-01, S-02 | E-02 | D-03 | 1 |
| FR-09 | S-01, S-02 | E-04 | D-05 | 2 |
| FR-10 | S-01, S-02 | E-04 | D-05 | 2 |
| FR-11 | S-01, S-02 | E-04 | D-05 | 2 |
| FR-12 | S-01, S-02 | E-04 | D-05 | 2 |
| FR-13 | S-01, S-02 | E-04 | D-05 | 2 |
| FR-14 | S-01, S-02 | E-04 | D-07 | 2 |
| FR-15 | S-01, S-02 | — | D-02 | 3 |
| FR-16 | S-01, S-02 | — | D-06 | 3 |
| FR-17 | S-03 | E-04 | D-06, D-07 | 3 |

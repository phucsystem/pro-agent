# Lean MVP Analysis: Pro Agent (Tier 2)

## Problem Statement

The Dumb Agent (Tier 1) proves identity + short-term memory + LLM works, but lacks persistent context and external tool use — two capabilities required for any useful production agent. The Pro Agent bridges this gap: an agent that **remembers across sessions** and **acts on the world via tools**, while validating that these capabilities actually improve output quality before investing in the heavier Tier 3 (RAG, graph, self-optimisation).

Critical middle tier in the agent4startup prototype ladder. If long-term memory and tool use don't reliably improve output, no point building Tier 3.

## Target Users (→ IPA User Roles)

| User Type | Description | Primary Need |
|-----------|-------------|--------------|
| **Agent Developer (you)** | Building the agent4startup platform | Validate memory + tool patterns before domain agents |
| **Orchestrator Agent** | Future manager agent that delegates to Pro Agents | Reliable API contract, structured output, tool execution |
| **End User (via API)** | Future clients who "hire" agents | Agent that remembers context and can take actions |

## Dumb Agent Integration Parity

The Pro Agent MUST support all Dumb Agent integration patterns as a drop-in upgrade:

### Inherited from Dumb Agent (a-dumb-agent v2.0.0)

| Integration | Dumb Agent Implementation | Pro Agent Must Match |
|-------------|--------------------------|----------------------|
| **POST /chat** | `{ message, sender }` → `{ reply, agent, timestamp }` | Same contract + add optional `session_id`, `tool_calls` in response |
| **POST /webhook** | Chatbot platform webhook (Typebot/n8n): `{ event, message: { content, sender_name, sender_id, sender_is_agent, conversation_id }, conversation: { id } }` → `{ reply, agent, conversation_id, timestamp }`. Skips `sender_is_agent=true`. | Identical webhook contract — zero changes for existing integrations |
| **GET /health** | `{ status, agent, provider, uptime, langgraph }` | Same + add `memory_stats`, `tools_available` fields |
| **Bearer token auth** | `Authorization: Bearer <token>` on all endpoints except /health | Identical auth middleware |
| **Identity system** | `soul.md` + `identity.md` loaded at startup, injected as system prompt | Port to `SOUL.md` + `agent.yaml` (superset) |
| **User facts memory** | InMemoryStore: stores/retrieves facts per sender | Upgrade to pgai but same concept: per-user fact recall |
| **LangGraph agent loop** | StateGraph → agent node → tool node (conditional) → END | Same pattern in Python LangGraph |
| **Docker deployment** | `docker-compose.yml` with volume mounts for soul.md/identity.md | Same + add PostgreSQL service |
| **OpenAI-compatible API** | DeepSeek, OpenRouter via base_url config | Expand via LiteLLM to Claude/GPT/Ollama too |

### Key Webhook Contract (Typebot/n8n Integration)

```json
// Request (from Typebot/n8n)
{
  "event": "message_created",
  "message": {
    "content": "Hello!",
    "sender_name": "John",
    "sender_id": "user-123",
    "sender_is_agent": false,
    "conversation_id": "conv-456"
  },
  "conversation": { "id": "conv-456" }
}

// Response
{
  "reply": "Hi John! How can I help?",
  "agent": "pro-agent",
  "conversation_id": "conv-456",
  "timestamp": "2026-03-18T10:00:00.000Z"
}
```

## MVP Features (→ IPA Feature List FR-xx)

| Priority | Feature | User Value | Endpoint | Assumption |
|----------|---------|------------|----------|------------|
| P1 | Identity system (SOUL.md + YAML config) | Consistent personality across sessions | Config files | soul.md pattern from Dumb Agent transfers to Python |
| P1 | `POST /chat` + `POST /webhook` + `GET /health` API | Same contract as Dumb Agent, orchestrator + chatbot compatible | REST endpoints | API contract sufficient for integration |
| P1 | Long-term memory (pgai) | Agent recalls relevant context from weeks ago | Transparent to user | Semantic search over embeddings improves response quality |
| P1 | Conversation session management | Multi-user, multi-session support | session_id / user_id / conversation_id | Session isolation necessary for production |
| P2 | MCP tool use (web search, GitHub, file I/O) | Agent can research and act on external systems | Tool calls within chat | Tool use reliable >90% without hallucinated params |
| P2 | Tool call guardrails | Prevent infinite loops, cost blowouts | Internal limits | Max calls/turn + timeout sufficient protection |
| P2 | Tool call logging (Langfuse) | Observability, debugging, eval data | Langfuse dashboard | Tracing essential for validating tool reliability |
| P3 | Structured output (Pydantic) | Validated, parseable responses | Schema-validated JSON | Pydantic catches >95% of malformed output |
| P3 | Multi-model routing (LiteLLM) | Cost optimisation | Transparent routing | Routing meaningfully reduces cost without quality loss |
| P3 | Cost tracking per request | Budget visibility | Logged per request | Token counting × model price accurate enough |

## Implementation Phases (Estimated)

| Phase | Focus | Key Features | Effort |
|-------|-------|--------------|--------|
| 1 — Core + Memory | Identity + FastAPI + pgai memory | SOUL.md, /chat, /health, semantic recall, session mgmt | M |
| 2 — Tool Use | MCP integration + guardrails + logging | 3 tools, max-calls limit, timeout, Langfuse tracing | M |
| 3 — Structured Output + Routing | Pydantic schemas + LiteLLM + cost tracking | Output validation, multi-model, cost per request | S |

## Plan Structure Preview

```
plans/{date}-pro-agent-build/
├── plan.md
├── phase-01-core-memory/
│   ├── core.md      # FastAPI, identity, pgai memory
│   └── data.md      # PostgreSQL + pgai setup
├── phase-02-tool-use/
│   ├── core.md      # MCP integration, guardrails
│   └── tasks.md     # Tool implementations
└── phase-03-structured-output/
    ├── core.md      # Pydantic schemas, LiteLLM
    └── tasks.md     # Cost tracking, model routing
```

## Endpoints (→ IPA Screen List S-xx)

| Endpoint | Purpose | Features |
|----------|---------|----------|
| `POST /chat` | Direct API conversation | `{ message, sender, session_id? }` → `{ reply, agent, timestamp, tool_calls? }` |
| `POST /webhook` | Chatbot platform integration (Typebot/n8n) | `{ event, message, conversation }` → `{ reply, agent, conversation_id, timestamp }`. Skips agent messages. |
| `GET /health` | Status check | Uptime, memory stats, connected tools, model info |
| Config files | Identity loading | `SOUL.md` + `agent.yaml` loaded at startup |

## Data Entities (→ IPA Entity List E-xx)

| Entity | Description | Key Fields |
|--------|-------------|------------|
| **ConversationTurn** | Single message in a conversation | id, session_id, user_id, role, content, embedding, timestamp |
| **Session** | Conversation session | id, user_id, agent_id, created_at, metadata |
| **ToolCall** | Record of tool execution | id, turn_id, tool_name, params, result, duration_ms, cost, success |
| **AgentConfig** | Agent identity + settings | agent_id, soul_path, model_config, memory_config, tool_config |

## User Flow (→ IPA Screen Flow)

```
                    ┌── POST /chat (message, sender, session_id?)
Client/Platform ────┤
                    └── POST /webhook (event, message, conversation)
                              │
                              ▼
                    Parse input → normalize to (content, sender, thread_id)
                    Skip if sender_is_agent (webhook only)
                              │
                              ▼
                    Load identity (SOUL.md + agent.yaml)
                              │
                              ▼
                    Retrieve top-k relevant past turns from pgai
                    Retrieve user facts from pgai
                              │
                              ▼
                    Build prompt: identity + memory + user facts + message
                              │
                              ▼
                    LLM generates response (may include tool calls)
                    If tool calls: execute via MCP → inject results → re-invoke LLM
                              │
                              ▼
                    Store turn + embedding in pgai
                    Log to Langfuse
                              │
                              ▼
                    Return { reply, agent, timestamp, conversation_id?, tool_calls? }
```

## Tech Decisions (→ IPA Key Decisions D-xx)

| Decision | Context | Chosen | Rationale |
|----------|---------|--------|-----------|
| Language | Dumb Agent is TypeScript | **Python** | CrewAI/LangChain ecosystem, better ML libs, team alignment for Tier 3 |
| Framework | Web framework | **FastAPI** | Async, auto-docs, Pydantic native, lightweight |
| Memory store | Need semantic search over embeddings | **PostgreSQL + pgai** | Single DB for both structured data and vector search |
| Tool layer | Need extensible tool calling | **MCP via langchain-mcp-adapters** | Standard protocol, growing ecosystem |
| Model routing | Multi-provider support | **LiteLLM** | Unified API for Claude/GPT/DeepSeek/Ollama |
| Observability | Need tracing for eval | **Langfuse** | Open-source, LLM-native tracing |
| Containerization | Consistent deployment | **Docker + docker-compose** | Match Dumb Agent pattern, include PostgreSQL |

## Nice-to-Have (Post-MVP → Tier 3)

- RAG pipeline (document ingestion)
- Graph context (Memgraph relationships)
- Self-optimisation (reflection + prompt evolution)
- Reasoning model routing (extended thinking)
- Streaming responses (SSE)
- WebSocket support

## Key Assumptions to Validate

1. **Semantic search improves response quality** — A/B eval on 50 test conversations with/without pgai retrieval
2. **Tool calls reliable >90%** — Measure success rate over 100 tasks via Langfuse traces
3. **soul.md pattern transfers to Python** — Blind comparison of Dumb vs Pro Agent personality
4. **pgai top-k retrieval fast enough** — Latency < 200ms on 10k+ stored turns
5. **LiteLLM routing reduces cost** — Cost + quality comparison over 100 tasks

## Out of Scope

- No RAG / document ingestion (Tier 3)
- No graph context / Memgraph (Tier 3)
- No self-optimisation / reflection pipeline (Tier 3)
- No reasoning model / extended thinking (Tier 3)
- No UI / frontend — API only
- No multi-agent orchestration (Tier 4)
- No authentication beyond bearer token

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| pgai returns irrelevant memories | Agent confuses context, worse than no memory | Tune similarity threshold, add recency weighting, benchmark vs baseline |
| MCP tool calls hallucinate params | Failed actions, potential damage to external systems | Strict param validation, sandboxed execution, max retries = 1 |
| LiteLLM adds latency | Slower responses, harder debugging | Profile overhead, fallback to direct API if >100ms overhead |
| CrewAI framework lock-in | Harder to customize | Use CrewAI minimally, keep core logic framework-agnostic |
| Cost overruns from tool loops | Unexpected spend | Hard cost cap per request, max tool calls per turn (default 5) |

## Success Criteria

- Agent remembers context from 100+ conversations ago and uses it relevantly
- Tool calls succeed >90% without hallucinated parameters
- Structured output validates against Pydantic schema >95%
- Total cost per medium task < $0.50
- API contract matches Dumb Agent (drop-in replacement)
- Response latency < 5s for non-tool tasks, < 15s for tool-using tasks

## 🚦 GATE 1: Scope Validation

- [ ] Talked to 3+ potential users about the problem
- [ ] Users confirmed this is a real pain point
- [ ] MVP scope acceptable (≤ 3 phases) ✅
- [ ] Assumptions documented for later validation ✅
- [ ] Team aligned on priorities

**⚠️ Scope is exactly 3 phases — on budget. Do NOT add features without removing one.**

## Next Step

After GATE 1 validation:
→ Run `/ipa:spec` to generate `docs/SRD.md` + `docs/UI_SPEC.md`
→ Work context: `/Users/phuc/Code/04-llms/pro-agent/`

# Pro Agent (Tier 2)

Tier 2 in the agent4startup ladder. Drop-in replacement for Dumb Agent with long-term semantic memory (PostgreSQL + pgvector) and MCP tool integration.

**Version:** 1.0.0 | **Status:** Production Ready | **License:** MIT

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Python 3.12+ (for local development)

### 1. Clone and Configure

```bash
cp .env.example .env
# Edit .env with your API keys (LLM, embedding provider, etc.)
```

### 2. Start Services

```bash
docker-compose up -d
# Starts: FastAPI agent (port 8000) + PostgreSQL with pgvector
```

### 3. Test

```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer $(echo $AUTH_TOKEN)" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the meaning of life?", "sender": "test_user"}'
```

### 4. Check Health

```bash
curl http://localhost:8000/health | jq .
```

---

## Architecture Overview

```mermaid
flowchart TD
    A["Client<br/>Typebot, script, app"] -->|POST /chat, /webhook| B["FastAPI + Auth<br/>Bearer Token"]
    B --> C["Agent Pipeline<br/>LangGraph"]
    C -->|1. Load| D["Identity<br/>SOUL.md + agent.yaml"]
    C -->|2. Retrieve| E["Memory<br/>pgvector semantic search"]
    C -->|3. Invoke| F["LLM<br/>LiteLLM provider/model<br/>DeepSeek, OpenAI, etc."]
    C -->|4. Execute| G["Tools<br/>MCP adapters"]
    C -->|5. Store| H["PostgreSQL<br/>pgvector + TimescaleDB"]
    C -->|6. Trace| I["Langfuse<br/>optional"]
    G -->|web_search| J["DuckDuckGo"]
    G -->|github| K["PyGithub"]
    G -->|file_io| L["Sandbox FS"]
    style B fill:#ffebee
    style C fill:#fff3e0
    style F fill:#fff9c4
    style H fill:#e1f5fe


---

## Core Features

| Feature | Phase | Status |
|---------|-------|--------|
| Identity (SOUL.md + agent.yaml) | 1 | ✅ |
| Chat endpoint (/chat) | 1 | ✅ |
| Webhook endpoint (/webhook) | 1 | ✅ |
| Health endpoint (/health) | 1 | ✅ |
| Bearer token auth | 1 | ✅ |
| Long-term memory (conversation turns) | 1 | ✅ |
| User facts retrieval | 1 | ✅ |
| Session management (LangGraph threads) | 1 | ✅ |
| MCP tool integration | 2 | ✅ |
| Web search tool | 2 | ✅ |
| GitHub tool | 2 | ✅ |
| File I/O tool (sandboxed) | 2 | ✅ |
| Tool guardrails (max calls, timeout) | 2 | ✅ |
| Langfuse observability | 2 | ✅ |
| Structured output validation | 3 | ✅ |
| Multi-model routing (LiteLLM) | 3 | ✅ |
| Cost tracking | 3 | ✅ |

---

## API Reference

### POST /chat

Direct conversation API with memory context and tool support.

**Request:**
```json
{
  "message": "Tell me about FastAPI",
  "sender": "user123",
  "session_id": "conv-456"
}
```

**Response:**
```json
{
  "reply": "FastAPI is a modern web framework...",
  "agent": "pro-agent",
  "timestamp": "2026-03-18T10:00:00.000Z",
  "tool_calls": [
    {
      "tool": "web_search",
      "result": "Found 3 articles about FastAPI",
      "success": true
    }
  ]
}
```

**Auth:** `Authorization: Bearer <AUTH_TOKEN>`

See [API_SPEC.md](./docs/API_SPEC.md) for full details.

---

### POST /webhook

Typebot/n8n compatible webhook. Skips messages from agents to prevent loops.

**Request:**
```json
{
  "event": "message_created",
  "message": {
    "content": "Hello",
    "sender_name": "John",
    "sender_id": "user-123",
    "sender_is_agent": false,
    "conversation_id": "conv-456"
  },
  "conversation": { "id": "conv-456" }
}
```

**Response:** Same format as /chat (without `tool_calls` field for simplicity).

---

### GET /health

No auth required. Returns service status, uptime, memory stats, available tools.

**Response:**
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
  "tools_available": ["web_search", "github", "file_io"]
}
```

---

## Configuration

### Environment Variables (Core)

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_TOKEN` | Required | Bearer token for API authentication |
| `LLM_PROVIDER` | `deepseek` | LLM provider (deepseek, openai, anthropic, ollama) |
| `LLM_MODEL` | `deepseek-chat` | Model identifier |
| | | **Note:** LiteLLM combines as `{provider}/{model}` for routing (e.g. `deepseek/deepseek-chat`) |
| | | **DeepSeek R1:** Use `deepseek-reasoner` to enable `<think>` blocks in responses |
| `LLM_API_KEY` | Required | API key for LLM provider |
| `POSTGRES_URL` | `postgresql://agent:agent@localhost:5432/pro_agent` | Database connection string |
| `PORT` | `8000` | Server port |

### Environment Variables (Embeddings)

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model (configurable) |
| `EMBEDDING_API_KEY` | `${LLM_API_KEY}` | API key for embedding provider |
| `EMBEDDING_API_BASE` | `""` | Custom base URL (e.g., for Ollama) |

### Environment Variables (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `LANGFUSE_PUBLIC_KEY` | `""` | Langfuse public key (optional observability) |
| `LANGFUSE_SECRET_KEY` | `""` | Langfuse secret key |
| `GITHUB_TOKEN` | `""` | GitHub API token for tool use |
| `SEARCH_API_KEY` | `""` | Search API key for web_search tool |
| `FILE_IO_SANDBOX_DIR` | `/app/sandbox` | Sandbox directory for file I/O tool |

### Identity Configuration

**SOUL.md** — Agent personality (markdown, human-editable):
```markdown
# Soul

## Values
- Be helpful, honest, and concise
- Admit uncertainty rather than guessing

## Communication Style
- Direct — no filler words
- Use bullet points for structured answers
```

**agent.yaml** — Structured configuration (machine-readable):
```yaml
name: "Pro Agent"
role: "A versatile assistant with persistent memory and tool access"
style: "Concise, technical, slightly witty"

model:
  temperature: 0.7
  max_tokens: 4096

memory:
  top_k_turns: 10
  top_k_facts: 5
  similarity_threshold: 0.7

tools:
  max_calls_per_turn: 5
  timeout_seconds: 30
  enabled:
    - web_search
    - github
    - file_io

cost:
  max_per_request: 1.00
  currency: "USD"
```

---

## Deployment

### Docker Compose

```bash
docker-compose up -d
```

Services:
- **pro-agent** (FastAPI): Runs on port 8000
- **postgres** (PostgreSQL 17 + pgvector): Runs on port 5432

Volumes:
- `pgdata:/var/lib/postgresql/data` — Database persistence
- `./SOUL.md:/app/SOUL.md` — Agent personality
- `./agent.yaml:/app/agent.yaml` — Agent configuration
- `./sandbox/:/app/sandbox/` — File I/O sandbox

### Environment File

Create `.env` from `.env.example`:

```bash
cp .env.example .env
# Edit with your credentials
```

### Health Checks

Both containers have health checks configured. Verify:

```bash
docker-compose ps
# Should show "healthy" status
```

---

## Database Schema

Four tables store agent memory and tool audit trails:

| Table | Purpose | Rows (typical) |
|-------|---------|--------|
| `sessions` | Conversation grouping by thread_id | 100s–1000s |
| `conversation_turns` | Message storage with embeddings | 10k–100k+ |
| `user_facts` | Persistent user knowledge | 100s–1000s |
| `tool_call_logs` | Tool execution audit trail + cost | 1k–10k+ |

See [DB_DESIGN.md](./docs/DB_DESIGN.md) for schema details.

---

## Development

### Local Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Testing

```bash
pytest tests/ -v
pytest tests/ -k "test_chat" -v  # Specific test
```

### Code Structure

```
pro-agent/
├── app/
│   ├── main.py               # FastAPI routes (224 LOC)
│   ├── config.py             # Pydantic settings
│   ├── auth.py               # Bearer token validation
│   ├── identity.py           # SOUL.md + agent.yaml loading
│   ├── agent/
│   │   ├── graph.py          # LangGraph agent definition
│   │   ├── nodes.py          # Agent nodes (LLM, tools)
│   │   └── state.py          # Agent state schema
│   ├── memory/
│   │   ├── embeddings.py     # LiteLLM-based embedding
│   │   ├── retriever.py      # Semantic memory retrieval
│   │   └── store.py          # PostgreSQL memory storage
│   ├── tools/
│   │   ├── registry.py       # Tool registration
│   │   ├── guardrails.py     # Execution limits
│   │   └── logger.py         # Tool call audit
│   ├── output/
│   │   ├── schemas.py        # Pydantic output models
│   │   └── validator.py      # Output validation
│   ├── models/
│   │   ├── requests.py       # Request schemas
│   │   └── responses.py      # Response schemas
│   ├── db/
│   │   └── pool.py           # async psycopg pool
│   └── observability/
│       └── langfuse.py       # Optional tracing
├── db/
│   └── init.sql              # Database schema + extensions
├── tests/
│   └── test_*.py             # Pytest suite
├── pyproject.toml            # Dependencies + metadata
├── docker-compose.yml        # Services definition
├── Dockerfile                # Agent image
├── SOUL.md                   # Agent personality
├── agent.yaml                # Agent configuration
└── docs/                     # Detailed documentation
    ├── SRD.md                # Functional requirements
    ├── API_SPEC.md           # API specification
    ├── DB_DESIGN.md          # Database design
    ├── UI_SPEC.md            # (N/A for backend)
    ├── IMPLEMENTATION_NOTES.md # Implementation status
    ├── project-overview-pdr.md # Project overview
    ├── codebase-summary.md    # Module summary
    ├── code-standards.md      # Python conventions
    ├── system-architecture.md # Detailed architecture
    └── project-roadmap.md     # Future tiers + improvements
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python | LangChain ecosystem, ML libs, Tier 3 alignment |
| Web framework | FastAPI | Async, auto-docs, Pydantic integration |
| Agent orchestration | LangGraph | State machine with checkpointing, same pattern as Dumb Agent |
| Memory store | PostgreSQL + pgvector | Single DB for structured + vector data |
| Tool protocol | MCP | Standard, reusable across tiers |
| Model access | LiteLLM | Unified API for multiple providers + cost tracking |
| Observability | Langfuse | LLM-native tracing (optional) |
| Identity format | SOUL.md + agent.yaml | Personality (markdown) + config (YAML) separation |

---

## Operational Insights

### Performance

- Response latency: < 5s (no tools), < 15s (with tools)
- Memory retrieval: < 200ms (pgvector semantic search)
- Health endpoint: < 50ms
- Tool success rate: > 90%

### Graceful Degradation

- If PostgreSQL unavailable → agent works with in-context memory only
- If embedding API fails → turns stored but not searchable
- If tool call fails → agent responds without tool results
- If Langfuse unavailable → no tracing (agent works normally)

### Backward Compatibility

- 100% compatible with Dumb Agent API
- `/chat` contract is a superset (new `tool_calls` field optional)
- `/webhook` response unchanged
- Same Docker deployment pattern

---

## Monitoring & Observability

### Logs

Structured JSON logs to stdout:

```bash
docker-compose logs -f pro-agent
```

### Health Checks

```bash
curl http://localhost:8000/health | jq '.memory_stats'
```

### Langfuse Integration (Optional)

If configured:
- Every request traced with spans for memory, LLM, tools
- Cost tracking per request
- Conversation replay via Langfuse dashboard

---

## Roadmap & Future

**Current Status:** v1.0.0 Complete
- All 17 functional requirements implemented and tested
- Production-ready, drop-in replacement for Dumb Agent

**Tier 3 (Pro Max):**
- Batch embedding generation (async)
- Hierarchical memory (summaries + chunks)
- Fine-tuned tool routing
- Multi-turn planning (extended context)

**Tier 4:**
- Orchestrator agent delegating to Pro Agent
- Agent-to-agent communication
- Shared knowledge base across agents

See [project-roadmap.md](./docs/project-roadmap.md) for details.

---

## Support & Documentation

- **API Details:** [API_SPEC.md](./docs/API_SPEC.md)
- **Database Design:** [DB_DESIGN.md](./docs/DB_DESIGN.md)
- **Functional Requirements:** [SRD.md](./docs/SRD.md)
- **System Architecture:** [system-architecture.md](./docs/system-architecture.md)
- **Code Standards:** [code-standards.md](./docs/code-standards.md)
- **Codebase Summary:** [codebase-summary.md](./docs/codebase-summary.md)
- **Project Overview & PDR:** [project-overview-pdr.md](./docs/project-overview-pdr.md)

---

## License

MIT License. See LICENSE file for details.

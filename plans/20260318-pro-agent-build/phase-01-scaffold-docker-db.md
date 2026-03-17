# Phase 1: Project Scaffold + Docker + DB

## Context Links
- [SRD.md](../../docs/SRD.md) — FR-01, FR-04, FR-05
- [UI_SPEC.md](../../docs/UI_SPEC.md) — §4 Config Interface, §7 Docker Compose
- [DB_DESIGN.md](../../docs/DB_DESIGN.md) — Full DDL, extensions, init.sql
- [Dumb Agent](https://github.com/phucsystem/a-dumb-agent) — Reference for API contract

## Overview
- **Priority:** P1
- **Status:** ✅ Complete
- **Effort:** 4h
- **FRs:** FR-01 (Identity), FR-04 (Health), FR-05 (Auth)

Set up Python project structure, Docker Compose (agent + PostgreSQL), database init script, identity loader, health endpoint, and auth middleware. By end of this phase: `docker-compose up` starts a working agent that responds on `/health` with auth enforced.

## Key Insights
- Dumb Agent uses Express.js + LangGraph.js — Pro Agent ports to FastAPI + LangGraph Python
- Identity pattern: `soul.md` + `identity.md` → upgraded to `SOUL.md` + `agent.yaml`
- PostgreSQL needs pgvector + pgai extensions (pre-installed in timescaledb-ha image)
- Auth: timing-safe bearer token comparison (same as Dumb Agent)

## Requirements

**Functional:**
- FR-01: Load SOUL.md + agent.yaml at startup, fallback defaults if missing
- FR-04: GET /health returns status, uptime, provider, memory_stats, tools_available
- FR-05: Bearer token auth on /chat and /webhook, skip on /health

**Non-Functional:**
- NFR-06: Single `docker-compose up` brings up everything
- NFR-07: Same env var names as Dumb Agent where applicable

## Architecture

```
pro-agent/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, endpoints, middleware
│   ├── config.py            # Settings from .env + agent.yaml
│   ├── identity.py          # Load SOUL.md + agent.yaml → system prompt
│   ├── auth.py              # Bearer token middleware
│   └── models/
│       └── __init__.py
├── db/
│   └── init.sql             # Extensions + CREATE TABLE statements
├── SOUL.md                  # Agent personality (human-editable)
├── agent.yaml               # Agent config (structured)
├── .env.example             # Environment template
├── .env                     # Local env (gitignored)
├── Dockerfile               # Multi-stage Python build
├── docker-compose.yml       # Agent + PostgreSQL
├── pyproject.toml           # Dependencies (uv/pip)
├── requirements.txt         # Pinned deps (for Docker)
└── .gitignore
```

## Related Code Files

**Create:**
- `app/__init__.py`
- `app/main.py` — FastAPI app with /health endpoint
- `app/config.py` — Pydantic Settings loading .env + agent.yaml
- `app/identity.py` — Load SOUL.md + agent.yaml → combined system prompt
- `app/auth.py` — Bearer token auth dependency
- `app/models/__init__.py`
- `db/init.sql` — Full DDL from DB_DESIGN.md
- `SOUL.md` — Default soul template
- `agent.yaml` — Default config template
- `.env.example` — Environment template
- `Dockerfile` — Python 3.12, multi-stage
- `docker-compose.yml` — Agent + PostgreSQL + pgai
- `pyproject.toml` — Project metadata + deps
- `requirements.txt` — Pinned for Docker
- `.gitignore`

## Implementation Steps

### 1. Initialize Python project

```bash
cd /Users/phuc/Code/04-llms/pro-agent
```

Create `pyproject.toml` with deps:
- `fastapi[standard]` — web framework
- `uvicorn[standard]` — ASGI server
- `langgraph` — agent framework
- `langchain-openai` — LLM integration
- `litellm` — multi-model routing
- `psycopg[binary]` — PostgreSQL driver (async)
- `pydantic-settings` — config from .env
- `pyyaml` — agent.yaml parsing
- `hmac` (stdlib) — timing-safe auth

Create `requirements.txt` pinned versions for Docker reproducibility.

### 2. Create .env.example and .gitignore

`.env.example` — copy from UI_SPEC §4:
```
AUTH_TOKEN=your-long-lived-token-here
LLM_API_KEY=sk-xxx
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
PORT=8000
POSTGRES_URL=postgresql://agent:agent@localhost:5432/pro_agent
```

`.gitignore`:
```
__pycache__/
*.pyc
.env
.venv/
dist/
*.egg-info/
.worktrees/
```

### 3. Create db/init.sql

Copy full DDL from DB_DESIGN.md §3:
- CREATE EXTENSION vector, ai, uuid-ossp
- CREATE TABLE sessions, conversation_turns, user_facts, tool_call_logs
- CREATE INDEX statements

### 4. Create docker-compose.yml

From UI_SPEC §7:
- `agent` service: build from Dockerfile, port 8000, env_file, volumes for SOUL.md + agent.yaml, depends_on postgres healthy
- `postgres` service: timescale/timescaledb-ha:pg17, mount db/init.sql to /docker-entrypoint-initdb.d/, healthcheck, pgdata volume

### 5. Create Dockerfile

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY SOUL.md agent.yaml ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6. Create app/config.py

Use `pydantic-settings` BaseSettings:
- Load from .env: AUTH_TOKEN, LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL, PORT, POSTGRES_URL
- Load from agent.yaml: name, role, style, model config, memory config, tools config, cost config
- Merge: env vars override agent.yaml values

### 7. Create app/identity.py

Port from Dumb Agent's `identity.js`:
- Read SOUL.md from project root (fallback: default personality)
- Read agent.yaml (fallback: defaults)
- Combine: `[name/role/style from yaml]\n\n[SOUL.md content]`
- Cache result (load once at startup)

### 8. Create app/auth.py

FastAPI dependency:
```python
async def verify_bearer_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Unauthorized")
    token = authorization[7:]
    if not hmac.compare_digest(token, settings.auth_token):
        raise HTTPException(401, "Unauthorized")
```

### 9. Create app/main.py

- FastAPI app instance
- Startup: load identity, connect to PostgreSQL (with retry)
- GET /health: no auth, return status/uptime/provider/memory_stats/tools_available
- POST /chat: placeholder (returns 501, implemented in Phase 2)
- POST /webhook: placeholder (returns 501, implemented in Phase 2)
- Auth middleware on /chat and /webhook via FastAPI dependencies

### 10. Create SOUL.md + agent.yaml defaults

SOUL.md — default personality template
agent.yaml — default config with all fields + comments

### 11. Test: docker-compose up

- Verify PostgreSQL starts, init.sql runs, tables created
- Verify agent starts, connects to PostgreSQL
- Verify GET /health returns 200 with correct structure
- Verify POST /chat returns 401 without token
- Verify POST /chat with valid token returns 501 (not yet implemented)

## Todo List

- [ ] Create pyproject.toml + requirements.txt
- [ ] Create .env.example + .gitignore
- [ ] Create db/init.sql with full DDL
- [ ] Create docker-compose.yml (agent + postgres)
- [ ] Create Dockerfile (Python 3.12)
- [ ] Create app/config.py (Pydantic Settings + agent.yaml)
- [ ] Create app/identity.py (SOUL.md + agent.yaml loader)
- [ ] Create app/auth.py (bearer token middleware)
- [ ] Create app/main.py (FastAPI + /health + placeholder endpoints)
- [ ] Create SOUL.md + agent.yaml defaults
- [ ] Test: docker-compose up, health, auth

## Success Criteria

- `docker-compose up` starts agent + PostgreSQL without errors
- `GET /health` returns 200 with `{ status: "ok", agent: "pro-agent", ... }`
- All 4 database tables created with correct schema
- Bearer token auth blocks unauthorized requests (401)
- Authorized requests reach endpoint handlers
- SOUL.md + agent.yaml loaded and reflected in identity

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| pgai extension not in Docker image | DB init fails | Use timescale/timescaledb-ha:pg17, verify with `SELECT * FROM pg_available_extensions` |
| Python/FastAPI unfamiliar patterns | Slower development | Reference FastAPI docs, keep endpoints simple |
| Port conflict (8000, 5432) | Can't start services | Make ports configurable via .env |

## Security Considerations
- AUTH_TOKEN never logged or returned in responses
- POSTGRES_URL with credentials via .env only (never in code)
- .env in .gitignore

## Next Steps
- Phase 2: Implement core agent loop, memory retrieval, /chat + /webhook endpoints

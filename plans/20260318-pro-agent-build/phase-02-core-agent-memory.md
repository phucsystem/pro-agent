# Phase 2: Core Agent + Memory + Endpoints

## Context Links
- [SRD.md](../../docs/SRD.md) — FR-02, FR-03, FR-06, FR-07, FR-08
- [API_SPEC.md](../../docs/API_SPEC.md) — §2 Endpoint Details, §4.2 Memory Retriever, §4.3 Session Manager
- [DB_DESIGN.md](../../docs/DB_DESIGN.md) — §4 Key Queries, §5 Embedding Strategy
- [Dumb Agent graph.js](https://github.com/phucsystem/a-dumb-agent) — LangGraph pattern reference

## Overview
- **Priority:** P1
- **Status:** ✅ Complete
- **Effort:** 6h
- **FRs:** FR-02, FR-03, FR-06, FR-07, FR-08

Implement the LangGraph agent loop, pgai memory retrieval, session management, and both /chat and /webhook endpoints. By end of this phase: agent responds to messages with long-term memory context, stores embeddings, and works with Typebot/n8n via webhook.

## Key Insights
- Dumb Agent uses LangGraph.js StateGraph → port to `langgraph` Python SDK
- Dumb Agent graph: START → agent → (tools conditional) → END — same pattern
- Memory retrieval: embed incoming message → cosine search past turns → inject as system prompt context
- User facts: LLM extracts facts from conversation → store with embeddings for retrieval
- Session = LangGraph thread_id; upsert on each request

## Requirements

**Functional:**
- FR-02: POST /chat — `{ message, sender, session_id? }` → `{ reply, agent, timestamp }`
- FR-03: POST /webhook — Typebot/n8n payload → `{ reply, agent, conversation_id, timestamp }`, skip agent messages
- FR-06: Embed + store every turn; retrieve top-k similar turns per request
- FR-07: Store/retrieve per-user facts via pgai semantic search
- FR-08: Session upsert by thread_id, LangGraph checkpointing per session

**Non-Functional:**
- NFR-01: < 5s response latency (no tools), < 200ms pgai search
- NFR-02: Graceful degradation if pgai unavailable
- NFR-07: Backward-compatible with Dumb Agent /chat and /webhook contracts

## Architecture

```
app/
├── main.py              # Add /chat and /webhook endpoint handlers
├── agent/
│   ├── __init__.py
│   ├── graph.py         # LangGraph StateGraph: agent node → (tool node) → END
│   ├── state.py         # AgentState annotation (messages, system_prompt, sender)
│   └── nodes.py         # Agent node: build prompt + invoke LLM
├── memory/
│   ├── __init__.py
│   ├── store.py         # pgai connection pool, turn storage, embedding generation
│   ├── retriever.py     # Semantic search: top-k turns + user facts
│   └── facts.py         # Extract + store user facts from conversations
├── sessions/
│   ├── __init__.py
│   └── manager.py       # Session upsert, thread_id mapping
└── db/
    ├── __init__.py
    └── pool.py          # asyncpg connection pool lifecycle
```

## Related Code Files

**Create:**
- `app/db/__init__.py`
- `app/db/pool.py` — async connection pool (startup/shutdown lifecycle)
- `app/memory/__init__.py`
- `app/memory/store.py` — store turns + embeddings in pgai
- `app/memory/retriever.py` — semantic search for relevant turns + facts
- `app/memory/facts.py` — extract user facts from LLM response
- `app/sessions/__init__.py`
- `app/sessions/manager.py` — session upsert by thread_id
- `app/agent/__init__.py`
- `app/agent/state.py` — LangGraph state annotation
- `app/agent/graph.py` — StateGraph definition
- `app/agent/nodes.py` — agent node implementation

**Modify:**
- `app/main.py` — add /chat, /webhook handlers + DB lifecycle
- `requirements.txt` — add `asyncpg`, `langchain-core`

## Implementation Steps

### 1. Create app/db/pool.py

Async connection pool using `psycopg` (async):
```python
from psycopg_pool import AsyncConnectionPool

pool: AsyncConnectionPool | None = None

async def init_pool(postgres_url: str):
    global pool
    pool = AsyncConnectionPool(conninfo=postgres_url, min_size=2, max_size=10)
    await pool.open()

async def close_pool():
    if pool:
        await pool.close()

def get_pool() -> AsyncConnectionPool:
    assert pool is not None, "DB pool not initialized"
    return pool
```

Register in FastAPI lifespan (startup/shutdown).

### 2. Create app/memory/store.py

```python
async def store_turn(session_id, user_id, role, content, embedding=None):
    """Insert conversation turn + optional embedding vector."""
    # INSERT INTO conversation_turns ... RETURNING id
    # See DB_DESIGN.md §4 "Store a Conversation Turn"

async def generate_embedding(text: str) -> list[float]:
    """Call LiteLLM embedding API → text-embedding-3-small → 1536-dim vector."""
    # litellm.embedding(model="text-embedding-3-small", input=text)
    # Return embedding vector; on failure return None (graceful degradation)
```

### 3. Create app/memory/retriever.py

```python
async def retrieve_relevant_turns(embedding, user_id, top_k=10, threshold=0.7):
    """Semantic search: cosine similarity over conversation_turns."""
    # See DB_DESIGN.md §4 "Semantic Search: Retrieve Relevant Past Turns"

async def retrieve_user_facts(embedding, user_id, top_k=5):
    """Get user facts ranked by relevance to current message."""
    # See DB_DESIGN.md §4 "Retrieve User Facts"

def format_memory_context(turns, facts) -> str:
    """Format retrieved turns + facts for system prompt injection."""
    # "## Relevant past conversations:\n{turns}\n\n## Known about this user:\n{facts}"
```

### 4. Create app/memory/facts.py

```python
async def extract_and_store_facts(user_id, conversation_content):
    """Ask LLM to extract new facts about the user from conversation.
    Store each fact with embedding in user_facts table.
    Only extract if conversation contains personal info worth remembering."""
    # Simple approach: after every N turns, ask LLM:
    # "Extract any new facts about the user from this conversation. Return JSON array."
    # Deduplicate against existing facts via semantic similarity
```

### 5. Create app/sessions/manager.py

```python
async def get_or_create_session(user_id, agent_id, thread_id) -> str:
    """Upsert session by thread_id. Return session UUID."""
    # See DB_DESIGN.md §4 "Get or Create Session"
    # INSERT ... ON CONFLICT (thread_id) DO UPDATE SET last_active_at = now()
```

### 6. Create app/agent/state.py

Port from Dumb Agent's AgentAnnotation:
```python
from langgraph.graph import MessagesState
from typing import Annotated

class AgentState(MessagesState):
    system_prompt: str
    sender: str
    session_id: str
```

### 7. Create app/agent/nodes.py

```python
async def agent_node(state: AgentState):
    """Build full prompt and invoke LLM."""
    # 1. Start with identity (system prompt from config)
    # 2. Append memory context (retrieved turns + facts)
    # 3. Create SystemMessage with combined prompt
    # 4. Invoke LLM via LiteLLM (or langchain ChatOpenAI)
    # 5. Return { messages: [response] }
```

### 8. Create app/agent/graph.py

Port from Dumb Agent's createGraph():
```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

def create_graph():
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)  # No tools yet (Phase 3)
    checkpointer = MemorySaver()  # In-memory for now; Postgres checkpointer later
    return builder.compile(checkpointer=checkpointer)
```

### 9. Implement POST /chat in app/main.py

```python
@app.post("/chat", dependencies=[Depends(verify_bearer_token)])
async def chat(request: ChatRequest):
    # 1. Normalize: content=message, sender=sender, thread_id=session_id
    # 2. Session upsert
    # 3. Generate embedding for message
    # 4. Retrieve memory context (turns + facts)
    # 5. Build system prompt: identity + memory context
    # 6. Invoke graph with thread_id
    # 7. Store user turn + assistant turn with embeddings
    # 8. Extract/store facts (async, non-blocking)
    # 9. Return { reply, agent, timestamp }
```

### 10. Implement POST /webhook in app/main.py

```python
@app.post("/webhook", dependencies=[Depends(verify_bearer_token)])
async def webhook(request: WebhookRequest):
    # 1. Extract message.content (400 if missing)
    # 2. Skip if sender_is_agent → return { skipped: true }
    # 3. Normalize: content, sender, thread_id (from conversation.id)
    # 4. Same pipeline as /chat steps 2–8
    # 5. Return { reply, agent, conversation_id, timestamp }
    #    (NO tool_calls in webhook response)
```

### 11. Create Pydantic request/response models

```python
class ChatRequest(BaseModel):
    message: str
    sender: str = "unknown"
    session_id: str = "default"

class ChatResponse(BaseModel):
    reply: str
    agent: str = "pro-agent"
    timestamp: str

class WebhookMessage(BaseModel):
    content: str
    sender_name: str | None = None
    sender_id: str | None = None
    sender_is_agent: bool = False
    conversation_id: str | None = None

class WebhookConversation(BaseModel):
    id: str | None = None

class WebhookRequest(BaseModel):
    event: str | None = None
    message: WebhookMessage
    conversation: WebhookConversation | None = None

class WebhookResponse(BaseModel):
    reply: str
    agent: str = "pro-agent"
    conversation_id: str
    timestamp: str
```

### 12. Test end-to-end

- POST /chat with message → get reply with memory retrieval
- POST /chat same session → agent recalls previous message
- POST /webhook with Typebot-format payload → correct response
- POST /webhook with sender_is_agent=true → skipped
- Verify conversation_turns table populated with embeddings
- Verify sessions table has correct entries
- Test with pgai down → agent still responds (degraded, no memory)

## Todo List

- [ ] Create app/db/pool.py — async connection pool
- [ ] Create app/memory/store.py — turn storage + embedding generation
- [ ] Create app/memory/retriever.py — semantic search (turns + facts)
- [ ] Create app/memory/facts.py — fact extraction + storage
- [ ] Create app/sessions/manager.py — session upsert
- [ ] Create app/agent/state.py — LangGraph state annotation
- [ ] Create app/agent/nodes.py — agent node (prompt build + LLM call)
- [ ] Create app/agent/graph.py — StateGraph definition
- [ ] Create Pydantic request/response models
- [ ] Implement POST /chat endpoint
- [ ] Implement POST /webhook endpoint
- [ ] Wire DB pool lifecycle in FastAPI lifespan
- [ ] Test: /chat with memory recall
- [ ] Test: /webhook with Typebot payload
- [ ] Test: graceful degradation (pgai down)

## Success Criteria

- POST /chat returns correct response with memory context
- Agent recalls context from 10+ previous conversations (semantic search works)
- POST /webhook matches Dumb Agent contract exactly
- Agent messages skipped in webhook (no loops)
- Conversation turns stored with embeddings in PostgreSQL
- User facts extracted and stored
- Graceful degradation when pgai unavailable (responds without memory)
- Response latency < 5s for non-tool conversations

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Embedding API latency adds to response time | Slower responses | Generate embeddings async after response sent; store turn first, backfill embedding |
| LangGraph Python API differs from JS | Implementation confusion | Reference langgraph Python docs, not JS patterns |
| pgai vector search returns noise | Bad memory injection hurts quality | Tune similarity_threshold (0.7 default), test with various thresholds |
| Fact extraction too aggressive | Irrelevant facts pollute context | Only extract facts every N turns, semantic dedup before storing |

## Security Considerations
- Embeddings contain semantic content — treat as sensitive data
- User facts are personal data — scope retrieval strictly by user_id
- Never return raw memory context in API response

## Next Steps
- Phase 3: Add MCP tool integration, guardrails, Langfuse logging

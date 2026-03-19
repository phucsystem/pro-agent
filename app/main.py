import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.auth import verify_bearer_token
from app.identity import load_identity
from app.models.requests import ChatRequest, WebhookRequest
from app.models.responses import (
    ChatResponse, WebhookResponse, WebhookSkippedResponse,
    HealthResponse, MemoryStats,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    assert settings.auth_token, "FATAL: AUTH_TOKEN env var must be set"
    logger.info(f"Starting Pro Agent — provider={settings.llm_provider} model={settings.llm_model}")
    load_identity()  # warm cache

    # Try DB pool init
    try:
        from app.db.pool import init_pool
        await init_pool(settings.postgres_url)
        logger.info("Database pool initialized")
    except Exception as exc:
        logger.warning(f"DB pool init failed (degraded mode): {exc}")

    # Try Langfuse init
    try:
        from app.observability.langfuse import init_langfuse
        init_langfuse(
            settings.langfuse_public_key,
            settings.langfuse_secret_key,
            settings.langfuse_host,
        )
    except Exception:
        pass  # Langfuse is optional

    yield

    # Shutdown
    try:
        from app.db.pool import close_pool
        await close_pool()
    except Exception:
        pass


app = FastAPI(title="Pro Agent", version="1.0.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health():
    uptime = int(time.time() - _start_time)
    memory_stats = MemoryStats()
    tools_available: list[str] = []

    try:
        from app.db.pool import get_pool
        from app.db.tables import SESSIONS, CONVERSATION_TURNS, USER_FACTS
        async with get_pool().connection() as conn:
            row = await conn.fetchrow(
                f"SELECT "
                f"(SELECT GREATEST(COALESCE(reltuples, 0), 0)::bigint FROM pg_class WHERE relname = $1) AS turns,"
                f"(SELECT GREATEST(COALESCE(reltuples, 0), 0)::bigint FROM pg_class WHERE relname = $2) AS sessions,"
                f"(SELECT GREATEST(COALESCE(reltuples, 0), 0)::bigint FROM pg_class WHERE relname = $3) AS facts",
                CONVERSATION_TURNS, SESSIONS, USER_FACTS,
            )
            memory_stats = MemoryStats(
                total_turns=row["turns"],
                total_sessions=row["sessions"],
                total_user_facts=row["facts"],
                pgai_connected=True,
            )
    except Exception:
        pass  # degraded — memory_stats stays default

    try:
        from app.tools.registry import get_registered_tools
        tools_available = [t.name for t in get_registered_tools()]
    except Exception:
        pass

    return HealthResponse(
        provider=settings.llm_provider,
        model=settings.llm_model,
        uptime=uptime,
        memory_stats=memory_stats,
        tools_available=tools_available,
    )


@app.post("/chat", dependencies=[Depends(verify_bearer_token)])
async def chat(request: ChatRequest):
    from app.agent.pipeline import run_agent

    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"[/chat] sender={request.sender} session={request.session_id} msg={request.message[:80]!r}")

    try:
        reply, tool_calls = await run_agent(
            content=request.message,
            sender=request.sender,
            thread_id=request.session_id,
        )
    except Exception as exc:
        logger.error(f"Chat error: {exc}")
        raise HTTPException(status_code=500, detail="LLM request failed")

    response = ChatResponse(reply=reply, timestamp=timestamp)
    if tool_calls:
        response.tool_calls = tool_calls
    return response


@app.post("/webhook", dependencies=[Depends(verify_bearer_token)])
async def webhook(request: WebhookRequest):
    from app.agent.pipeline import run_agent

    msg = request.message
    if not msg.content:
        raise HTTPException(status_code=400, detail="message.content is required")

    if msg.sender_is_agent:
        return WebhookSkippedResponse()

    sender = msg.sender_name or msg.sender_id or "unknown"
    thread_id = (
        (request.conversation.id if request.conversation else None)
        or msg.conversation_id
        or "default"
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"[/webhook] event={request.event} sender={sender} conv={thread_id} msg={msg.content[:80]!r}")

    try:
        reply, _ = await run_agent(
            content=msg.content,
            sender=sender,
            thread_id=thread_id,
        )
    except Exception as exc:
        logger.error(f"Webhook error: {exc}")
        raise HTTPException(status_code=500, detail="LLM request failed")

    return WebhookResponse(reply=reply, conversation_id=thread_id, timestamp=timestamp)

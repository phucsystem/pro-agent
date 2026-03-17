# Code Review — Pro Agent Python Implementation

**Date:** 2026-03-18
**Scope:** `app/` — 29 Python files, ~700 LOC
**Score: 7.5 / 10**

---

## Overall Assessment

Clean, readable codebase. YAGNI/KISS applied well — no over-engineering. Graceful degradation patterns are consistent throughout (DB down, LLM errors, memory failures all handled). The main weaknesses are: a sandbox escape vector in file I/O tooling, a missing `reason` field breaking API contract, `ToolGuardrails` being instantiated but never wired into the graph, and the embedding model being hard-coded without auth.

---

## Critical Issues

### C1 — Sandbox path-traversal escape (registry.py:47, 56)

The sandbox check uses string prefix matching on resolved paths. This is almost correct but has an edge case: if `sandbox_dir` resolves to `/app/sandbox`, a path like `/app/sandbox-escape/file.txt` will pass the `startswith` check.

```python
# Current — UNSAFE
if not str(safe).startswith(str(sandbox.resolve())):

# Fix — add trailing separator
sandbox_str = str(sandbox.resolve()) + "/"
if not str(safe).startswith(sandbox_str) and str(safe) != str(sandbox.resolve()):
```

**Impact:** LLM-controlled path traversal outside sandbox boundary.

### C2 — API contract break: `WebhookSkippedResponse` missing `reason` (responses.py:26)

`WebhookSkippedResponse` has `reason: str` as a required field with no default, but it is instantiated as `WebhookSkippedResponse()` in `main.py:129` with no arguments. This will raise a `ValidationError` at runtime whenever an agent-originated webhook is received.

```python
# responses.py:26 — reason has no default
class WebhookSkippedResponse(BaseModel):
    skipped: bool = True
    reason: str  # <-- required, no default

# main.py:129 — called with no args
return WebhookSkippedResponse()  # raises ValidationError
```

**Impact:** Every agent message webhook returns HTTP 500. Breaks Dumb Agent API contract.

---

## High Priority

### H1 — `ToolGuardrails` never wired into the agent loop (guardrails.py)

`ToolGuardrails` exists and has correct logic, but is never instantiated or called anywhere in `graph.py`, `nodes.py`, or `registry.py`. The `tools_max_calls_per_turn` setting is loaded from config but unused. A runaway tool loop will execute indefinitely until LiteLLM or the DB times out.

**Impact:** DoS via tool call amplification; cost blowout.

### H2 — Embedding model hard-coded without API key (embeddings.py:10)

`generate_embedding` calls `litellm.aembedding(model="text-embedding-3-small", input=text)` with no `api_key` or `api_base`. This will silently use OpenAI credentials (not the configured LLM provider). If the deployment is DeepSeek-only, every memory retrieval silently fails, degrading to a context-free agent.

```python
# embeddings.py:10 — no api_key passed
response = await litellm.aembedding(
    model="text-embedding-3-small",
    input=text,
)
```

**Impact:** Silent memory failure for non-OpenAI deployments.

### H3 — `app/routing/litellm.py` is a dead module

`chat_completion()` in `routing/litellm.py` duplicates the exact same LiteLLM invocation already in `agent/nodes.py`. It is never imported anywhere. The tool call logger (`tools/logger.py`) also references it via `get_pool()` but is never called either. Dead code creates maintenance confusion.

**Impact:** Maintenance confusion; developers may edit the dead copy and wonder why nothing changes.

### H4 — Auth token encoding assumption (auth.py:10)

`settings.auth_token.encode()` uses the default UTF-8 encoding. If the token contains non-ASCII characters (common in base64url tokens with padding), this silently breaks comparison. More importantly, if `settings.auth_token` is an empty string (mis-configuration), `hmac.compare_digest(b"", b"")` returns `True` — any empty `Authorization: Bearer ` header is accepted.

```python
# auth.py:10 — empty token accepted
if not hmac.compare_digest(token.encode(), settings.auth_token.encode()):
```

**Fix:** Add a startup guard: `assert settings.auth_token, "AUTH_TOKEN must be set"`.

---

## Medium Priority

### M1 — `_yaml` module-level execution on import (config.py:15)

`_load_agent_yaml()` is called at import time (`_yaml = _load_agent_yaml()`). If `agent.yaml` has a YAML injection or is malformed, it silently returns `{}`, causing all YAML-derived settings to fall back to defaults with no warning. The silent fallback masks misconfigurations.

### M2 — `load_identity()` cached but settings not (identity.py:7)

`@lru_cache(maxsize=1)` caches the result of `load_identity()` permanently. If `SOUL.md` or `agent.yaml` changes at runtime (e.g., hot-reload scenario), the identity is stale. This is fine for production, but the cache is never invalidated and there is no way to force reload without restarting the process. Document this explicitly or add a `reload_identity()` helper.

### M3 — `tool_call_logs` stores `parameters` as `str(dict)` (logger.py:31)

`str(parameters)` produces Python repr, not JSON. This makes the stored data hard to query or parse later. Use `json.dumps(parameters, default=str)` instead.

### M4 — `_extract_tool_calls` success heuristic is wrong (main.py:222)

```python
success=bool(result_text),
```

This reports success=False when a tool returns an empty string (valid for some tools like `file_write` with empty content), and success=True when a tool returns an error string like `"Error: path outside sandbox"`. The result text should be checked for error prefixes, or the tool node should propagate structured success/failure.

### M5 — `MemorySaver` (in-process) not suitable for multi-worker deployments (graph.py:30)

`MemorySaver()` stores LangGraph checkpoints in memory. With `uvicorn --workers N`, each worker has its own `MemorySaver` instance. Thread-level conversation continuity will break across workers. Document the single-worker constraint, or swap to `PostgresSaver` when the DB is available.

### M6 — `tc.function.arguments` is a JSON string, not a dict (nodes.py:57)

LiteLLM returns `tc.function.arguments` as a JSON-encoded string. Passing it directly into `AIMessage(tool_calls=[{"args": tc.function.arguments}])` means LangGraph's `ToolNode` receives stringified args instead of a dict. This will cause tool invocation failures.

```python
# nodes.py:57 — should be json.loads(tc.function.arguments)
"args": tc.function.arguments  # wrong — this is a JSON string
```

---

## Low Priority

### L1 — `LLM_API_KEY` logged at INFO level indirectly

`main.py:27` logs `provider` and `model`. Neither exposes the key. However, `litellm` itself logs request headers at DEBUG level by default. Confirm `litellm.set_verbose = False` (or rely on logging level) to prevent key leakage in verbose mode.

### L2 — `postgres_url` default contains credentials (config.py:30)

The default `postgresql://agent:agent@localhost:5432/pro_agent` is fine as a dev default, but if the app is deployed with no `POSTGRES_URL` env var set, it will attempt to connect to localhost with these credentials. A missing env var should fail loudly rather than silently use a default credential string.

### L3 — `file_write` tool has no size limit (registry.py:54-61)

There is no cap on `content` size. An LLM could write arbitrarily large files to the sandbox, causing disk exhaustion.

### L4 — `WebhookRequest.event` is optional but not validated (requests.py:31)

`event: str | None = None` — if downstream logic ever routes on event type, a missing event will cause an `AttributeError`. Consider requiring it or documenting its optional nature.

### L5 — `retrieve_user_facts` has no similarity threshold (retriever.py:36-56)

`retrieve_relevant_turns` applies a similarity threshold, but `retrieve_user_facts` returns top-k facts with no threshold. Low-relevance facts will always be injected into the prompt.

---

## Edge Cases Found During Review

- **Empty `msg.content` after tool calls** (`main.py:183`): When an AIMessage contains only tool_calls (no text content), `msg.content` is `""`. The check `if not reply_content` catches this and raises `ValueError`, but the error is caught above and returns HTTP 500 instead of retrying for the tool result. This is a legitimate flow where the LLM's turn ends with a tool call, not a text reply — the graph should have routed to tools first before hitting this check.

- **Concurrent `get_registered_tools()` calls** (`registry.py:95-99`): The lazy init pattern `if _registered_tools is None` is not thread-safe in a multi-threaded context. Under CPython's GIL this is fine, but worth noting if switching to a threaded executor.

- **`_get_or_create_session` race** (`store.py:9`): The upsert uses `ON CONFLICT (thread_id) DO UPDATE`. If two concurrent requests share a `thread_id` and the session doesn't exist yet, the first upsert wins and both get the same session — correct behavior. No issue here.

---

## Positive Observations

- `hmac.compare_digest` used correctly for timing-safe token comparison.
- Consistent graceful-degradation pattern — DB/memory/observability failures never surface as 500s to callers (except the `WebhookSkippedResponse` bug).
- Pydantic models for all request/response shapes — clean API contract documentation.
- `asyncio.gather` for parallel embedding generation in `store_turn_pair` — good async hygiene.
- `lru_cache` on `get_graph()` and `load_identity()` — avoids redundant initialization.
- YAML parsed with `yaml.safe_load` — no arbitrary code execution from config file.
- No secrets appear in log lines (auth token, LLM key, DB password not logged directly).

---

## Recommended Actions (Priority Order)

1. **Fix `WebhookSkippedResponse()` instantiation** — add `reason="sender_is_agent"` or give `reason` a default. Immediate API breakage.
2. **Fix sandbox `startswith` check** — append `/` to sandbox path before comparison.
3. **Add empty-token guard in `auth.py`** — assert `settings.auth_token` is non-empty at startup.
4. **Wire `ToolGuardrails` into the graph** — instantiate per-request and check before each tool node execution.
5. **Fix `tc.function.arguments` deserialization** — `json.loads()` before passing to `AIMessage`.
6. **Fix embedding model config** — pass `api_key`/`api_base` from settings, or make embedding model/provider configurable.
7. **Document or fix `MemorySaver` single-worker constraint**.
8. **Remove dead `routing/litellm.py`** or wire it in and remove the duplicate in `nodes.py`.
9. **Add file size limit to `file_write` tool**.
10. **Add similarity threshold to `retrieve_user_facts`**.

---

## Metrics

| Metric | Value |
|---|---|
| Files reviewed | 17 |
| Approx LOC | ~700 |
| Critical issues | 2 |
| High priority | 4 |
| Medium priority | 6 |
| Low priority | 5 |
| Dead code modules | 1 (`routing/litellm.py`) |

---

## Unresolved Questions

- Is `routing/litellm.py` intentionally kept for future use, or is it truly dead code?
- Is `ToolGuardrails` planned for Phase 3 wiring, or was it inadvertently left disconnected?
- What embedding provider is intended for non-OpenAI deployments (DeepSeek has no embedding API)?
- Is multi-worker deployment a target? If yes, `MemorySaver` must be replaced before launch.

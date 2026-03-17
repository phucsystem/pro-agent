# Phase 4: Structured Output + Model Routing + Cost Tracking

## Context Links
- [SRD.md](../../docs/SRD.md) — FR-15, FR-16, FR-17
- [API_SPEC.md](../../docs/API_SPEC.md) — §4.6 Output Validator, §4.7 Model Router, §4.5 Cost Tracking
- [UI_SPEC.md](../../docs/UI_SPEC.md) — §4 agent.yaml config structure

## Overview
- **Priority:** P3
- **Status:** ✅ Complete
- **Effort:** 4h
- **FRs:** FR-15 (Structured Output), FR-16 (Multi-Model Routing), FR-17 (Cost Tracking)

Add Pydantic output validation, LiteLLM-based multi-model routing, and per-request cost tracking. By end of this phase: agent validates outputs against schemas, routes to different LLM providers, and tracks costs in Langfuse + /health endpoint.

## Key Insights
- LiteLLM already used for embedding (Phase 2) — extend to chat completions
- Structured output: validate AFTER LLM response, don't force output format (fallback to raw text)
- Cost = LLM tokens cost + tool call costs (from Phase 3)
- LiteLLM has built-in token counting + model pricing — leverage it
- Model routing via agent.yaml config, not per-request (keep simple for prototype)

## Requirements

**Functional:**
- FR-15: Pydantic schemas for common response types, validate LLM output, fallback to raw text
- FR-16: LiteLLM routes to Claude/GPT/DeepSeek/Ollama based on agent.yaml config
- FR-17: Track tokens in/out, calculate cost, log to Langfuse, expose in /health

**Non-Functional:**
- NFR-03: Average cost per medium task < $0.50, tracking accurate ±5%

## Architecture

```
app/
├── output/
│   ├── __init__.py
│   ├── schemas.py       # Pydantic output schemas (GeneralReply, ResearchReport, etc.)
│   └── validator.py     # Validate LLM output against schemas, fallback logic
├── routing/
│   ├── __init__.py
│   └── litellm.py       # LiteLLM wrapper, model config, cost extraction
└── main.py              # MODIFY: add cost_stats to /health
```

## Related Code Files

**Create:**
- `app/output/__init__.py`
- `app/output/schemas.py` — Pydantic output models
- `app/output/validator.py` — output validation + fallback
- `app/routing/__init__.py`
- `app/routing/litellm.py` — LiteLLM chat completion wrapper + cost tracking

**Modify:**
- `app/agent/nodes.py` — use LiteLLM wrapper instead of direct ChatOpenAI
- `app/main.py` — add cost_stats to /health response
- `app/observability/langfuse.py` — log cost metadata per trace
- `requirements.txt` — ensure `litellm` version supports cost tracking

## Implementation Steps

### 1. Create app/routing/litellm.py

```python
import litellm
from litellm import completion, completion_cost

class LLMRouter:
    def __init__(self, config):
        self.provider = config.model.provider
        self.model = config.model.name
        self.api_key = config.llm_api_key
        self.base_url = config.llm_base_url
        self.temperature = config.model.temperature
        self.max_tokens = config.model.max_tokens

    async def chat(self, messages, tools=None) -> tuple[str, dict]:
        """Call LLM via LiteLLM. Return (response, usage_info).
        usage_info = { tokens_in, tokens_out, cost_usd, model }
        """
        response = await litellm.acompletion(
            model=self.model,
            messages=messages,
            api_key=self.api_key,
            api_base=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            tools=tools,
        )

        usage = response.usage
        cost = completion_cost(completion_response=response)

        usage_info = {
            "tokens_in": usage.prompt_tokens,
            "tokens_out": usage.completion_tokens,
            "cost_usd": cost,
            "model": self.model,
        }

        return response.choices[0].message, usage_info
```

### 2. Create app/output/schemas.py

```python
from pydantic import BaseModel, Field

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
    issues: list[dict] = []
    suggestions: list[str] = []
    overall_quality: str = "good"
```

### 3. Create app/output/validator.py

```python
import json
from pydantic import ValidationError

async def validate_output(raw_text: str, schema_class=None):
    """Try to validate LLM output against Pydantic schema.
    Return (validated_dict, is_structured).
    On failure: return ({"content": raw_text}, False).
    """
    if not schema_class:
        return {"content": raw_text}, False

    try:
        parsed = json.loads(raw_text)
        validated = schema_class.model_validate(parsed)
        return validated.model_dump(), True
    except (json.JSONDecodeError, ValidationError):
        return {"content": raw_text}, False
```

### 4. Modify app/agent/nodes.py — use LLMRouter

Replace direct ChatOpenAI with LLMRouter:
```python
# Before: model = ChatOpenAI(...)
# After:
router = get_llm_router()  # singleton from config
response, usage_info = await router.chat(messages, tools=tools)
# Store usage_info in state for cost tracking
```

### 5. Track per-request cost

In main.py /chat handler, accumulate costs:
```python
total_cost = usage_info["cost_usd"]
# Add tool call costs from Phase 3 logger
tool_costs = sum(tc.cost for tc in tool_calls)
total_cost += tool_costs

# Log to Langfuse trace
if langfuse_handler:
    langfuse_handler.trace.update(metadata={"cost_usd": total_cost})
```

### 6. Update /health with cost_stats

```python
# Query from tool_call_logs + add LLM costs
cost_stats = {
    "total_tool_cost_usd": await get_total_tool_cost(),
    "total_requests": await get_total_request_count(),
}
# Add to health response
```

### 7. Test structured output + routing + cost

- Send message → verify response, check LiteLLM routes to configured model
- Change model in agent.yaml → verify routing changes
- Check Langfuse trace includes cost metadata
- Verify /health shows cost_stats
- Test structured output: prompt that should return JSON → validate against schema
- Test fallback: ambiguous response → falls back to raw text (no error)

## Todo List

- [ ] Create app/routing/litellm.py — LLM router wrapper
- [ ] Create app/output/schemas.py — Pydantic output models
- [ ] Create app/output/validator.py — validation + fallback
- [ ] Modify app/agent/nodes.py — use LLMRouter
- [ ] Add per-request cost tracking in /chat handler
- [ ] Update /health with cost_stats
- [ ] Log cost metadata to Langfuse traces
- [ ] Test: LiteLLM routing to different providers
- [ ] Test: structured output validation + fallback
- [ ] Test: cost tracking accuracy

## Success Criteria

- LiteLLM routes to configured model provider (verify via Langfuse trace)
- Structured output validates against Pydantic schema > 95% when format is correct
- Fallback to raw text works without errors when output doesn't match schema
- Per-request cost tracked and logged to Langfuse
- /health shows aggregate cost stats
- Cost tracking accurate to ±5% (compare LiteLLM reported cost vs manual calculation)

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LiteLLM cost calculation wrong for some models | Inaccurate tracking | Verify against provider billing dashboard, add manual cost override in config |
| Structured output forces awkward LLM responses | Worse quality | Only validate, never force format; fallback to raw text |
| LiteLLM version compatibility | API breaks | Pin version in requirements.txt |

## Security Considerations
- LLM API keys routed through LiteLLM — ensure no key leakage in logs
- Cost cap enforcement: if total cost exceeds max_per_request, stop tool calls

## Next Steps
- All 4 phases complete → run eval suite → document results → go/no-go for Tier 3

# TODOS

Deferred work items from engineering review (2026-03-20).

## TODO-1: Copier Template Layer

**What:** Wrap the boilerplate in a `copier` project template with variables for agent_name, llm_provider, table_prefix, etc.
**Why:** Currently forking requires manually find-replacing 'Pro Agent' and 'pro-agent' across 10+ files. A template makes forking a 1-command operation.
**Pros:** Dramatically lowers barrier to reuse. Makes the 'boilerplate' claim real.
**Cons:** Adds template syntax complexity. Needs maintenance when new config is added.
**Context:** The codebase has 'pro-agent' hardcoded in agent.yaml, docker-compose.yml, SOUL.md, and config defaults. copier preferred over cookiecutter (supports updates).
**Depends on:** All boilerplate fixes (1A–9A) complete first.
**Priority:** P2

## TODO-2: Data Retention / Archival Policy

**What:** Add configurable retention period (`MEMORY_RETENTION_DAYS=90`) and cleanup task for old conversation_turns and user_facts.
**Why:** Turns accumulate indefinitely. At 100+ msgs/day = 36k+ rows/year with embeddings. Vector search degrades, storage grows, HNSW index rebuilds slow down.
**Pros:** Keeps DB lean. Prevents silent performance degradation over months.
**Cons:** Adds background task (cron or startup cleanup). Users may want different policies.
**Context:** No TTL, no archival, no cleanup currently. `created_at` column exists on all tables — filtering by age is trivial.
**Depends on:** HNSW indexes (issue 3A) in place first.
**Priority:** P3

## TODO-3: Full Test Suite (Expand from Skeleton)

**What:** Complete test suite covering all branches: memory store/retrieve, tool execution + guardrails, LLM response handling, webhook agent-skip, structured output validation. ~15 additional test cases.
**Why:** Skeleton tests cover auth + /health + config only. Remaining tests cover the agent's core value (memory, tools, routing). Without them, pipeline modifications are untested.
**Pros:** Full safety net for forkers. Example tests teach how to test LLM-based code.
**Cons:** ~30min CC time. Needs mock strategies for LLM + DB.
**Context:** Deferred from eng review issue 8. Should be done before publicizing as boilerplate.
**Depends on:** Skeleton tests (8B) and all code fixes (1A–7A) complete.
**Priority:** P2

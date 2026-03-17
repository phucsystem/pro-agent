---
title: "Pro Agent (Tier 2) Implementation"
description: "Build Pro Agent with long-term memory (pgai), MCP tool use, structured output, and multi-model routing — drop-in upgrade from Dumb Agent"
status: completed
priority: P1
effort: 20h
branch: main
tags: [backend, api, ai-agent, python, fastapi, langgraph]
created: 2026-03-18
completed: 2026-03-18
---

# Pro Agent (Tier 2) Implementation Plan

## Overview

Build a Python/FastAPI agent that upgrades the Dumb Agent with:
1. Persistent long-term memory via PostgreSQL + pgai (semantic search)
2. MCP tool use (web search, GitHub, file I/O) with guardrails
3. Structured output (Pydantic) + multi-model routing (LiteLLM) + cost tracking

Must be a **drop-in replacement** for the Dumb Agent — identical `/chat`, `/webhook`, `/health` API contracts. Same bearer token auth, same Docker deployment pattern.

## Docs Reference

- [SRD.md](../../docs/SRD.md) — 17 FRs, 4 entities, 7 NFRs
- [UI_SPEC.md](../../docs/UI_SPEC.md) — API contracts, integration patterns, config interface
- [API_SPEC.md](../../docs/API_SPEC.md) — Endpoint details, internal components, request lifecycle
- [DB_DESIGN.md](../../docs/DB_DESIGN.md) — Schema DDL, queries, embedding strategy

## Phases

| # | Phase | Status | Effort | FRs | Link |
|---|-------|--------|--------|-----|------|
| 1 | Project scaffold + Docker + DB | ✅ Complete | 4h | FR-01, FR-04, FR-05 | [phase-01](./phase-01-scaffold-docker-db.md) |
| 2 | Core agent + memory + endpoints | ✅ Complete | 6h | FR-02, FR-03, FR-06, FR-07, FR-08 | [phase-02](./phase-02-core-agent-memory.md) |
| 3 | MCP tool use + guardrails + logging | ✅ Complete | 6h | FR-09–FR-14 | [phase-03](./phase-03-tool-use.md) |
| 4 | Structured output + model routing + cost | ✅ Complete | 4h | FR-15, FR-16, FR-17 | [phase-04](./phase-04-structured-output-routing.md) |

## Dependencies

```
Phase 1 → Phase 2 → Phase 3 → Phase 4
(sequential — each phase builds on the previous)
```

## Key Constraints

- Python 3.12+, FastAPI, LangGraph (Python)
- PostgreSQL + pgai (timescale/timescaledb-ha:pg17)
- Must match Dumb Agent API contract exactly (backward compat)
- Webhook contract identical (Typebot/n8n zero-migration)
- Bearer token auth, timing-safe comparison
- SOUL.md + agent.yaml for identity/config

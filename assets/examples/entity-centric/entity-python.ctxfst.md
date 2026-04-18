---
title: "Python (Entity File)"
entities:
  - id: entity:python
    name: Python
    type: skill
    aliases: [py, python3]
chunks:
  - id: skill:python-core
    tags: [Python, Language, Async]
    entities: [entity:python]
    context: "Core Python usage — async, testing, performance profiling, package management"
    created_at: "2026-04-18"
    version: 1
    priority: high
  - id: skill:python-with-fastapi
    tags: [Python, FastAPI, API]
    entities: [entity:python, entity:fastapi]
    context: "Python paired with FastAPI to build REST endpoints with async handlers"
    created_at: "2026-04-18"
    version: 1
    priority: medium
    dependencies: [skill:python-core]
---

# Python

<Chunk id="skill:python-core">
## Core usage

I use Python daily for data pipelines, CLI tooling, and small services.

Preferred workflow:
- `uv` for dependency and virtualenv management
- `pytest` for testing, with `pytest-asyncio` when async code is involved
- `pyright` for type checking
- `asyncio` for concurrency work when the workload is I/O bound
</Chunk>

<Chunk id="skill:python-with-fastapi">
## Paired with FastAPI

When the service is a REST API, Python pairs with FastAPI (see [entity-fastapi.ctxfst.md](./entity-fastapi.ctxfst.md)).

FastAPI's Pydantic-based validation and dependency injection make it the default choice over Flask for new projects. Async handlers stay Python-native, so the skill carries over without a new mental model.
</Chunk>

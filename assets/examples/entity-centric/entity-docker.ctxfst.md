---
title: "Docker (Entity File)"
entities:
  - id: entity:docker
    name: Docker
    type: tool
    aliases: []
chunks:
  - id: tool:docker-packaging
    tags: [Docker, Packaging, Images]
    entities: [entity:docker]
    context: "Docker as the packaging layer for Python services"
    created_at: "2026-04-18"
    version: 1
    priority: high
  - id: tool:docker-fastapi-images
    tags: [Docker, FastAPI, Deployment]
    entities: [entity:docker, entity:fastapi]
    context: "Docker image conventions used for FastAPI services in this stack"
    created_at: "2026-04-18"
    version: 1
    priority: medium
---

# Docker

<Chunk id="tool:docker-packaging">
## Packaging layer

Docker is the packaging layer: one service, one image, one entrypoint.

Conventions:
- Multi-stage builds when the build environment differs from the runtime
- Non-root user inside the container
- `.dockerignore` mirrors `.gitignore` plus build artefacts
- Tags follow `<service>:<git-sha>` for traceability
</Chunk>

<Chunk id="tool:docker-fastapi-images">
## Images for FastAPI services

For FastAPI services (see [entity-fastapi.ctxfst.md](./entity-fastapi.ctxfst.md)), the image pattern is:

1. `python:3.12-slim` base
2. Install with `uv sync --frozen`
3. Copy application code last (to maximise layer cache hits on dependency-only changes)
4. `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`
</Chunk>

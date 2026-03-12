---
title: "World Model Example — Kubernetes Learning Path"
entities:
  - id: entity:docker
    name: Docker
    type: skill
    aliases: []
  - id: entity:kubernetes
    name: Kubernetes
    type: skill
    aliases: [K8s]
  - id: entity:ian-chou
    name: Ian Chou
    type: agent
    aliases: []
  - id: entity:learn-kubernetes-path
    name: Learn Kubernetes Path
    type: goal
    aliases: []
  - id: entity:analyze-resume
    name: Analyze Resume
    type: action
    preconditions:
      - "entity:has-raw-resume"
    postconditions:
      - "entity:has-parsed-resume"
      - "entity:has-skill-evidence"
    related_skills:
      - "analyze-resume"
  - id: entity:has-raw-resume
    name: Has Raw Resume
    type: state
    aliases: []
  - id: entity:has-parsed-resume
    name: Has Parsed Resume
    type: state
    aliases: []
  - id: entity:has-skill-evidence
    name: Has Skill Evidence
    type: state
    aliases: []
  - id: entity:docker-3yr-experience
    name: Docker 3yr Experience
    type: evidence
    aliases: []
chunks:
  - id: skill:docker-overview
    tags: [Docker, Containers]
    entities: [entity:docker]
    context: "Docker container runtime skills including image building and orchestration basics"
    created_at: "2026-03-12"
    version: 1
    type: text
    priority: high
    dependencies: []
  - id: skill:kubernetes-overview
    tags: [Kubernetes, Orchestration]
    entities: [entity:kubernetes, entity:docker]
    context: "Kubernetes container orchestration skills building on Docker foundation"
    created_at: "2026-03-12"
    version: 1
    type: text
    priority: high
    dependencies: [skill:docker-overview]
  - id: action:resume-analysis
    tags: [Resume, Analysis]
    entities: [entity:analyze-resume, entity:ian-chou]
    context: "Resume analysis action that extracts skill evidence from raw resume documents"
    created_at: "2026-03-12"
    version: 1
    type: text
    priority: critical
    dependencies: []
    state_refs: [entity:has-raw-resume, entity:has-parsed-resume]
---

<Chunk id="skill:docker-overview">
## Docker Skills

Hands-on experience with Docker for containerization:
- Building and managing Docker images and Dockerfiles
- Docker Compose for multi-container applications
- Container networking and volume management
- CI/CD pipeline integration with Docker
</Chunk>

<Chunk id="skill:kubernetes-overview">
## Kubernetes Skills

Kubernetes orchestration skills built on Docker foundation:
- Pod management and deployment strategies
- Service discovery and load balancing
- ConfigMaps, Secrets, and resource management
- Helm charts for application packaging
</Chunk>

<Chunk id="action:resume-analysis">
## Resume Analysis Action

This action parses a raw resume document and extracts structured skill evidence.

**Precondition**: A raw resume document must be available (entity:has-raw-resume).
**Postcondition**: Produces parsed resume (entity:has-parsed-resume) and skill evidence (entity:has-skill-evidence).

The output includes confidence scores for each identified skill and years of experience.
</Chunk>

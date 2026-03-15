---
title: "CH22 Retrieval Benchmark Notes"
entities:
  - id: entity:go
    name: Go
    type: skill
    aliases: [golang]
  - id: entity:grpc
    name: gRPC
    type: protocol
    aliases: []
  - id: entity:docker
    name: Docker
    type: tool
    aliases: []
  - id: entity:kubernetes
    name: Kubernetes
    type: platform
    aliases: [k8s]
  - id: entity:postgresql
    name: PostgreSQL
    type: database
    aliases: [postgres]
  - id: entity:rocksdb
    name: RocksDB
    type: database
    aliases: []
  - id: entity:database-systems
    name: Database Systems
    type: domain
    aliases: [databases, storage systems]
  - id: entity:backend-engineering
    name: Backend Engineering
    type: domain
    aliases: [backend]
  - id: entity:service-deployment
    name: Service Deployment
    type: domain
    aliases: [deployment, infra]
  - id: entity:openai
    name: OpenAI
    type: product
    aliases: []
  - id: entity:tool-calling
    name: Tool Calling
    type: concept
    aliases: []
  - id: entity:planning-loop
    name: Planning Loop
    type: concept
    aliases: [planner]
  - id: entity:graph-aware-retrieval
    name: Graph-Aware Retrieval
    type: concept
    aliases: [entity-aware retrieval]
chunks:
  - id: skill:go-service-runtime
    tags: [Go, gRPC, Services, Concurrency]
    entities: [entity:go, entity:grpc, entity:backend-engineering]
    context: "Go service notes focused on gRPC, concurrency, and runtime behavior under load"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: high
    dependencies: []
  - id: workflow:deployment-stack
    tags: [Docker, Kubernetes, Deployment]
    entities: [entity:docker, entity:kubernetes, entity:service-deployment]
    context: "Deployment notes that treat Docker and Kubernetes as one connected stack"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: medium
    dependencies: []
  - id: reference:database-tradeoffs
    tags: [PostgreSQL, RocksDB, Storage, Indexing]
    entities: [entity:postgresql, entity:rocksdb, entity:database-systems]
    context: "Database notes comparing transactional systems, embedded stores, indexing, WAL, and compaction"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: high
    dependencies: []
  - id: workflow:agent-runtime
    tags: [OpenAI, Tool Calling, Planning, Retrieval]
    entities: [entity:openai, entity:tool-calling, entity:planning-loop, entity:graph-aware-retrieval]
    context: "Agent runtime notes connecting tool calling, planning loops, and retrieval quality"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: medium
    dependencies: []
  - id: project:service-platform
    tags: [Project, Go, PostgreSQL, Kubernetes]
    entities: [entity:go, entity:grpc, entity:postgresql, entity:kubernetes, entity:backend-engineering, entity:service-deployment]
    context: "Project ledger entry for a service platform using Go, gRPC, PostgreSQL, and Kubernetes"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: high
    dependencies: []
  - id: project:embedded-analysis-store
    tags: [Project, RocksDB, Storage]
    entities: [entity:rocksdb, entity:database-systems]
    context: "Project ledger entry for an analysis pipeline built around an embedded storage engine"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: medium
    dependencies: []
  - id: about:backend-summary
    tags: [Backend, API, Storage, Deployment]
    entities: [entity:backend-engineering, entity:go, entity:grpc, entity:postgresql, entity:rocksdb, entity:docker, entity:kubernetes]
    context: "High-level summary of backend experience across service, storage, and deployment topics"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: medium
    dependencies: []
  - id: principle:retrieval-gap
    tags: [Retrieval, Benchmark, Entity Graph]
    entities: [entity:graph-aware-retrieval, entity:backend-engineering, entity:database-systems]
    context: "Why literal wording alone misses useful notes when concepts are distributed across multiple files"
    created_at: "2026-03-15"
    version: 1
    type: text
    priority: medium
    dependencies: []
---

# CH22 Retrieval Benchmark Notes

<Chunk id="skill:go-service-runtime">
## Go service runtime notes

I used Go to build internal gRPC services where latency mattered more than framework ergonomics.

The useful lesson was not just that Go is fast. It was that the language made concurrency behavior easier to reason about when a service had to multiplex work under load.

Most of the deployment work for these services later moved into containers and Kubernetes, even when the original note was mainly about service runtime design.
</Chunk>

<Chunk id="workflow:deployment-stack">
## Docker and Kubernetes as one deployment stack

My deployment notes started from Docker basics and then gradually shifted toward Kubernetes.

Docker gave me the packaging layer. Kubernetes gave me the scheduling, rollout, and service-discovery layer that made multiple services manageable together.

In practice I usually wrote about them as one deployment stack instead of as isolated tools.
</Chunk>

<Chunk id="reference:database-tradeoffs">
## Storage and database tradeoffs

When I wrote about databases, I often meant very different things under one umbrella: PostgreSQL for transactional application data, and RocksDB for embedded storage engines.

The interesting part was comparing indexing, write amplification, transaction behavior, WAL tuning, and compaction strategy.

Some notes only mention those lower-level details without repeating the higher-level category word database.
</Chunk>

<Chunk id="workflow:agent-runtime">
## Agent runtime notes

My recent work shifted toward OpenAI tool calling, planning loops, and graph-aware execution.

I usually grouped these ideas under agent runtime rather than under any one vendor API, because the main concern was how tools, memory, and planner state fit together.

These notes connect back to retrieval because the planner behaves better when the knowledge layer returns conceptually related chunks instead of only textually similar ones.
</Chunk>

<Chunk id="project:service-platform">
## Project ledger: service platform

One side project combined a Go API layer, gRPC between services, PostgreSQL for the main data model, and a Kubernetes deployment target.

The note was written like a project journal entry, so it did not explicitly label itself as backend engineering or service deployment, even though that is what the work clearly represents.
</Chunk>

<Chunk id="project:embedded-analysis-store">
## Project ledger: embedded analysis pipeline

Another experiment used RocksDB inside a local analysis pipeline because I wanted a lightweight embedded store without running a full separate database service.

This note mostly talks about storage behavior and system shape, not the broad category word database.
</Chunk>

<Chunk id="about:backend-summary">
## Backend experience summary

If I summarize my backend experience at a high level, it includes API design, service decomposition, deployment workflows, and storage tradeoffs.

The concrete technologies are spread across different notes: Go and gRPC on the service side, PostgreSQL and RocksDB on the storage side, and Docker plus Kubernetes on the deployment side.

That spread is exactly why a retrieval system based only on literal wording tends to miss useful supporting chunks.
</Chunk>

<Chunk id="principle:retrieval-gap">
## Why literal wording is not enough

The retrieval problem here is not that pure vector search never finds anything useful. It often retrieves high-level summary chunks first.

The gap is that many relevant notes are written as project logs, lower-level implementation details, or adjacent concepts. Entity-aware retrieval has a chance to recover those chunks because it can move through canonical concepts such as backend engineering, database systems, or graph-aware retrieval.
</Chunk>


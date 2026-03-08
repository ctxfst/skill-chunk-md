# Entity Format Reference

Complete reference for the **entity** schema used in CtxFST documents. Entities are the canonical concept layer for GraphRAG: they give chunks a stable, typed identity and enable navigation and traversal.

---

## 1. Where entities live

Entities are **document-level**. They are defined once in the YAML frontmatter under the top-level key `entities:`, alongside `chunks:`.

```yaml
---
title: "Document Title"
entities:
  - id: entity:python
    name: Python
    type: skill
    aliases: [python3]
chunks:
  - id: skill:python-api
    entities: [entity:python, entity:fastapi]
---
```

Each entity is defined once per document. Chunks reference them by `id` in their `entities` array.

---

## 2. Fields per entity

Each entity is one YAML object with the following fields.

| Field      | Required | Type     | Description |
|-----------|----------|----------|-------------|
| `id`      | Yes      | string   | Unique identifier; format below |
| `name`    | Yes      | string   | Human-readable canonical name |
| `type`    | Yes      | string   | Concept type from the allowed list |
| `aliases` | No       | string[] | Alternative spellings or abbreviations |

---

## 3. `id` format

- **Pattern**: `entity:{canonical-name}`
- **Rules**:
  - Prefix is always `entity:` (lowercase).
  - The part after the colon is **lowercase kebab-case** (words joined by `-`).
  - Must be **unique within the document**.

**Examples**:

| Concept                    | Correct id                         | Wrong |
|---------------------------|-------------------------------------|--------|
| Python                    | `entity:python`                    | `entity:Python` |
| FastAPI                   | `entity:fastapi`                   | `entity:FastAPI` |
| PostgreSQL                | `entity:postgresql`                | `entity:PostgreSQL` |
| Event-Driven Architecture | `entity:event-driven-architecture` | `entity:Event Driven Architecture` |
| CI/CD                     | `entity:ci-cd`                     | `entity:CI/CD` |

The `id` is the stable machine key; `name` is for display.

---

## 4. `name` format

- **Type**: string.
- **Convention**: Use the most recognizable formal name (capitalization, spaces, slashes as in common usage).

Examples: `FastAPI`, `CI/CD`, `Event-Driven Architecture`.

This is what you show in UIs, reports, or graph node labels.

---

## 5. `type` (allowed values)

`type` must be exactly one of the following. It classifies the concept for filtering and graph semantics.

| type           | Use for                         | Example entities |
|----------------|----------------------------------|------------------|
| `skill`        | Skills, languages, competencies | Python, SQL, System Design |
| `tool`         | Tools, CLIs, runtimes           | Docker, Git, Redis |
| `library`      | Libraries, packages             | Pandas, Lodash, axios |
| `framework`    | Frameworks                      | FastAPI, React, Spring |
| `platform`     | Platforms, clouds, orchestrators| AWS, Vercel, Kubernetes |
| `database`     | Databases                       | PostgreSQL, MongoDB |
| `architecture`| Architectures, patterns         | Event-Driven, Microservices |
| `protocol`     | Protocols, standards            | HTTP, JWT, gRPC |
| `concept`      | Generic concepts                | Caching, Indexing |
| `domain`       | Domains, areas                  | DevOps, Frontend |
| `product`      | Products, systems               | Stripe, Notion |

If none fit well, use `concept` rather than inventing many custom types.

---

## 6. `aliases` format

- **Type**: array of strings.
- **Purpose**: Other ways the same concept appears in text (e.g. K8s → Kubernetes). Used for matching and normalization.
- **Optional**: Use `aliases: []` or omit.

**Example**:

```yaml
- id: entity:kubernetes
  name: Kubernetes
  type: platform
  aliases: [K8s, k8s]

- id: entity:javascript
  name: JavaScript
  type: skill
  aliases: [JS, js]
```

---

## 7. Full YAML example

```yaml
---
title: "Backend Skills"
entities:
  - id: entity:python
    name: Python
    type: skill
    aliases: [python3, py]

  - id: entity:fastapi
    name: FastAPI
    type: framework
    aliases: []

  - id: entity:postgresql
    name: PostgreSQL
    type: database
    aliases: [postgres, psql]

  - id: entity:event-driven-architecture
    name: Event-Driven Architecture
    type: architecture
    aliases: [EDA, event-driven]

chunks:
  - id: skill:python-api
    tags: [Python, Backend]
    entities: [entity:python, entity:fastapi]
    context: "Python REST API development with FastAPI"
---
```

---

## 8. How chunks reference entities

Inside `chunks`, each chunk may have:

- **Field**: `entities`
- **Type**: array of strings
- **Values**: Must be `id`s of entities defined in the same document’s `entities` list.

```yaml
chunks:
  - id: skill:python-api
    entities: [entity:python, entity:fastapi]
```

- Chunks that do not discuss specific entities can omit `entities` or use `entities: []`.
- Typically list 1–6 entities per chunk; only those the chunk actually discusses.

---

## 9. How entity similarity is produced

The CtxFST entity schema does **not** store similarity scores directly. It stores the canonical node inventory that downstream systems use to compute an entity embedding graph.

In other words:

- `entities[]` defines **which nodes exist**
- `chunks[].entities` defines **which chunks link to which nodes**
- embeddings or graph algorithms define **which nodes are similar**

Typical pipeline:

```text
entities[] + linked chunks
  -> build a text representation for each entity
  -> embed each representation
  -> compare vectors with cosine similarity
  -> create Entity -> Entity edges above a threshold
```

Two common strategies:

1. **Metadata-only embedding**
   - Embed `name`, `type`, and `aliases`
2. **Chunk-enriched embedding**
   - Embed `name`, `type`, and summaries from chunks linked through `chunks[].entities`

Chunk-enriched representations usually produce better graph structure because they reflect how an entity is used in the source documents.

---

## 10. Translating to a Graph Database

When loading CtxFST data into Neo4j, Lance Graph, or HelixDB, the schema maps directly to graph primitives:

1. **`entities[]` items** 👉 become `(Node:Entity)`
2. **`chunks[]` items** 👉 become `(Node:Chunk)`
3. **`chunks[].entities`** 👉 become `(Chunk)-[:MENTIONS]->(Entity)` edges

*(Similarity edges between entities are then computed by the graph DB or an external embedding pipeline).*

---

## 11. Quick reference

| Item              | Rule |
|-------------------|------|
| **Where**        | Top-level `entities:` array in frontmatter |
| **Required**     | `id`, `name`, `type` |
| **Optional**     | `aliases` |
| **id format**    | `entity:` + lowercase kebab-case; unique per document |
| **type values**  | skill, tool, library, framework, platform, database, architecture, protocol, concept, domain, product |
| **Chunk link**   | `chunks[].entities: [entity:id, ...]`; every id must exist in `entities` |

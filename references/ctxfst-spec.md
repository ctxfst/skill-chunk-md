# CtxFST Specification (v2.0)

CtxFST is a **semantic world model format** for agent-ready knowledge graphs. It represents knowledge as structured chunks with an entity layer that captures both descriptive relationships (what things are) and operational relationships (how things depend on, lead to, and block each other).

A CtxFST document supports:
- **Vector search** via chunk context and content
- **Graph traversal** via entity nodes and multi-relation edges
- **Agent execution** via preconditions, postconditions, and world state tracking

A formal JSON Schema is available at [`schema.json`](../schema.json).

---

## 1. Design Principles

1. **World model first** — Entities are not an optional addon; they are the semantic backbone that gives chunks meaning in a graph.
2. **Strict superset** — Every valid v1.x document is a valid v2.0 document. Parsers that only need chunks still work.
3. **Operational graph** — Entities can represent not just skills and tools, but also states, actions, goals, agents, and evidence — everything an agent needs to plan and execute.
4. **Multi-relation edges** — The entity graph supports similarity, causal, prerequisite, and completion edges, enabling both retrieval and planning.

---

## 2. Document Structure

A valid CtxFST document consists of:
1. **YAML Frontmatter**: Bounded by `---`, containing entities, chunks, and metadata.
2. **Markdown Body**: Bounded by `<Chunk id="...">` tags, containing the textual passages.

---

## 3. Top-Level Schema (The Export JSON)

When compiled to JSON (via `scripts/export_to_lancedb.py`):

| Field | Required? | Description |
|-------|-----------|-------------|
| `chunks` | **Required** | Array of semantic passages. |
| `entities` | Recommended | Canonical entity catalog — the graph nodes. |
| `title` | Optional | Human-readable document title. |

Parsers **MUST NOT** crash on unknown top-level keys.

---

## 4. Entity Schema (`entities[]`)

Entities are the semantic backbone of the world model. They define the concepts, states, actions, and relationships that give chunks meaning.

| Field | Required? | Type | Description |
|-------|-----------|------|-------------|
| `id` | **Required** | string | Unique ID. Format: `entity:kebab-case`. |
| `name` | **Required** | string | Human-readable name (e.g., `FastAPI`). |
| `type` | **Required** | enum | Ontological category (see below). |
| `aliases` | Optional | string[] | Alternative names (e.g., `['K8s']`). |
| `preconditions` | Recommended | string[] | State entity IDs that must exist before this entity is actionable. |
| `postconditions` | Recommended | string[] | State entity IDs created/updated when this entity completes. |
| `related_skills` | Optional | string[] | Associated SKILL.md file names. |

### Entity Types

#### Descriptive Types
For representing knowledge:
`skill`, `tool`, `library`, `framework`, `platform`, `database`, `architecture`, `protocol`, `concept`, `domain`, `product`.

#### Operational Types
For representing world model state and actions:

| Type | Purpose | Example |
|------|---------|---------|
| `state` | World state condition | `entity:resume-parsed` |
| `action` | Executable operation | `entity:analyze-resume` |
| `goal` | Task objective | `entity:learn-kubernetes-path` |
| `agent` | Actor or user | `entity:ian-chou` |
| `evidence` | Observed result | `entity:docker-3yr-experience` |

---

## 5. Chunk Schema (`chunks[]`)

Chunks carry context and content for vector retrieval.

| Field | Required? | Type | Description |
|-------|-----------|------|-------------|
| `id` | **Required** | string | Unique chunk ID. Format: `category:topic`. |
| `context` | **Required** | string | 50-100 word summary for the LLM context window. |
| `content` | **Required** | string | Raw passage from the `<Chunk>` tags. |
| `tags` | Optional | string[] | Filterable metadata strings. |
| `entities` | Recommended | string[] | Entity IDs this chunk mentions. Defines `MENTIONS` edges. |
| `state_refs` | Optional | string[] | State entity IDs this chunk is relevant to. |
| `created_at` | Optional | date | ISO 8601 date for temporal sorting. |
| `version` | Optional | int | Incrementing state tracker. |
| `priority` | Optional | enum | `low`, `medium`, `high`, `critical`. |
| `dependencies` | Optional | string[] | Chunk IDs required before reading this one. |

### Validation Rules
- `chunks[].entities`: Every ID **MUST** match a top-level `entities[].id`.
- `chunks[].state_refs`: Every ID **SHOULD** match a `state`-type entity.

---

## 6. Entity Graph Edge Relations

The entity graph supports multiple edge types for both retrieval and world model planning.

### Auto-Computed Edges
| Relation | Method | Semantic |
|----------|--------|----------|
| `SIMILAR` | TF-IDF cosine | Co-occurrence similarity between entities |
| `REQUIRES` | Inferred from `postconditions → preconditions` | Prerequisite dependency |
| `LEADS_TO` | Inferred from `postconditions → preconditions` | Causal successor |

### Manual / Runtime Edges
| Relation | Source | Semantic |
|----------|--------|----------|
| `EVIDENCE` | Runtime | Observed evidence linking agent to skill |
| `IMPLIES` | Manual | Logical entailment |
| `COMPLETED` | Runtime | Execution completion record |
| `BLOCKED_BY` | Runtime | Blocking dependency |

### Edge Properties (Optional)
| Property | Type | Description |
|----------|------|-------------|
| `score` | number | Similarity or confidence score |
| `timestamp` | ISO 8601 | When the edge was created/updated |
| `confidence` | number (0.0–1.0) | Certainty of the relationship |
| `result_summary` | string | Brief result description |
| `status` | enum | `active`, `expired`, `failed` |

---

## 7. World State (Runtime)

A `world-state.json` file tracks runtime session state for agent execution loops:

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | UUID for the session |
| `goal` | string | Target goal entity ID |
| `active_states` | string[] | Currently active state entity IDs |
| `completed_skills` | object[] | Executed skills with timestamps and results |
| `current_subgraph` | object | Goal-relevant nodes and edges |

See [`world-state-schema.json`](../world-state-schema.json) for the formal schema.

---

## 8. SKILL.md World Model Fields

SKILL.md files that participate in the world model include:

| Field | Type | Description |
|-------|------|-------------|
| `preconditions` | string[] | State entities required before execution |
| `postconditions` | string[] | State entities produced after execution |
| `related_nodes` | string[] | Graph anchor points |
| `related_skills` | string[] | Sequential/complementary skills |
| `cost` | enum | `low`, `medium`, `high` |
| `idempotent` | bool | Safe to re-run? |

---

## 9. Compatibility

### Strict Superset Guarantee
- Every valid v1.0/v1.1/v1.2 document is a valid v2.0 document.
- Parsers **MUST NOT** crash on unknown fields.
- A vector-only RAG system can consume `chunks[]` and ignore everything else.
- A graph RAG system can consume `entities[]` + `SIMILAR` edges and ignore operational edges.
- An agent system can use the full world model: entities + edges + state + skills.

### Extension Rule
- Authors **MAY** add custom fields to chunks or entities.
- Custom fields **MUST NOT** conflict with defined fields.

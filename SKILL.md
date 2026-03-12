---
name: skill-chunk-md
description: "Transform Markdown into CtxFST documents — a semantic world model format with structured chunks, entity graphs, and operational metadata. Use when converting notes into agent-ready knowledge bases, adding `<Chunk>` tags and YAML frontmatter, extracting canonical entities from text, or preparing documents for LanceDB, Lance Graph, HelixDB, LightRAG, and HippoRAG pipelines."
---

# Skill Chunk MD

Transform Markdown into CtxFST documents with semantic `<Chunk>` tags, structured frontmatter, and an explicit entity layer.

## Goal

Use this skill to produce documents that support both:

1. **Chunk retrieval** for detailed context
2. **Entity retrieval** for navigation, graph expansion, and related-concept discovery

Do not only split text. Also extract the important domain entities, normalize them, and link each chunk to the entities it actually discusses.

## Target Format

CtxFST documents should contain:

1. **YAML frontmatter**
2. **Document-level `entities` catalog**
3. **Document-level `chunks` catalog**
4. **Body content wrapped in `<Chunk>` tags**

```markdown
---
title: "Document Title"
entities:
  - id: entity:python
    name: Python
    type: skill
    aliases: [python3]
  - id: entity:fastapi
    name: FastAPI
    type: framework
    aliases: []
chunks:
  - id: skill:python-api
    tags: [Python, Backend, API]
    entities: [entity:python, entity:fastapi]
    context: "Python backend work focused on APIs built with FastAPI"
---

<Chunk id="skill:python-api">
## Python API Work
I use Python and FastAPI to build REST APIs...
</Chunk>
```

## Core Principle

Use **chunks** as the content carrier and **entities** as the semantic index.

- **Chunks** answer: "What exact passage should be retrieved?"
- **Entities** answer: "What concept does this passage belong to?"

Tags are useful for broad filtering. Entities are the canonical graph nodes.

## Core Workflow

### Step 1: Analyze Document Structure

Identify semantic boundaries in the source Markdown:

- Headers (`##`, `###`) that introduce a new topic
- Thematic shifts within long sections
- Lists that describe one coherent concept
- Code blocks plus their explanation when they should stay together

### Step 2: Determine Chunk Boundaries

Each chunk should be:

- **Self-contained**: understandable when retrieved alone
- **Focused**: centered on one main topic or closely related subtopic
- **Retrievable**: useful as a standalone answer fragment

Size guidelines:

- Minimum: ~100 tokens
- Target: 300-800 tokens
- Maximum: ~1500 tokens

Split oversized chunks when the topic changes. Merge undersized chunks when they cannot stand on their own.

### Step 3: Extract Candidate Entities

Before writing frontmatter, extract the domain-specific entities from the document.

Look for:

- Hard skills
- Tools and libraries
- Frameworks
- Platforms
- Databases
- Protocols and standards
- Architectures and design patterns
- Named products or systems

Do not promote every noun into an entity. Prefer terms that would make sense as nodes in a knowledge graph.

### Step 4: Normalize and Deduplicate Entities

Convert raw mentions into canonical entities.

Normalization rules:

- Use the most recognizable canonical name: `PostgreSQL`, not `postgres`
- Merge aliases into one entity: `JS` -> `JavaScript`, `K8s` -> `Kubernetes`
- Keep acronym + full name only when both are genuinely used as aliases
- Remove generic terms like `system`, `project`, `tool`, `computer`, `work`
- Remove incidental mentions that are not semantically important to retrieval

If unsure whether something is an entity, ask:

1. Would this help navigate related knowledge?
2. Would this deserve its own node in a skills graph?
3. Would retrieving chunks by this term produce meaningful results?

If the answer is no, keep it out of the entity list.

### Step 5: Generate Entity IDs

Use the format: `entity:{canonical-name}`

Examples:

- `entity:python`
- `entity:fastapi`
- `entity:postgresql`
- `entity:event-driven-architecture`

IDs must be lowercase kebab-case after the prefix.

### Step 6: Generate Chunk IDs

Use the format: `{category}:{topic}[-{subtopic}]`

| Category | Use Case | Examples |
|----------|----------|----------|
| `skill:` | Technical skills | `skill:python`, `skill:react-hooks` |
| `about:` | Personal or org info | `about:background`, `about:mission` |
| `project:` | Project descriptions | `project:graphrag`, `project:api-v2` |
| `principle:` | Guidelines and values | `principle:security-first` |
| `workflow:` | Processes | `workflow:deployment`, `workflow:review` |
| `reference:` | Reference material | `reference:api-auth`, `reference:schema` |

### Step 7: Create YAML Frontmatter

Define both `entities` and `chunks`.

```yaml
---
title: "My Skills Document"
entities:
  - id: entity:python
    name: Python
    type: skill
    aliases: [python3]
  - id: entity:fastapi
    name: FastAPI
    type: framework
    aliases: []
  - id: entity:pandas
    name: Pandas
    type: library
    aliases: []
chunks:
  - id: skill:python-api
    tags: [Python, Backend, API]
    entities: [entity:python, entity:fastapi]
    context: "Python backend skills focused on REST APIs and service implementation"
    created_at: "2026-03-08"
    version: 1
    type: text
    priority: high
    dependencies: []
  - id: skill:python-data
    tags: [Python, Data]
    entities: [entity:python, entity:pandas]
    context: "Python data-processing skills focused on tabular analysis and ETL work"
    created_at: "2026-03-08"
    version: 1
    type: text
    priority: medium
    dependencies: []
---
```

### Step 8: Link Chunks to Entities

Every chunk should list the canonical entities it actually discusses.

Linking rules:

- Include entities that are central to the chunk
- Skip entities that appear only in passing
- Prefer 1-6 entities per chunk
- Do not copy all document entities into every chunk
- If two chunks mention the same entity for different reasons, differentiate that in `context`

### Step 9: Wrap Content with `<Chunk>` Tags

Apply `<Chunk>` tags that match the frontmatter chunk IDs.

```markdown
<Chunk id="skill:python-api">
## Python API Work

I use Python and FastAPI to build REST APIs and internal services.
</Chunk>
```

### Step 10: Validate and Export

Use the included scripts:

```bash
python3 scripts/validate_chunks.py document.md
python3 scripts/export_to_lancedb.py document.md --output chunks.json
python3 scripts/diagnose_chunks.py document.md --level suggest
```

## Entity Rules

### What counts as an entity

Prefer entities that are:

- Specific
- reusable across documents
- meaningful as graph nodes
- useful for retrieval or expansion

Good examples:

- `Python`
- `FastAPI`
- `Docker`
- `Kubernetes`
- `CI/CD`
- `Event-Driven Architecture`
- `JWT`

Usually not entities:

- `experience`
- `technology`
- `feature`
- `application`
- `computer`
- `problem`
- `task`

### Entity types

Use one of these default types:

- `skill`
- `tool`
- `library`
- `framework`
- `platform`
- `database`
- `architecture`
- `protocol`
- `concept`
- `domain`
- `product`

If none fit well, use `concept` instead of inventing many custom types.

### World Model entity types

When building documents that participate in a world model or agent loop, these additional types are available:

- `state` — world state node (e.g., `entity:resume-parsed`)
- `action` — executable action (e.g., `entity:analyze-resume`)
- `goal` — task objective (e.g., `entity:learn-kubernetes-path`)
- `agent` — actor or user (e.g., `entity:ian-chou`)
- `evidence` — observation result (e.g., `entity:docker-3yr-experience`)

### World Model YAML fields

SKILL.md files that participate in a world model may include these optional YAML frontmatter fields:

```yaml
---
name: analyze-resume
description: "Parse raw resume and extract skill evidence"
# === World Model Fields (all optional) ===
preconditions:
  - "entity:has-raw-resume"
  - "NOT entity:has-parsed-resume"
postconditions:
  - "entity:has-parsed-resume"
  - "entity:has-skill-evidence"
related_nodes:
  - "entity:resume-parsing"
  - "entity:skill-extraction"
related_skills:
  - "career-mapping"
  - "skill-gap-analysis"
cost: low
idempotent: true
---
```

| Field | Type | Description |
|-------|------|-------------|
| `preconditions` | `string[]` | State entities that must exist before this skill can execute |
| `postconditions` | `string[]` | State entities created or updated after execution |
| `related_nodes` | `string[]` | Anchor points in the semantic graph |
| `related_skills` | `string[]` | Sequential or complementary skill names |
| `cost` | `enum` | `low`, `medium`, `high` — estimated execution cost |
| `idempotent` | `bool` | Whether safe to re-run without side effects |

Preconditions use `NOT` prefix for negation (e.g., `"NOT entity:has-parsed-resume"` means that state must **not** exist).

### Tags vs entities

Use **tags** for:

- broad classification
- filtering
- document organization

Use **entities** for:

- canonical concept identity
- chunk-to-graph linking
- similarity and traversal workflows
- cross-document concept reuse

Example:

- Tag: `Backend`
- Entity: `entity:fastapi`

## Frontmatter Schema

### Entity schema

```yaml
entities:
  - id: entity:fastapi
    name: FastAPI
    type: framework
    aliases: []
```

Required fields:

- `id`
- `name`
- `type`

Optional field:

- `aliases`

### Chunk schema

```yaml
chunks:
  - id: skill:python-api
    tags: [Python, Backend, API]
    entities: [entity:python, entity:fastapi]
    context: "Python backend skills focused on REST APIs built with FastAPI"
    created_at: "2026-03-08"
    version: 1
    type: text
    priority: high
    dependencies: []
```

Recommended fields:

- `id`
- `entities`
- `context`

Optional fields:

- `tags`
- `created_at`
- `version`
- `type`
- `priority`
- `dependencies`

## Context Writing Rules

Each chunk `context` should:

- explain the chunk's role in the document
- mention the distinguishing use case
- reflect the linked entities naturally
- avoid copying the first sentence verbatim

Good:

- `"Python backend skills focused on REST APIs, async services, and FastAPI-based implementation"`

Weak:

- `"This chunk talks about Python"`

## Example Transformation

### Before

```markdown
## About Me

I'm a backend engineer focused on APIs and distributed systems.

## Python

I use Python for REST APIs and internal tools.

### Key Libraries
- FastAPI for web services
- Pandas for data processing
```

### After

```markdown
---
title: "Profile"
entities:
  - id: entity:python
    name: Python
    type: skill
    aliases: [python3]
  - id: entity:fastapi
    name: FastAPI
    type: framework
    aliases: []
  - id: entity:pandas
    name: Pandas
    type: library
    aliases: []
chunks:
  - id: about:background
    tags: [About, Experience]
    entities: []
    context: "Professional background as a backend engineer working on APIs and distributed systems"
    created_at: "2026-03-08"
    version: 1
    type: text
    priority: medium
    dependencies: []
  - id: skill:python
    tags: [Python, Backend]
    entities: [entity:python, entity:fastapi, entity:pandas]
    context: "Python skills for API development, service work, and data processing"
    created_at: "2026-03-08"
    version: 1
    type: text
    priority: high
    dependencies: [about:background]
---

<Chunk id="about:background">
## About Me

I'm a backend engineer focused on APIs and distributed systems.
</Chunk>

<Chunk id="skill:python">
## Python

I use Python for REST APIs and internal tools.

### Key Libraries
- FastAPI for web services
- Pandas for data processing
</Chunk>
```

## GraphRAG Guidance

When preparing documents for graph-oriented retrieval:

- Treat `entities` as the canonical node inventory
- Treat chunk `entities` arrays as chunk-to-entity edges
- Treat `dependencies` as chunk-to-chunk prerequisite links
- Keep tags broad and entities precise

Do not rely on tags alone when the goal is entity-based navigation.

## When Not to Extract Many Entities

Be conservative when:

- the document is very short
- the document is mostly narrative with few domain terms
- the same concept is repeated with no useful distinctions
- the source is noisy and entity extraction would create junk nodes

In these cases, return a smaller, cleaner entity set.

## Validation

After conversion, verify:

1. Every `<Chunk>` ID exists in `chunks`
2. Every `chunks[].entities` reference exists in `entities`
3. Entity IDs are unique and canonical
4. Chunk IDs are unique
5. No nested chunks exist
6. Context fields differentiate similar chunks
7. Generic or noisy entities have been removed

```bash
python3 scripts/validate_chunks.py path/to/document.md
```

## Diagnostics

When the user asks to diagnose, review both chunk quality and entity quality.

### Check categories

1. **Chunk similarity**
   - Flag chunks that are too similar to distinguish during retrieval
2. **Context quality**
   - Flag vague, repetitive, or overly short context fields
3. **Tag overlap**
   - Flag tags that appear everywhere and no longer help filtering
4. **Entity noise**
   - Flag generic or low-value entities
5. **Entity duplication**
   - Flag aliases that should be merged into one canonical node
6. **Chunk-to-entity linking**
   - Flag chunks with missing, excessive, or irrelevant entity links

### Diagnostic prompts

**Diagnose only:**

```text
Check this document for chunk and entity quality issues
```

**Diagnose with suggestions:**

```text
Diagnose this document's chunk and entity structure and suggest fixes
```

**Fix-oriented review:**

```text
Rewrite the frontmatter so the entities are canonical and each chunk links only to the right entities
```

## Resources

- **Chunk syntax details**: See [references/chunk-syntax.md](references/chunk-syntax.md)
- **Entity format reference**: See [references/entity-format.md](references/entity-format.md)
- **Semantic chunking theory**: See [references/semantic-chunking.md](references/semantic-chunking.md)
- **Examples**: See [assets/examples/](assets/examples/) for before/after samples


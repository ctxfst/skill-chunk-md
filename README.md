# skill-chunk-md

> **Transform Markdown into semantically chunked documents for better LLM retrieval.**

**Frontmatter format for LanceDB / Lance Graph / HelixDB / LightRAG / HippoRAG compatibility** 🚀

A [Claude skill](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/prompt_caching_examples) that teaches Claude how to convert plain Markdown documents into **CtxFST format** using `<Chunk>` tags and YAML frontmatter. CtxFST is **entity + chunk**: entities are the semantic index (the map); chunks are the content carrier (the passages you retrieve). Both layers are part of the format.

### Why chunk your Markdown?

When you feed a long document to an LLM, retrieval can be imprecise.  
`<Chunk>` tags + structured frontmatter act as **semantic anchors** — they help Claude locate and reference specific sections precisely.

```markdown
# Before
I know Python, React, and Docker.

# After
---
entities:
  - id: entity:python
    name: Python
    type: skill
chunks:
  - id: skill:python
    tags: [Python, Backend]
    entities: [entity:python]
    context: "Author's Python skills for data pipelines and APIs"
---

<Chunk id="skill:python">
## Python
**Proficiency**: Advanced  
**Context**: Used for data pipelines and APIs with FastAPI.
</Chunk>
```

---

## Quick start

### 1. Install the skill

Use [`SKILL.md`](SKILL.md) directly in your Claude project, or download [`skill-chunk-md.skill`](https://github.com/ctxfst/skill-chunk-md/releases/latest/download/skill-chunk-md.skill).

### 2. Ask Claude to chunk your document

```
Convert this document into CtxFST format with proper <Chunk> tags and YAML frontmatter.
```

Claude will:
- Analyze semantic boundaries
- Extract and normalize canonical entities
- Generate meaningful chunk IDs
- Create YAML frontmatter with context, tags, and entity links
- Wrap content in `<Chunk>` tags

---

## What's included

```
skill-chunk-md/
├── SKILL.md                    # Main skill instructions
├── scripts/
│   ├── validate_chunks.py      # Validate chunk syntax & frontmatter
│   ├── export_to_lancedb.py    # Export chunks to JSON/LanceDB
│   └── contextualize_chunks.py # Generate contextual descriptions (LLM)
├── references/
│   ├── chunk-syntax.md         # Complete <Chunk> tag reference
│   ├── entity-format.md        # Entity schema and field reference
│   └── semantic-chunking.md     # Chunking methodology
└── assets/examples/
    ├── before.md               # Sample: plain Markdown
    └── after.md                # Sample: CtxFST format
```

---

## Frontmatter Format

CtxFST uses **YAML frontmatter** to store chunk metadata separately from content:

```yaml
---
entities:
  - id: entity:python
    name: Python
    type: skill
    aliases: [python3]
  - id: entity:go
    name: Go
    type: skill
    aliases: [golang]
chunks:
  - id: skill:python
    tags: [Python, Backend, API]
    entities: [entity:python]
    context: "Author's Python skills for REST APIs and data pipelines"
    created_at: "2026-02-03"
    version: 1
    type: text
    priority: high
    dependencies: []
  - id: skill:go
    tags: [Go, Microservices]
    entities: [entity:go]
    context: "Go programming for high-performance services"
    created_at: "2026-01-15"
    version: 1
---
```

### Core Fields

#### Document Level
| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `entities` | array | No | Canonical entity catalog for the document |
| `chunks` | array | ✅ Yes | Catalog of chunks and their metadata |

#### Entity Level (`entities[]`)
| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | string | ✅ Yes | Unique entity identifier (e.g., `entity:python`) |
| `name` | string | ✅ Yes | Canonical human-readable name |
| `type` | string | ✅ Yes | Entity classification (skill, tool, concept, etc.) |
| `aliases` | array | No | Alternative names or acronyms |

#### Chunk Level (`chunks[]`)
| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | string | ✅ Yes | Unique chunk identifier (category:topic) |
| `tags` | array | No | Broad classification tags for RAG filtering |
| `entities` | array | No | List of entity IDs discussed in this chunk |
| `context` | string | No | 50-100 token description of chunk content |

### 2026 RAG Extension Fields

| Field | Type | Purpose |
|-------|------|---------|
| `created_at` | ISO date | Temporal RAG — enables point-in-time retrieval |
| `version` | integer | Version control for knowledge base updates |
| `type` | enum | Multi-modal support: text, image, video, audio |
| `priority` | enum | Agent hints: high, medium, low |
| `dependencies` | array | List prerequisite chunk IDs for context |

### Why Frontmatter?

| Benefit | Description |
|---------|-------------|
| **Structured data** | Easy to parse for vector DBs |
| **Separated concerns** | Context as metadata, content stays clean |
| **LanceDB ready** | Store context, content, tags as columns |
| **Graph DB ready** | `entities` array maps directly to nodes for Lance Graph and HelixDB |
| **GraphRAG enabled** | Tags and chunk links build the semantic graph for LightRAG/HippoRAG |
| **Agentic RAG** | Priority & dependencies guide agent retrieval strategy |
| **Temporal RAG** | `created_at` & `version` enable historical queries |

---

## The `<Chunk>` pattern

```markdown
<Chunk id="category:topic">
Your content here...
</Chunk>
```

### ID categories

| Category | Use Case | Example |
|----------|----------|---------|
| `skill:` | Technical skills | `skill:python-async` |
| `about:` | Background info | `about:experience` |
| `project:` | Projects | `project:payment-gateway` |
| `principle:` | Guidelines | `principle:security-first` |

---

## Export to LanceDB

Use the included script to export chunks for vector database ingestion:

```bash
python3 scripts/export_to_lancedb.py your-document.md --output chunks.json
```

Output format (with 2026 RAG extensions and entities):
```json
{
  "entities": [
    {
      "id": "entity:python",
      "name": "Python",
      "type": "skill"
    }
  ],
  "chunks": [
    {
      "id": "skill:python",
      "context": "Author's Python skills...",
      "content": "## Python\n...",
      "tags": ["Python", "Backend"],
      "entities": ["entity:python"],
      "created_at": "2026-02-03",
      "version": 1,
      "type": "text",
      "priority": "high",
      "dependencies": [],
      "source": "path/to/file.md"
    }
  ]
}
```

Use this JSON directly with:
- **LanceDB** — Import as table with structured columns
- **Graph Databases** — Read `entities` as nodes and chunk linkage as edges for **Lance Graph** and **HelixDB**
- **LightRAG / HippoRAG** — Build entity embedding graphs from `entities` and chunk links
- **LlamaIndex** — Hybrid retrieval with priority-based reranking
- **LangGraph** — Agent-directed chunk selection via priority field

---

## Validation

Use the included script to validate your chunked documents:

```bash
python3 scripts/validate_chunks.py your-document.md
```

Checks for:
- ✅ Frontmatter contains `chunks` and optionally `entities` catalogs
- ✅ Entity definitions are valid (id, name, type) and unique
- ✅ Chunk `entities` references match document entities
- ✅ All `<Chunk>` IDs match frontmatter
- ✅ Unique chunk IDs
- ✅ Properly closed tags
- ✅ No nested chunks
- ✅ Temporal fields (ISO date format, valid version numbers)
- ✅ Agentic fields (valid priority values, dependency references)
- ✅ Multi-modal fields (valid type values, referenced file paths)

---

## Diagnostics

Analyze chunk quality before RAG ingestion. You can use **conversation** or **CLI**.

### Method 1: Ask Claude (Recommended)

Just paste your document and ask:

```
Diagnose this document's chunk quality and give me suggestions
```

Claude will analyze according to the skill and respond with issues + suggestions. No API key needed — Claude does the analysis directly.

**Intervention levels:**
- **Level 1 (diagnose)**: "Check chunk quality and mark problems"
- **Level 2 (suggest)**: "Diagnose and give me modification suggestions"
- **Level 3 (fix)**: "Auto-fix chunk issues and let me review"

### Method 2: CLI Script (Batch Processing)

For automation or processing multiple files:

```bash
# Level 1: Identify problems
python3 scripts/diagnose_chunks.py doc.md --level diagnose

# Level 2: Get modification suggestions
python3 scripts/diagnose_chunks.py doc.md --level suggest

# Level 3: Auto-generate fixes for review
python3 scripts/diagnose_chunks.py doc.md --level fix

# JSON output for LLM processing
python3 scripts/diagnose_chunks.py doc.md --level suggest --json
```

> **Note**: The CLI script uses static analysis only. No API key required.

### What Gets Checked

| Check | What It Detects |
|-------|-----------------|
| 🔄 Semantic similarity | Chunk pairs that may confuse retrieval |
| 📝 Context quality | Too short, too vague, or just repeating content |
| 🏷️ Tag overlap | Identical tags across chunks, reducing filter effectiveness |
| 🆔 ID naming | Inconsistent category prefixes, invalid format |
| 👻 Entity noise | Generic or low-value entities |
| 👯 Entity duplication | Aliases that should be merged into one canonical node |
| 🔗 Entity linking | Chunks with missing, excessive, or irrelevant entity links |

---

## Part of CtxFST

This skill is part of the [CtxFST](https://github.com/ctxfst) ecosystem.

**Related skills:**
- `skill-chunk-mdx` (coming soon)
- `skill-chunk-pdf` (coming soon)

---

## License

MIT — Fork it, adapt it, share it.

---

**Maintained by**: [ctxfst](https://github.com/ctxfst)

# skill-chunk-md

> **Transform Markdown into semantically chunked documents for better LLM retrieval.**

**Frontmatter format for LanceDB / LightRAG / HippoRAG compatibility** 🚀

A [Claude skill](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/prompt_caching_examples) that teaches Claude how to convert plain Markdown documents into **CtxFST format** using `<Chunk>` tags and YAML frontmatter.

### Why chunk your Markdown?

When you feed a long document to an LLM, retrieval can be imprecise.  
`<Chunk>` tags + structured frontmatter act as **semantic anchors** — they help Claude locate and reference specific sections precisely.

```markdown
# Before
I know Python, React, and Docker.

# After
---
chunks:
  - id: skill:python
    tags: [Python, Backend]
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

Download [`skill-chunk-md.skill`](https://github.com/ctxfst/skill-chunk-md/releases) and add it to your Claude project.

### 2. Ask Claude to chunk your document

```
Convert this document into CtxFST format with proper <Chunk> tags and YAML frontmatter.
```

Claude will:
- Analyze semantic boundaries
- Generate meaningful chunk IDs
- Create YAML frontmatter with context and tags
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
│   └── semantic-chunking.md    # Chunking methodology
└── assets/examples/
    ├── before.md               # Sample: plain Markdown
    └── after.md                # Sample: CtxFST format
```

---

## Frontmatter Format

CtxFST uses **YAML frontmatter** to store chunk metadata separately from content:

```yaml
---
chunks:
  - id: skill:python
    tags: [Python, Backend, API]
    context: "Author's Python skills for REST APIs and data pipelines"
    created_at: "2026-02-03"
    version: 1
    type: text
    priority: high
    dependencies: []
  - id: skill:go
    tags: [Go, Microservices]
    context: "Go programming for high-performance services"
    created_at: "2026-01-15"
    version: 1
---
```

### Core Fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | string | ✅ Yes | Unique chunk identifier (category:topic) |
| `tags` | array | No | Classification tags for RAG filtering |
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
| **LightRAG/HippoRAG** | Tags become graph nodes, dependencies enable GraphRAG |
| **Agentic RAG** | Priority & dependencies guide agent retrieval strategy |
| **Temporal RAG** | created_at & version enable historical queries |

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
python scripts/export_to_lancedb.py your-document.md --output chunks.json
```

Output format (with 2026 RAG extensions):
```json
[
  {
    "id": "skill:python",
    "context": "Author's Python skills...",
    "content": "## Python\n...",
    "tags": ["Python", "Backend"],
    "created_at": "2026-02-03",
    "version": 1,
    "type": "text",
    "priority": "high",
    "dependencies": [],
    "source": "path/to/file.md"
  }
]
```

Use this JSON directly with:
- **LanceDB** — Import as table with structured columns
- **LightRAG** — Build knowledge graph from tags & dependencies
- **LlamaIndex** — Hybrid retrieval with priority-based reranking
- **LangGraph** — Agent-directed chunk selection via priority field

---

## Validation

Use the included script to validate your chunked documents:

```bash
python scripts/validate_chunks.py your-document.md
```

Checks for:
- ✅ Frontmatter chunk definitions exist
- ✅ All `<Chunk>` IDs match frontmatter
- ✅ Unique chunk IDs
- ✅ Properly closed tags
- ✅ No nested chunks
- ✅ Temporal fields (ISO date format, valid version numbers)
- ✅ Agentic fields (valid priority values, dependency references)
- ✅ Multi-modal fields (valid type values, referenced file paths)

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

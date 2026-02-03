---
name: skill-chunk-md
description: "Convert Markdown documents into CtxFST format using Semantic Chunking, Chunk tags, and YAML Frontmatter. Use this skill when (1) transforming plain Markdown into semantically chunked documents, (2) adding Chunk tags to improve LLM retrieval accuracy, (3) preparing documents for LanceDB/LightRAG/HippoRAG pipelines, or (4) creating skill documents with proper chunk boundaries."
---

# Skill Chunk MD

Transform Markdown documents into CtxFST format with semantic `<Chunk>` tags and structured frontmatter for improved LLM retrieval.

## Overview

This skill guides Claude to convert plain Markdown documents into semantically chunked documents using the CtxFST standard. The combination of **YAML frontmatter** and `<Chunk>` tags enables precise retrieval in RAG pipelines, including vector databases (LanceDB) and graph-based systems (LightRAG, HippoRAG).

## Document Format

CtxFST documents have two parts:

1. **YAML Frontmatter** — Structured metadata with chunk IDs, tags, and context
2. **Content Body** — `<Chunk>` tags wrapping the actual content

```markdown
---
title: "Document Title"
chunks:
  - id: skill:python
    tags: [Python, Backend]
    context: "Author's Python programming skills for APIs and data pipelines"
---

<Chunk id="skill:python">
## Python
I use Python for building REST APIs and data pipelines...
</Chunk>
```

## Core Workflow

### Step 1: Analyze Document Structure

Identify semantic boundaries in the source Markdown:

- **Headers** (H2, H3) typically mark topic boundaries
- **Thematic shifts** within sections
- **Lists of related items** that form logical units
- **Code blocks with explanations**

### Step 2: Determine Chunk Granularity

Each chunk should be:

- **Self-contained**: Understandable without surrounding context
- **Focused**: One main concept or topic per chunk
- **Retrievable**: Useful when found via search

**Size guidelines:**
- Minimum: ~100 tokens (avoid over-fragmentation)
- Optimal: 300-800 tokens
- Maximum: ~1500 tokens (split if larger)

### Step 3: Generate Chunk IDs

Use the format: `{category}:{topic}[-{subtopic}]`

| Category | Use Case | Examples |
|----------|----------|----------|
| `skill:` | Technical skills | `skill:python`, `skill:react-hooks` |
| `about:` | Personal/org info | `about:background`, `about:mission` |
| `project:` | Project descriptions | `project:graphrag`, `project:api-v2` |
| `principle:` | Guidelines/values | `principle:security-first` |
| `workflow:` | Processes | `workflow:deployment`, `workflow:review` |
| `reference:` | Reference material | `reference:api-auth`, `reference:schema` |

### Step 4: Create YAML Frontmatter

Define all chunks in the frontmatter with context and tags:

```yaml
---
title: "My Skills Document"
chunks:
  - id: skill:python
    tags: [Python, Backend, API]
    context: "Author's Python skills for REST APIs and data pipelines using FastAPI"
  - id: skill:go
    tags: [Go, Microservices]
    context: "Go programming experience for high-performance microservices"
---
```

**Context generation guidelines:**
- 50-100 tokens describing the chunk's role in the document
- Include key entities and relationships
- Help disambiguate similar content across documents

### Step 5: Wrap Content with Chunk Tags

Apply `<Chunk>` tags matching the frontmatter IDs:

```markdown
<Chunk id="skill:python">
## Python

**Proficiency**: Advanced

I use Python daily for building data pipelines and REST APIs.

### Key Patterns
- async/await for I/O-bound operations
- asyncio.gather for parallel execution
</Chunk>
```

### Step 6: Validate and Export

Use the included scripts:

```bash
# Validate chunk structure
python scripts/validate_chunks.py document.md

# Export for LanceDB
python scripts/export_to_lancedb.py document.md --output chunks.json
```

## Why Frontmatter?

| Approach | Storage | Flexibility | Best For |
|----------|---------|-------------|----------|
| **Anthropic Original** | Context merged into content | Low | Simple RAG |
| **Frontmatter** | Context separated as metadata | High | LanceDB, LightRAG |

### Benefits for Vector DBs (LanceDB)

```python
# Frontmatter enables structured columns
table.add({
    "id": chunk.id,
    "context": chunk.context,    # Separate column
    "content": chunk.content,    # Separate column
    "tags": chunk.tags,          # Filterable
    "vector": embed(chunk.context + chunk.content)
})
```

### Benefits for Graph RAG (LightRAG/HippoRAG)

- **Tags** become graph nodes and edges
- **Context** helps entity extraction
- **Structured IDs** enable cross-document linking

## Chunk Syntax Rules

1. **ID is required** — Must match a frontmatter entry
2. **IDs use kebab-case** — `skill:my-topic` not `skill:myTopic`
3. **No nested chunks** — Chunks cannot contain other chunks
4. **Preserve Markdown** — All formatting works inside chunks

## Example Transformation

### Before (Plain Markdown)

```markdown
## About Me

I'm a backend engineer with 8 years of experience...

## Python

I use Python for data pipelines and APIs...

### Key Libraries
- FastAPI for web services
- Pandas for data processing
```

### After (CtxFST Format)

```markdown
---
chunks:
  - id: about:background
    tags: [About, Experience]
    context: "Author's professional background as a backend engineer"
  - id: skill:python
    tags: [Python, Backend]
    context: "Python programming skills for APIs and data processing"
---

<Chunk id="about:background">
## About Me

I'm a backend engineer with 8 years of experience...
</Chunk>

---

<Chunk id="skill:python">
## Python

I use Python for data pipelines and APIs...

### Key Libraries
- FastAPI for web services
- Pandas for data processing
</Chunk>
```

## When NOT to Chunk

- **Very short documents** (<500 tokens total) — chunking adds overhead
- **Highly interconnected content** — if every paragraph references others
- **Code-only files** — use code comments instead

## Validation

After chunking, verify:

1. All `<Chunk>` tags have matching frontmatter entries
2. All IDs are unique
3. No chunks are nested
4. Each chunk is self-contained

```bash
python scripts/validate_chunks.py path/to/document.md
```

## Resources

- **Chunk syntax details**: See [references/chunk-syntax.md](references/chunk-syntax.md)
- **Semantic chunking theory**: See [references/semantic-chunking.md](references/semantic-chunking.md)
- **Examples**: See [assets/examples/](assets/examples/) for before/after samples

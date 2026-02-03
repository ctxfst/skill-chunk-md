---
name: skill-chunk-md
description: "Convert Markdown documents into CtxFST format using Semantic Chunking and Chunk tags. Use this skill when (1) transforming plain Markdown into semantically chunked documents, (2) adding Chunk tags to improve LLM retrieval accuracy, (3) preparing documents for Contextual BM25/Embeddings pipelines, or (4) creating skill documents with proper chunk boundaries."
---

# Skill Chunk MD

Transform Markdown documents into CtxFST format with semantic `<Chunk>` tags for improved LLM retrieval.

## Overview

This skill guides Claude to convert plain Markdown documents into semantically chunked documents using the CtxFST standard. The `<Chunk>` tags act as **LLM anchors** that enable precise retrieval in RAG (Retrieval Augmented Generation) pipelines.

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

### Step 4: Wrap Content

Apply `<Chunk>` tags:

```markdown
<Chunk id="skill:python-async">
## Python Async Programming

**Proficiency**: Advanced
**Context**: Used for high-concurrency web services and data pipelines.

### Key Patterns
- async/await for I/O-bound operations
- asyncio.gather for parallel execution
- Proper exception handling in async contexts
</Chunk>
```

## Chunk Syntax Reference

### Basic Syntax

```markdown
<Chunk id="unique-identifier">
Content goes here...
</Chunk>
```

### Rules

1. **ID is required** - Must be unique within the document
2. **IDs use kebab-case** - `skill:my-topic` not `skill:myTopic`
3. **No nested chunks** - Chunks cannot contain other chunks
4. **Preserve Markdown** - All Markdown formatting works inside chunks

### ID Naming Best Practices

- Be descriptive: `skill:python-data-analysis` > `skill:python-1`
- Use hierarchy: `project:api-authentication` > `project:auth`
- Stay consistent: Pick a pattern and stick to it

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

- **Very short documents** (<500 tokens total) - chunking adds overhead
- **Highly interconnected content** - if every paragraph references others
- **Code-only files** - use code comments instead

## Validation

After chunking, verify:

1. All `<Chunk>` tags are properly closed
2. All IDs are unique
3. No chunks are nested inside other chunks
4. Each chunk is self-contained

Use `scripts/validate_chunks.py` for automated validation:

```bash
python scripts/validate_chunks.py path/to/document.md
```

## Resources

- **Chunk syntax details**: See [references/chunk-syntax.md](references/chunk-syntax.md)
- **Semantic chunking theory**: See [references/semantic-chunking.md](references/semantic-chunking.md)
- **Examples**: See [assets/examples/](assets/examples/) for before/after samples

# skill-chunk-md

> **Transform Markdown into semantically chunked documents for better LLM retrieval.**

A [Claude skill](https://github.com/anthropics/anthropic-cookbook/tree/main/misc/prompt_caching_examples) that teaches Claude how to convert plain Markdown documents into **CtxFST format** using `<Chunk>` tags.

### Why chunk your Markdown?

When you feed a long document to an LLM, retrieval can be imprecise.  
`<Chunk>` tags act as **semantic anchors** — they help Claude locate and reference specific sections precisely.

```markdown
# Before
I know Python, React, and Docker.

# After
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
Convert this document into CtxFST format with proper <Chunk> tags.
```

Claude will:
- Analyze semantic boundaries
- Generate meaningful chunk IDs
- Wrap content in `<Chunk>` tags

---

## What's included

```
skill-chunk-md/
├── SKILL.md                    # Main skill instructions
├── scripts/
│   ├── validate_chunks.py      # Validate chunk syntax
│   └── contextualize_chunks.py # Generate contextual descriptions (Anthropic method)
├── references/
│   ├── chunk-syntax.md         # Complete <Chunk> tag reference
│   └── semantic-chunking.md    # Chunking methodology
└── assets/examples/
    ├── before.md               # Sample: plain Markdown
    └── after.md                # Sample: CtxFST format
```

---

## Anthropic Contextual Retrieval

This skill implements [Anthropic's Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) method, which improves RAG retrieval accuracy by **up to 49%**.

### The Process

1. **Semantic Chunking** — Divide documents at meaning boundaries using `<Chunk>` tags
2. **Context Generation** — Use Claude to generate 50-100 token context for each chunk
3. **Context Prepending** — Combine context + original chunk for embedding/BM25

### Generate Contextual Descriptions

```bash
# Requires: pip install anthropic
# Requires: export ANTHROPIC_API_KEY="your-key"

python scripts/contextualize_chunks.py your-document.md
```

Uses prompt caching to reduce costs (~$1.02 per million tokens).

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

## Validation

Use the included script to validate your chunked documents:

```bash
python scripts/validate_chunks.py your-document.md
```

Checks for:
- ✅ Unique chunk IDs
- ✅ Properly closed tags
- ✅ No nested chunks
- ✅ Valid ID format

---

## Part of CtxFST

This skill is part of the [CtxFST](https://github.com/ctxfst) ecosystem.

**Related skills:**
- `skill-chunk-mdx` (coming soon)
- `skill-chunk-pdf` (coming soon)
- `skill-chunk-org` (coming soon)

---

## License

MIT — Fork it, adapt it, share it.

---

**Maintained by**: [ctxfst](https://github.com/ctxfst)

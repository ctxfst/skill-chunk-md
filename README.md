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
│   └── validate_chunks.py      # Validate chunk syntax
├── references/
│   ├── chunk-syntax.md         # Complete <Chunk> tag reference
│   └── semantic-chunking.md    # Chunking methodology
└── assets/examples/
    ├── before.md               # Sample: plain Markdown
    └── after.md                # Sample: CtxFST format
```

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

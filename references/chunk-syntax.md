# Chunk Syntax Reference

Complete reference for the `<Chunk>` tag syntax used in CtxFST documents.

## Document Structure

CtxFST documents use **YAML frontmatter** for metadata and `<Chunk>` tags for content:

```markdown
---
title: "Document Title"
chunks:
  - id: skill:python
    tags: [Python, Backend]
    context: "Brief context about this chunk..."
---

<Chunk id="skill:python">
Content here...
</Chunk>
```

## Frontmatter Schema

```yaml
---
title: string              # Optional: Document title
chunks:                    # Required: Array of chunk definitions
  - id: string             # Required: Unique chunk identifier
    tags: [string, ...]    # Optional: Semantic tags for filtering
    context: string        # Required: 50-100 token context description
---
```

### Why Frontmatter?

| Benefit | Description |
|---------|-------------|
| **Structured metadata** | Easy to parse with `yaml.safe_load()` |
| **Separated concerns** | Context is metadata, content stays clean |
| **LanceDB/LightRAG ready** | Can store context and content as separate columns |
| **Updateable** | Change context without modifying content |

## Chunk Tag Syntax

### Basic Syntax

```markdown
<Chunk id="category:topic">
Your content here...
</Chunk>
```

### Required Attribute: `id`

Every chunk must have a unique identifier matching one in frontmatter.

**Format**: `{category}:{topic}[-{subtopic}]`

**Valid examples**:
```
skill:python
skill:python-async
about:background
project:api-v2-auth
```

**Invalid examples**:
```
python              # Missing category
skill:Python        # Use lowercase
skill:python async  # No spaces allowed
```

## ID Categories

| Category | Purpose | When to Use |
|----------|---------|-------------|
| `skill:` | Technical skills | Languages, frameworks, tools |
| `about:` | Identity/background | Personal info, team, mission |
| `project:` | Projects/products | Work samples, portfolio |
| `principle:` | Values/guidelines | Design principles, standards |
| `workflow:` | Processes | Deployment, review flows |
| `reference:` | Reference material | API docs, schemas |

## Tags Best Practices

Tags help with filtering and graph-based retrieval:

```yaml
chunks:
  - id: skill:python-async
    tags: [Python, Async, Concurrency, Backend]
    context: "..."
```

- Use **PascalCase** for tags: `FastAPI` not `fastapi`
- Keep tags **focused**: 3-6 tags per chunk
- Reuse tags across chunks for **graph connections**

## Formatting Rules

### 1. Chunks Cannot Nest

❌ **Wrong**:
```markdown
<Chunk id="outer">
  <Chunk id="inner">
  </Chunk>
</Chunk>
```

✅ **Correct**:
```markdown
<Chunk id="first">
...
</Chunk>

<Chunk id="second">
...
</Chunk>
```

### 2. IDs Must Match Frontmatter

Every `<Chunk id="...">` must have a corresponding entry in frontmatter.

### 3. Markdown Works Inside Chunks

```markdown
<Chunk id="skill:python">
## Python

**Proficiency**: Advanced

- List item 1
- List item 2

\```python
def hello():
    print("Hello")
\```
</Chunk>
```

### 4. Use Horizontal Rules Between Chunks

```markdown
<Chunk id="first">
...
</Chunk>

---

<Chunk id="second">
...
</Chunk>
```

## Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Missing frontmatter entry | Chunk won't have context | Add to frontmatter |
| ID mismatch | Parser error | Sync frontmatter and tags |
| Missing closing tag | Parser error | Add `</Chunk>` |
| Duplicate IDs | Ambiguous retrieval | Use unique IDs |
| Nested chunks | Not supported | Flatten structure |

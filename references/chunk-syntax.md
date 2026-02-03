# Chunk Syntax Reference

Complete reference for the `<Chunk>` tag syntax used in CtxFST documents.

## Basic Syntax

```markdown
<Chunk id="category:topic">
Your content here...
</Chunk>
```

## Required Attribute

### `id`

Every chunk must have a unique identifier.

**Format**: `{category}:{topic}[-{subtopic}]`

**Valid examples**:
```
skill:python
skill:python-async
about:background
project:api-v2-auth
principle:security-first
workflow:ci-cd-pipeline
```

**Invalid examples**:
```
python              # Missing category
skill:Python        # Use lowercase
skill:python async  # No spaces allowed
skill:python_async  # Use hyphens, not underscores
```

## ID Categories

| Category | Purpose | When to Use |
|----------|---------|------------|
| `skill:` | Technical skills | Programming languages, frameworks, tools |
| `about:` | Identity/background | Personal info, team info, mission |
| `project:` | Projects/products | Work samples, portfolio items |
| `principle:` | Values/guidelines | Design principles, coding standards |
| `workflow:` | Processes | Deployment, review, onboarding |
| `reference:` | Reference material | API docs, schemas, specs |
| `example:` | Examples/samples | Code samples, use cases |

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

### 2. Markdown Works Inside Chunks

```markdown
<Chunk id="skill:python">
## Python

**Proficiency**: Advanced

- List item 1
- List item 2

```python
def hello():
    print("Hello")
```
</Chunk>
```

### 3. Use Horizontal Rules Between Chunks

Recommended for visual separation:

```markdown
<Chunk id="first">
...
</Chunk>

---

<Chunk id="second">
...
</Chunk>
```

## HTML/XML Compatibility

- Tags are case-sensitive: `<Chunk>` not `<chunk>`
- Self-closing not allowed: Use `</Chunk>`, not `<Chunk />`
- Attributes use double quotes: `id="value"` not `id='value'`

## Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Missing closing tag | Parser error | Add `</Chunk>` |
| Duplicate IDs | Ambiguous retrieval | Use unique IDs |
| Nested chunks | Not supported | Flatten structure |
| Too many chunks | Over-fragmentation | Merge related content |
| Too few chunks | Poor retrieval | Split at semantic boundaries |

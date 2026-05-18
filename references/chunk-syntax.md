# Chunk Syntax Reference

Complete reference for the `%% chunk-start %%` / `%% chunk-end %%` marker syntax used in CtxFST documents.

## Document Structure

CtxFST documents use **YAML frontmatter** for metadata and `%% chunk-start %%` / `%% chunk-end %%` markers for content:

```markdown
---
title: "Document Title"
chunks:
  - id: skill:python
    tags: [Python, Backend]
    context: "Brief context about this chunk..."
---

%% chunk-start id="skill:python" %%
Content here...
%% chunk-end %%
```

## Frontmatter Schema

```yaml
---
title: string              # Optional: Document title
entities:                  # Optional: Canonical entity catalog
  - id: string             # Required: Unique entity identifier
    name: string           # Required: Human-readable name
    type: string           # Required: Entity classification
chunks:                    # Required: Array of chunk definitions
  - id: string             # Required: Unique chunk identifier
    tags: [string, ...]    # Optional: Semantic tags for filtering
    entities: [string, ...]# Optional: Linked entity IDs
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

## Chunk Marker Syntax

### Basic Syntax

```markdown
%% chunk-start id="category:topic" %%
Your content here...
%% chunk-end %%
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
%% chunk-start id="outer" %%
  %% chunk-start id="inner" %%
  %% chunk-end %%
%% chunk-end %%
```

✅ **Correct**:
```markdown
%% chunk-start id="first" %%
...
%% chunk-end %%

%% chunk-start id="second" %%
...
%% chunk-end %%
```

### 2. IDs Must Match Frontmatter

Every `%% chunk-start id="..." %%` must have a corresponding entry in frontmatter.

### 3. Markdown Works Inside Chunks

```markdown
%% chunk-start id="skill:python" %%
## Python

**Proficiency**: Advanced

- List item 1
- List item 2

\```python
def hello():
    print("Hello")
\```
%% chunk-end %%
```

### 4. Use Horizontal Rules Between Chunks

```markdown
%% chunk-start id="first" %%
...
%% chunk-end %%

---

%% chunk-start id="second" %%
...
%% chunk-end %%
```

## Common Mistakes

| Mistake | Problem | Fix |
|---------|---------|-----|
| Missing frontmatter entry | Chunk won't have context | Add to frontmatter |
| ID mismatch | Parser error | Sync frontmatter and tags |
| Missing closing marker | Parser error | Add `%% chunk-end %%` |
| Duplicate IDs | Ambiguous retrieval | Use unique IDs |
| Nested chunks | Not supported | Flatten structure |

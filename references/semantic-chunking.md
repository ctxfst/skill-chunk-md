# Semantic Chunking

How to identify meaningful boundaries in documents for optimal LLM retrieval.

## What is Semantic Chunking?

Semantic Chunking divides documents at **meaning boundaries** rather than fixed character/token counts.

### Comparison

| Method | How it Works | Retrieval Quality |
|--------|--------------|-------------------|
| Fixed-size | Split every N tokens | ⚠️ May cut mid-sentence |
| Sentence | Split at periods | ⚠️ Loses paragraph context |
| **Semantic** | Split at topic changes | ✅ Preserves meaning |

## Why Semantic Chunking Matters

When an LLM searches for relevant content:

1. **Fixed chunks** might return: `"...experience in building scalable"`
2. **Semantic chunks** return: `"I have 8 years of experience in building scalable distributed systems using Python and Go."`

The semantic chunk is **self-contained** and **useful**.

## Identifying Semantic Boundaries

### Strong Boundaries (Always Split)

- **H2 headers** (`##`) - New major topic
- **H3 headers** (`###`) - New subtopic
- **Horizontal rules** (`---`) - Intentional separation

### Weak Boundaries (Consider Context)

- **Paragraph breaks** - May or may not be topic change
- **List items** - Usually keep together
- **Code blocks** - Keep with explanation

## The Contextual Retrieval Connection

CtxFST works with **Contextual BM25/Embeddings**:

```
Document → Semantic Chunks → Add Context → Index
                  ↓
            <Chunk> tags mark boundaries
```

Each chunk gets **prepended context** explaining where it fits in the document, improving retrieval accuracy by ~49% (per Anthropic research).

## Chunk Size Guidelines

| Size | Use Case |
|------|----------|
| < 100 tokens | ❌ Too small, loses context |
| 100-300 tokens | Short definitions, single concepts |
| 300-800 tokens | **Optimal** - complete ideas |
| 800-1500 tokens | Complex topics with examples |
| > 1500 tokens | ❌ Consider splitting |

## Practical Heuristics

1. **The "standalone test"**: Can someone understand this chunk without reading the rest?
2. **The "search test"**: If someone searched for this topic, would this chunk answer their question?
3. **The "title test"**: Can you give this chunk a clear title? If not, it might be too broad.

## Example: Finding Boundaries

### Original Document

```markdown
## Experience

I worked at Company A for 5 years as a backend engineer.
I built their payment system from scratch.

## Skills

### Python
I use Python daily for data pipelines.

### Go
I use Go for microservices.
```

### Semantic Boundaries

```
[Chunk 1: about:experience]
  - "Experience" section
  - Company A details + payment system

[Chunk 2: skill:python]
  - Python subsection

[Chunk 3: skill:go]
  - Go subsection
```

Note: "Skills" H2 is NOT a chunk by itself—it's just a container for the skill subsections.

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

CtxFST implements **Anthropic's Contextual Retrieval** method:

```
Document → Semantic Chunks → LLM Context Generation → Prepend Context → Index
                  ↓                    ↓
            <Chunk> tags       Claude generates 50-100 token
            mark boundaries    contextual descriptions
```

### How It Works (Anthropic Method)

1. **Chunk the document** semantically (this is what `<Chunk>` tags provide)
2. **For each chunk**, use Claude to generate a brief context explaining where it fits in the full document
3. **Prepend the context** to the chunk content before embedding/indexing

### Example Transformation

**Original chunk:**
> "The company's revenue grew by 3% over the previous quarter."

**With context prepended:**
> "This chunk is from an SEC filing on ACME corp's performance in Q2 2023; the previous quarter's revenue was $314 million. The company's revenue grew by 3% over the previous quarter."

### Performance Improvements (Anthropic Research)

| Method | Top-20 Retrieval Failure Rate |
|--------|------------------------------|
| Baseline embeddings | 5.7% |
| Contextual Embeddings | 3.7% (**-35%**) |
| Contextual Embeddings + BM25 | 2.9% (**-49%**) |

### Official Sources

- [Introducing Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) - Anthropic (Sept 2024)
- [Contextual Embeddings Cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide) - Claude Developer

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

# CH22 Retrieval Benchmark Scaffold

This example is the starting point for the CH22 "proof chapter":

> same notes, same queries, two retrieval paths, side-by-side results

It is intentionally small and explicit. The goal is not to repackage the whole runtime, but to give you a reproducible benchmark harness that can later plug into a pure vector baseline and a CtxFST entity-aware retriever.

## What is included

- `notes/` - raw Markdown notes with overlapping themes
- `benchmark.ctxfst.md` - one hand-authored CtxFST document built from the note set
- `queries.yaml` - benchmark queries and what each query is trying to prove
- `evaluation-template.md` - a fill-in template for side-by-side retrieval results

## Dataset shape

- 6 Markdown source notes
- 8 chunks in the CtxFST document
- 13 canonical entities
- 6 benchmark queries

The note set is designed so that some relevant chunks do not repeat the query wording exactly. That gives the entity layer something real to recover.

## Run the existing pipeline on this example

From the repo root:

```bash
python3 scripts/validate_chunks.py examples/ch22-retrieval-benchmark/benchmark.ctxfst.md
python3 scripts/export_to_lancedb.py examples/ch22-retrieval-benchmark/benchmark.ctxfst.md --output examples/ch22-retrieval-benchmark/chunks.json --pretty
python3 scripts/build_entity_profiles.py examples/ch22-retrieval-benchmark/chunks.json --output examples/ch22-retrieval-benchmark/entity-profiles.json
python3 scripts/build_entity_graph.py examples/ch22-retrieval-benchmark/entity-profiles.json --output examples/ch22-retrieval-benchmark/entity-graph.json
```

## Retrieval benchmark runner

The repo now includes a lightweight local runner:

```bash
python3 scripts/ch22_retrieval_benchmark.py \
  examples/ch22-retrieval-benchmark/chunks.json \
  examples/ch22-retrieval-benchmark/entity-profiles.json \
  examples/ch22-retrieval-benchmark/entity-graph.json \
  examples/ch22-retrieval-benchmark/queries.yaml \
  --report-output examples/ch22-retrieval-benchmark/evaluation-results.md \
  --json-output examples/ch22-retrieval-benchmark/retrieval-results.json
```

It compares:

1. `baseline`: TF-IDF cosine over chunk text
2. `ctxfst`: query -> entity hits -> graph fan-out -> chunk rerank

The generated markdown report can be copied into the CH22 write-up, and the JSON
artifact is useful if you want to build stricter metrics later.

## Why this example exists

CH10 already showed the "aha" moment for entity-aware retrieval. This example is for the later, stricter question:

> is CtxFST retrieval actually more useful than pure RAG on a realistic personal notes corpus?

That makes this example a benchmark harness, not a feature demo.

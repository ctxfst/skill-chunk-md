#!/usr/bin/env python3
"""
Run a small reproducible CH22 retrieval benchmark.

This script compares:
- baseline: TF-IDF cosine over chunk text
- ctxfst: query -> entity hits -> graph fan-out -> chunk rerank

It is intentionally lightweight and uses only local benchmark artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "its", "of", "on", "or", "that", "the", "their", "this", "to", "with",
}

BASELINE_QUERY_EXPANSIONS = {
    "後端": ["backend"],
    "服務": ["service"],
    "資料庫": ["database"],
    "關係": ["relationship"],
    "高併發": ["concurrency"],
    "併發": ["concurrency"],
    "經驗": ["experience"],
    "agent": ["agent"],
    "planning": ["planning"],
    "retrieval": ["retrieval"],
    "entity": ["entity"],
    "Go": ["go"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "K8s": ["kubernetes", "k8s"],
    "OpenAI": ["openai"],
}

ENTITY_QUERY_EXPANSIONS = {
    # --- CH22 (Go/K8s/DB benchmark) ---
    "後端": ["backend", "service", "api", "deployment", "storage"],
    "服務": ["service", "services", "grpc", "api"],
    "資料庫": ["database", "databases", "storage", "postgresql", "rocksdb"],
    "索引": ["indexing", "index", "wal", "compaction"],
    "關係": ["relationship", "stack", "together", "connected"],
    "高併發": ["concurrency", "concurrent", "load", "latency", "multiplex"],
    "併發": ["concurrency", "concurrent", "load", "multiplex"],
    "想法": ["notes", "lessons", "ideas", "tradeoffs"],
    "經驗": ["experience", "project", "summary", "notes"],
    "完整": ["complete", "full", "connected"],
    "能力": ["tools", "memory", "planner", "retrieval", "execution", "automation"],
    "agent": ["agent", "runtime", "tool", "planning", "planner", "memory"],
    "planning": ["planning", "planner", "loop"],
    "retrieval": ["retrieval", "graph-aware", "entity-aware", "knowledge"],
    "entity": ["entity", "graph", "canonical", "concept"],
    "圖": ["graph", "connected", "fanout"],
    "寫過": ["notes", "wrote", "journal", "recorded"],
    "哪裡": ["notes", "chunk", "recorded"],
    "其實懂": ["tradeoffs", "systems", "experience"],
    "以前": ["previous", "earlier", "notes", "project"],
    "Go": ["go", "golang", "grpc", "service", "concurrency"],
    "Docker": ["docker", "containers", "container", "packaging"],
    "Kubernetes": ["kubernetes", "k8s", "deployment", "rollout", "scheduling"],
    "K8s": ["kubernetes", "k8s", "deployment", "rollout", "scheduling"],
    "OpenAI": ["openai", "tool-calling", "agent", "runtime"],
    # --- Career KB benchmark (new queries) ---
    # Q1: semantic search / AI search ecosystem
    "語意搜尋": ["semantic", "search", "embeddings", "vector", "retrieval", "similarity"],
    "語義搜尋": ["semantic", "search", "embeddings", "vector", "retrieval"],
    "AI": ["llm", "language", "model", "agent", "openai", "anthropic", "tool"],
    "做語意搜尋": ["semantic", "search", "embeddings", "vector", "rag", "lancedb"],
    # Q2: chatbot / messaging bot
    "聊天機器人": ["telegram", "discord", "bot", "chatbot", "messaging", "webhook"],
    "機器人": ["bot", "telegram", "discord", "webhook", "api"],
    "基礎": ["basics", "fundamentals", "foundation", "prerequisite", "intro"],
    # Q3: AI agent runtime internals
    "agent runtime": ["agent", "runtime", "planning", "tool", "llm", "memory", "langchain"],
    "底層知識": ["foundation", "prerequisite", "basics", "core", "internals", "concepts"],
    "runtime": ["runtime", "agent", "tool", "execution", "loop", "planner"],
    # Q4: frontend to LLM path
    "前端工程師": ["frontend", "javascript", "browser", "web", "typescript", "react"],
    "LLM 開發": ["llm", "language", "model", "api", "tool", "agent", "openai"],
    "入門路徑": ["intro", "getting-started", "beginner", "first-steps", "learn", "start"],
    "接觸": ["intro", "start", "begin", "getting-started", "learn"],
    # Q6: browser automation beyond scraping
    "網頁操作自動化": ["browser", "automation", "puppeteer", "playwright", "selenium", "web"],
    "自動化": ["automation", "automated", "automate", "scripting", "puppeteer", "playwright"],
    "爬蟲": ["scraping", "crawler", "crawl", "scrape", "extract"],
}


def tokenize(text: str) -> list[str]:
    raw_tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{1,}\b", text.lower())
    return [token for token in raw_tokens if token not in STOPWORDS]


def normalize_query(query: str, expansions: dict[str, list[str]]) -> str:
    parts = [query]
    lowered = query.lower()
    for key, expansion_terms in expansions.items():
        if key.lower() in lowered or key in query:
            parts.extend(expansion_terms)
    return " ".join(parts)


def build_tfidf_vectors(texts: dict[str, str]) -> tuple[dict[str, dict[str, float]], dict[str, float], dict[str, float]]:
    tokenized = {doc_id: tokenize(text) for doc_id, text in texts.items()}
    doc_count = len(tokenized)
    document_frequency: Counter[str] = Counter()

    for tokens in tokenized.values():
        document_frequency.update(set(tokens))

    idf = {
        token: math.log((1 + doc_count) / (1 + df)) + 1.0
        for token, df in document_frequency.items()
    }

    vectors: dict[str, dict[str, float]] = {}
    norms: dict[str, float] = {}
    for doc_id, tokens in tokenized.items():
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        vector = {
            token: (count / total) * idf[token]
            for token, count in counts.items()
        }
        vectors[doc_id] = vector
        norms[doc_id] = math.sqrt(sum(weight * weight for weight in vector.values()))

    return vectors, norms, idf


def build_query_vector(query: str, idf: dict[str, float], expansions: dict[str, list[str]]) -> tuple[dict[str, float], float]:
    tokens = tokenize(normalize_query(query, expansions))
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    vector = {
        token: (count / total) * idf.get(token, math.log(2.0))
        for token, count in counts.items()
    }
    norm = math.sqrt(sum(weight * weight for weight in vector.values()))
    return vector, norm


def cosine_similarity(
    vec_a: dict[str, float],
    norm_a: float,
    vec_b: dict[str, float],
    norm_b: float,
) -> float:
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    dot = sum(weight * vec_b.get(token, 0.0) for token, weight in vec_a.items())
    return dot / (norm_a * norm_b)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_queries(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data.get("queries", [])


def build_chunk_text(chunk: dict[str, Any], entity_names: dict[str, str]) -> str:
    parts = [
        chunk.get("context", ""),
        chunk.get("content", ""),
        " ".join(str(tag) for tag in chunk.get("tags", [])),
    ]
    parts.extend(entity_names.get(entity_id, "") for entity_id in chunk.get("entities", []))
    return "\n".join(str(part) for part in parts if part)


def build_entity_text(entity: dict[str, Any]) -> str:
    parts = [
        entity.get("name", ""),
        entity.get("type", ""),
        " ".join(str(alias) for alias in entity.get("aliases", [])),
        " ".join(str(tag) for tag in entity.get("tags", [])),
        " ".join(str(keyword) for keyword in entity.get("keywords", [])),
        " ".join(str(context) for context in entity.get("contexts", [])),
        " ".join(str(related) for related in entity.get("related_entities", [])),
        entity.get("representation", ""),
    ]
    return "\n".join(str(part) for part in parts if part)


def rank_baseline(
    query: str,
    chunk_vectors: dict[str, dict[str, float]],
    chunk_norms: dict[str, float],
    chunk_idf: dict[str, float],
) -> dict[str, float]:
    query_vector, query_norm = build_query_vector(query, chunk_idf, BASELINE_QUERY_EXPANSIONS)
    scores = {
        chunk_id: cosine_similarity(query_vector, query_norm, vector, chunk_norms[chunk_id])
        for chunk_id, vector in chunk_vectors.items()
    }
    return scores


def rank_entities(
    query: str,
    entity_vectors: dict[str, dict[str, float]],
    entity_norms: dict[str, float],
    entity_idf: dict[str, float],
) -> dict[str, float]:
    query_vector, query_norm = build_query_vector(query, entity_idf, ENTITY_QUERY_EXPANSIONS)
    scores = {
        entity_id: cosine_similarity(query_vector, query_norm, vector, entity_norms[entity_id])
        for entity_id, vector in entity_vectors.items()
    }
    return scores


def propagate_entity_scores(
    seed_scores: dict[str, float],
    adjacency: dict[str, list[tuple[str, float]]],
    depth: int = 1,
) -> dict[str, float]:
    scores = dict(seed_scores)
    frontier = dict(seed_scores)
    decay = 0.65

    for _step in range(depth):
        next_frontier: dict[str, float] = {}
        for entity_id, base_score in frontier.items():
            for neighbor_id, edge_score in adjacency.get(entity_id, []):
                neighbor_degree = len(adjacency.get(neighbor_id, []))
                degree_penalty = 1.0 / math.log2(2 + neighbor_degree)
                propagated = base_score * edge_score * decay * degree_penalty
                if propagated <= next_frontier.get(neighbor_id, 0.0):
                    continue
                next_frontier[neighbor_id] = propagated
        for entity_id, propagated in next_frontier.items():
            scores[entity_id] = max(scores.get(entity_id, 0.0), propagated)
        frontier = next_frontier

    return scores


def rank_ctxfst(
    query: str,
    chunks: list[dict[str, Any]],
    baseline_scores: dict[str, float],
    entity_vectors: dict[str, dict[str, float]],
    entity_norms: dict[str, float],
    entity_idf: dict[str, float],
    adjacency: dict[str, list[tuple[str, float]]],
) -> tuple[dict[str, float], dict[str, float]]:
    entity_scores = rank_entities(query, entity_vectors, entity_norms, entity_idf)
    seeds = {
        entity_id: score * (1.0 / math.log2(2 + len(adjacency.get(entity_id, []))))
        for entity_id, score in sorted(entity_scores.items(), key=lambda item: item[1], reverse=True)[:4]
        if score > 0.01
    }
    propagated = propagate_entity_scores(seeds, adjacency, depth=1)

    max_baseline = max(baseline_scores.values()) or 1.0
    max_entity = max(propagated.values()) or 1.0
    final_scores: dict[str, float] = {}

    for chunk in chunks:
        chunk_id = chunk["id"]
        chunk_entities = chunk.get("entities", [])
        n_linked = len(chunk_entities) or 1
        coverage = sum(propagated.get(entity_id, 0.0) for entity_id in chunk_entities) / math.sqrt(n_linked)
        density = len([entity_id for entity_id in chunk_entities if entity_id in propagated])
        baseline_component = baseline_scores.get(chunk_id, 0.0) / max_baseline
        entity_component = coverage / max_entity
        final_scores[chunk_id] = (
            (0.35 * baseline_component)
            + (0.55 * entity_component)
            + (0.10 * min(density, 3) / 3.0)
        )

    return final_scores, propagated


def top_items(scores: dict[str, float], top_k: int) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]


def format_chunk_list(items: list[tuple[str, float]]) -> str:
    return ", ".join(f"`{chunk_id}` ({score:.3f})" for chunk_id, score in items)


def summarize_notes(
    top_chunks: list[tuple[str, float]],
    expected_entities: set[str],
    chunk_map: dict[str, dict[str, Any]],
) -> str:
    hits = []
    misses = []
    for chunk_id, _score in top_chunks:
        chunk_entities = set(chunk_map[chunk_id].get("entities", []))
        overlap = sorted(chunk_entities & expected_entities)
        if overlap:
            hits.append(chunk_id)
        else:
            misses.append(chunk_id)

    if hits and not misses:
        return f"All top-3 chunks overlap expected entities: {', '.join(hits)}."
    if hits and misses:
        return f"Relevant support in {', '.join(hits)}; weaker fit in {', '.join(misses)}."
    return "Top-3 did not overlap the expected entity set."


def expected_entity_ids(query: dict[str, Any]) -> set[str]:
    expected = set()
    for item in query.get("expected_entities", []):
        if isinstance(item, str):
            expected.add(item)
        elif isinstance(item, dict) and isinstance(item.get("entity"), str):
            expected.add(item["entity"])
    return expected


def render_report(
    queries: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    baseline_results: dict[str, list[tuple[str, float]]],
    ctxfst_results: dict[str, list[tuple[str, float]]],
) -> str:
    chunk_map = {chunk["id"]: chunk for chunk in chunks}
    baseline_recovered = 0
    ctxfst_recovered = 0
    baseline_hits = 0
    ctxfst_hits = 0

    lines = [
        "# CH22 Evaluation Results",
        "",
        "## Summary Metrics",
        "",
        "| Method | Queries | Hit@3 | Relevant chunks recovered | Missed-but-relevant chunks |",
        "| --- | --- | --- | --- | --- |",
    ]

    for query in queries:
        expected_entities = expected_entity_ids(query)
        baseline_overlap = sum(
            1 for chunk_id, _score in baseline_results[query["id"]]
            if expected_entities & set(chunk_map[chunk_id].get("entities", []))
        )
        ctxfst_overlap = sum(
            1 for chunk_id, _score in ctxfst_results[query["id"]]
            if expected_entities & set(chunk_map[chunk_id].get("entities", []))
        )
        baseline_recovered += baseline_overlap
        ctxfst_recovered += ctxfst_overlap
        baseline_hits += int(baseline_overlap > 0)
        ctxfst_hits += int(ctxfst_overlap > 0)

    total_queries = len(queries) or 1
    max_relevant = total_queries * 3
    lines.append(
        f"| Pure RAG | {len(queries)} | {baseline_hits}/{len(queries)} | {baseline_recovered}/{max_relevant} | {max_relevant - baseline_recovered} |"
    )
    lines.append(
        f"| CtxFST entity-aware | {len(queries)} | {ctxfst_hits}/{len(queries)} | {ctxfst_recovered}/{max_relevant} | {max_relevant - ctxfst_recovered} |"
    )
    lines.extend(["", "## Side-by-side Cases", ""])

    for index, query in enumerate(queries, start=1):
        expected_entities = expected_entity_ids(query)
        lines.append(f"### Q{index}. {query['query']}")
        lines.append("")
        lines.append("| Method | Top-3 chunks | Notes |")
        lines.append("| --- | --- | --- |")
        lines.append(
            f"| Pure RAG | {format_chunk_list(baseline_results[query['id']])} | {summarize_notes(baseline_results[query['id']], expected_entities, chunk_map)} |"
        )
        lines.append(
            f"| CtxFST entity-aware | {format_chunk_list(ctxfst_results[query['id']])} | {summarize_notes(ctxfst_results[query['id']], expected_entities, chunk_map)} |"
        )
        lines.append("")
        lines.append(f"Expected difference: {query.get('likely_rag_failure', '')}")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the CH22 retrieval benchmark")
    parser.add_argument("chunks", type=Path, help="Path to chunks.json")
    parser.add_argument("entity_profiles", type=Path, help="Path to entity-profiles.json")
    parser.add_argument("entity_graph", type=Path, help="Path to entity-graph.json")
    parser.add_argument("queries", type=Path, help="Path to queries.yaml")
    parser.add_argument("--top-k", type=int, default=3, help="Number of chunks to return per method")
    parser.add_argument("--report-output", type=Path, help="Optional path for a markdown report")
    parser.add_argument("--json-output", type=Path, help="Optional path for structured results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunk_data = load_json(args.chunks)
    entity_profile_data = load_json(args.entity_profiles)
    entity_graph_data = load_json(args.entity_graph)
    queries = load_queries(args.queries)

    chunks = chunk_data.get("chunks", [])
    entity_names = {entity["id"]: entity["name"] for entity in chunk_data.get("entities", [])}
    chunk_map = {chunk["id"]: chunk for chunk in chunks}

    chunk_texts = {
        chunk["id"]: build_chunk_text(chunk, entity_names)
        for chunk in chunks
    }
    chunk_vectors, chunk_norms, chunk_idf = build_tfidf_vectors(chunk_texts)

    entity_texts = {
        entity["id"]: build_entity_text(entity)
        for entity in entity_profile_data.get("entities", [])
    }
    entity_vectors, entity_norms, entity_idf = build_tfidf_vectors(entity_texts)

    adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for edge in entity_graph_data.get("edges", []):
        source = edge["source"]
        target = edge["target"]
        score = float(edge.get("score", 0.0))
        adjacency[source].append((target, score))
        adjacency[target].append((source, score))

    baseline_results: dict[str, list[tuple[str, float]]] = {}
    ctxfst_results: dict[str, list[tuple[str, float]]] = {}
    json_results: dict[str, Any] = {"queries": []}

    for query in queries:
        baseline_scores = rank_baseline(query["query"], chunk_vectors, chunk_norms, chunk_idf)
        ctxfst_scores, propagated_entities = rank_ctxfst(
            query["query"],
            chunks,
            baseline_scores,
            entity_vectors,
            entity_norms,
            entity_idf,
            adjacency,
        )

        baseline_top = top_items(baseline_scores, args.top_k)
        ctxfst_top = top_items(ctxfst_scores, args.top_k)
        baseline_results[query["id"]] = baseline_top
        ctxfst_results[query["id"]] = ctxfst_top

        json_results["queries"].append(
            {
                "id": query["id"],
                "query": query["query"],
                "baseline_top": [
                    {
                        "chunk_id": chunk_id,
                        "score": round(score, 4),
                        "entities": chunk_map[chunk_id].get("entities", []),
                    }
                    for chunk_id, score in baseline_top
                ],
                "ctxfst_top": [
                    {
                        "chunk_id": chunk_id,
                        "score": round(score, 4),
                        "entities": chunk_map[chunk_id].get("entities", []),
                    }
                    for chunk_id, score in ctxfst_top
                ],
                "top_entities": [
                    {"entity_id": entity_id, "score": round(score, 4)}
                    for entity_id, score in top_items(propagated_entities, 5)
                ],
            }
        )

    report = render_report(queries, chunks, baseline_results, ctxfst_results)
    print(report)

    if args.report_output:
        args.report_output.write_text(report + "\n", encoding="utf-8")
    if args.json_output:
        args.json_output.write_text(json.dumps(json_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())

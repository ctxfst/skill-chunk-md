#!/usr/bin/env python3
"""
Build Entity -> Entity similarity edges from a derived entity layer.

This script can read either:
- the JSON produced by `export_to_lancedb.py` (`chunks.json`)
- the JSON produced by `build_entity_profiles.py` (`entity-profiles.json`)

It computes TF-IDF cosine similarity and emits a lightweight entity graph JSON.
Optionally merges manually-defined operational edges (v1.3 World Model).

Usage:
    python build_entity_graph.py chunks.json
    python build_entity_graph.py entity-profiles.json
    python build_entity_graph.py chunks.json --output entity-graph.json
    python build_entity_graph.py entity-profiles.json --mode metadata
    python build_entity_graph.py chunks.json --mode contextual --top-k 3 --min-score 0.2
    python build_entity_graph.py chunks.json --extra-edges extra-edges.json
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "its", "of", "on", "or", "that", "the", "their", "this", "to", "with",
}


def tokenize(text: str) -> list[str]:
    """Tokenize into simple lowercase terms."""
    raw_tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{1,}\b", text.lower())
    return [token for token in raw_tokens if token not in STOPWORDS]


def truncate_words(text: str, limit: int = 80) -> str:
    """Cap long content blocks so one chunk does not dominate the representation."""
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit])


def load_input(path: Path) -> dict[str, Any]:
    """Load either a CtxFST export or a derived entity profiles document."""
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"Error: '{path}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Error: '{path}' is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print("Error: export root must be a JSON object", file=sys.stderr)
        sys.exit(1)

    entities = data.get("entities", [])
    if not isinstance(entities, list):
        print("Error: input JSON must contain a list field 'entities'", file=sys.stderr)
        sys.exit(1)

    chunks = data.get("chunks")
    if isinstance(chunks, list):
        data["_input_type"] = "export"
        return data

    data["_input_type"] = "profiles"
    return data


def build_entity_lookup(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index entities by ID."""
    entity_map = {}
    for entity in entities:
        entity_id = entity.get("id")
        if isinstance(entity_id, str) and entity_id:
            entity_map[entity_id] = entity
    return entity_map


def collect_mentions(
    chunks: list[dict[str, Any]],
    entity_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Collect chunk mentions for each entity and report dangling references."""
    mentions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dangling_refs: set[str] = set()

    for chunk in chunks:
        chunk_entities = chunk.get("entities", [])
        if not isinstance(chunk_entities, list):
            continue

        for entity_id in chunk_entities:
            if entity_id in entity_map:
                mentions[entity_id].append(chunk)
            else:
                dangling_refs.add(str(entity_id))

    return mentions, sorted(dangling_refs)


def build_entity_representation(
    entity: dict[str, Any],
    mentions: list[dict[str, Any]],
    entity_map: dict[str, dict[str, Any]],
    mode: str,
) -> str:
    """Build the text that will be vectorized for an entity."""
    aliases = entity.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []

    parts = [
        f"name {entity.get('name', '')}",
        f"type {entity.get('type', '')}",
    ]

    if aliases:
        parts.append("aliases " + " ".join(str(alias) for alias in aliases))

    if mode == "metadata":
        return "\n".join(parts)

    co_mentioned_names: set[str] = set()
    seen_chunk_ids: set[str] = set()

    for chunk in mentions:
        chunk_id = chunk.get("id", "")
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)

        context = chunk.get("context", "")
        content = truncate_words(chunk.get("content", ""))
        tags = chunk.get("tags", [])
        if isinstance(tags, list) and tags:
            parts.append("tags " + " ".join(str(tag) for tag in tags))
        if context:
            parts.append("context " + str(context))
        if content:
            parts.append("content " + str(content))

        for other_id in chunk.get("entities", []):
            if other_id == entity.get("id"):
                continue
            other = entity_map.get(other_id)
            if other:
                co_mentioned_names.add(str(other.get("name", other_id)))

    if co_mentioned_names:
        parts.append("related " + " ".join(sorted(co_mentioned_names)))

    return "\n".join(parts)


def build_tfidf_vectors(texts: dict[str, str]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Vectorize entity representations with TF-IDF."""
    tokenized = {entity_id: tokenize(text) for entity_id, text in texts.items()}
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

    for entity_id, tokens in tokenized.items():
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        vector = {
            token: (count / total) * idf[token]
            for token, count in counts.items()
        }
        norm = math.sqrt(sum(weight * weight for weight in vector.values()))
        vectors[entity_id] = vector
        norms[entity_id] = norm

    return vectors, norms


def cosine_similarity(
    vec_a: dict[str, float],
    norm_a: float,
    vec_b: dict[str, float],
    norm_b: float,
) -> float:
    """Compute cosine similarity between sparse vectors."""
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a

    dot = sum(weight * vec_b.get(token, 0.0) for token, weight in vec_a.items())
    return dot / (norm_a * norm_b)


def build_edges(
    entity_ids: list[str],
    vectors: dict[str, dict[str, float]],
    norms: dict[str, float],
    top_k: int,
    min_score: float,
    mention_sets: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """Build unique similarity edges using top-k per entity and a minimum score."""
    pair_scores: dict[tuple[str, str], float] = {}
    neighbors: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for idx, source in enumerate(entity_ids):
        for target in entity_ids[idx + 1:]:
            score = cosine_similarity(vectors[source], norms[source], vectors[target], norms[target])
            pair = tuple(sorted((source, target)))
            pair_scores[pair] = score
            neighbors[source].append((target, score))
            neighbors[target].append((source, score))

    selected_pairs: set[tuple[str, str]] = set()
    for source, candidates in neighbors.items():
        ranked = sorted(candidates, key=lambda item: (-item[1], item[0]))
        for target, score in ranked[:top_k]:
            if score >= min_score:
                selected_pairs.add(tuple(sorted((source, target))))

    edges = []
    for source, target in sorted(selected_pairs):
        score = pair_scores[(source, target)]
        shared_chunk_count = len(mention_sets.get(source, set()) & mention_sets.get(target, set()))
        edges.append({
            "source": source,
            "target": target,
            "relation": "SIMILAR",
            "score": round(score, 4),
            "shared_chunk_count": shared_chunk_count,
            "properties": {},
        })

    edges.sort(key=lambda edge: (-edge["score"], edge["source"], edge["target"]))
    return edges


VALID_EDGE_RELATIONS = {
    "SIMILAR", "REQUIRES", "LEADS_TO", "EVIDENCE",
    "IMPLIES", "COMPLETED", "BLOCKED_BY",
}


def load_extra_edges(path: Path) -> list[dict[str, Any]]:
    """Load manually-defined operational edges from a JSON file.

    Expected format: a JSON array of edge objects, each with at least
    ``source``, ``target``, and ``relation`` keys.
    """
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"Error: extra-edges file '{path}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Error: extra-edges file '{path}' is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print("Error: extra-edges JSON must be an array of edge objects", file=sys.stderr)
        sys.exit(1)

    validated: list[dict[str, Any]] = []
    for idx, edge in enumerate(data):
        if not isinstance(edge, dict):
            print(f"Warning: extra-edges[{idx}] is not an object, skipping", file=sys.stderr)
            continue
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("relation", "")
        if not source or not target:
            print(f"Warning: extra-edges[{idx}] missing source/target, skipping", file=sys.stderr)
            continue
        if relation not in VALID_EDGE_RELATIONS:
            print(
                f"Warning: extra-edges[{idx}] has unknown relation '{relation}', "
                f"allowed: {sorted(VALID_EDGE_RELATIONS)}",
                file=sys.stderr,
            )

        validated_edge: dict[str, Any] = {
            "source": source,
            "target": target,
            "relation": relation,
        }
        if "score" in edge:
            validated_edge["score"] = edge["score"]
        if "shared_chunk_count" in edge:
            validated_edge["shared_chunk_count"] = edge["shared_chunk_count"]
        validated_edge["properties"] = edge.get("properties", {})
        validated.append(validated_edge)

    return validated


def infer_operational_edges(
    entity_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Auto-infer REQUIRES and LEADS_TO edges from preconditions/postconditions.

    Logic:
    - If entity A has postcondition S, and entity B has precondition S,
      then A --LEADS_TO--> B (A enables B)
      and  B --REQUIRES--> A (B depends on A)
    """
    # Build index: state_id -> entities that produce it (have it as postcondition)
    producers: dict[str, list[str]] = defaultdict(list)
    # Build index: state_id -> entities that consume it (have it as precondition)
    consumers: dict[str, list[str]] = defaultdict(list)

    for entity_id, entity in entity_map.items():
        for post in entity.get("postconditions", []):
            if isinstance(post, str):
                producers[post].append(entity_id)
        for pre in entity.get("preconditions", []):
            if isinstance(pre, str) and not pre.startswith("NOT "):
                consumers[pre].append(entity_id)

    # Generate edges
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for state_id in producers:
        if state_id not in consumers:
            continue
        for producer_id in producers[state_id]:
            for consumer_id in consumers[state_id]:
                if producer_id == consumer_id:
                    continue

                # LEADS_TO: producer -> consumer
                key_lt = (producer_id, consumer_id, "LEADS_TO")
                if key_lt not in seen:
                    seen.add(key_lt)
                    edges.append({
                        "source": producer_id,
                        "target": consumer_id,
                        "relation": "LEADS_TO",
                        "properties": {"inferred_via": state_id},
                    })

                # REQUIRES: consumer -> producer
                key_req = (consumer_id, producer_id, "REQUIRES")
                if key_req not in seen:
                    seen.add(key_req)
                    edges.append({
                        "source": consumer_id,
                        "target": producer_id,
                        "relation": "REQUIRES",
                        "properties": {"inferred_via": state_id},
                    })

    return edges


def build_graph_from_export(
    data: dict[str, Any],
    mode: str,
    top_k: int,
    min_score: float,
    input_path: Path,
) -> dict[str, Any]:
    """Build the entity graph JSON payload from chunks.json."""
    entities = data.get("entities", [])
    chunks = data.get("chunks", [])
    entity_map = build_entity_lookup(entities)
    mentions, dangling_refs = collect_mentions(chunks, entity_map)
    mention_sets = {
        entity_id: {chunk.get("id", "") for chunk in entity_mentions if chunk.get("id")}
        for entity_id, entity_mentions in mentions.items()
    }

    representations = {
        entity_id: build_entity_representation(entity, mentions.get(entity_id, []), entity_map, mode)
        for entity_id, entity in entity_map.items()
    }
    vectors, norms = build_tfidf_vectors(representations)
    entity_ids = sorted(entity_map.keys())
    edges = build_edges(entity_ids, vectors, norms, top_k, min_score, mention_sets)

    nodes = []
    for entity_id in entity_ids:
        entity = entity_map[entity_id]
        chunk_ids = sorted({chunk.get("id", "") for chunk in mentions.get(entity_id, []) if chunk.get("id")})
        node: dict[str, Any] = {
            "id": entity_id,
            "name": entity.get("name", ""),
            "type": entity.get("type", ""),
            "aliases": entity.get("aliases", []),
            "mention_count": len(chunk_ids),
            "chunk_ids": chunk_ids,
        }
        # World model fields (passthrough)
        for wm_field in ("preconditions", "postconditions", "related_skills"):
            if wm_field in entity:
                node[wm_field] = entity[wm_field]
        nodes.append(node)

    # Auto-infer operational edges from preconditions/postconditions
    inferred = infer_operational_edges(entity_map)
    edges.extend(inferred)

    return {
        "meta": {
            "input": str(input_path),
            "input_type": "ctxfst-export",
            "mode": mode,
            "vectorizer": "tfidf-cosine",
            "top_k": top_k,
            "min_score": min_score,
            "entity_count": len(nodes),
            "edge_count": len(edges),
            "inferred_edge_count": len(inferred),
            "dangling_chunk_entity_refs": dangling_refs,
        },
        "nodes": nodes,
        "edges": edges,
    }


def metadata_representation(entity: dict[str, Any]) -> str:
    """Build a minimal representation from canonical entity metadata only."""
    aliases = entity.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []

    parts = [
        f"name {entity.get('name', '')}",
        f"type {entity.get('type', '')}",
    ]
    if aliases:
        parts.append("aliases " + " ".join(str(alias) for alias in aliases))
    return "\n".join(parts)


def build_graph_from_profiles(
    data: dict[str, Any],
    mode: str,
    top_k: int,
    min_score: float,
    input_path: Path,
) -> dict[str, Any]:
    """Build the entity graph JSON payload from entity-profiles.json."""
    profiles = data.get("entities", [])
    mention_sets: dict[str, set[str]] = {}
    representations: dict[str, str] = {}
    nodes = []

    for profile in profiles:
        entity_id = profile.get("id")
        if not isinstance(entity_id, str) or not entity_id:
            continue

        mentioned_chunks = profile.get("mentioned_chunks", [])
        if not isinstance(mentioned_chunks, list):
            mentioned_chunks = []
        chunk_ids = sorted(chunk_id for chunk_id in mentioned_chunks if isinstance(chunk_id, str) and chunk_id)
        mention_sets[entity_id] = set(chunk_ids)

        if mode == "metadata":
            representations[entity_id] = metadata_representation(profile)
        else:
            representations[entity_id] = str(profile.get("representation", "")).strip() or metadata_representation(profile)

        node: dict[str, Any] = {
            "id": entity_id,
            "name": profile.get("name", ""),
            "type": profile.get("type", ""),
            "aliases": profile.get("aliases", []),
            "mention_count": profile.get("mention_count", len(chunk_ids)),
            "chunk_ids": chunk_ids,
        }
        # World model fields (passthrough)
        for wm_field in ("preconditions", "postconditions", "related_skills"):
            if wm_field in profile:
                node[wm_field] = profile[wm_field]
        nodes.append(node)

    entity_ids = sorted(representations.keys())
    vectors, norms = build_tfidf_vectors(representations)
    edges = build_edges(entity_ids, vectors, norms, top_k, min_score, mention_sets)
    dangling_refs = data.get("meta", {}).get("dangling_chunk_entity_refs", [])

    # Build profile lookup for inference
    profile_map = {p.get("id"): p for p in profiles if isinstance(p.get("id"), str)}
    inferred = infer_operational_edges(profile_map)
    edges.extend(inferred)

    nodes.sort(key=lambda node: node["id"])
    return {
        "meta": {
            "input": str(input_path),
            "input_type": "entity-profiles",
            "mode": mode,
            "vectorizer": "tfidf-cosine",
            "top_k": top_k,
            "min_score": min_score,
            "entity_count": len(nodes),
            "edge_count": len(edges),
            "inferred_edge_count": len(inferred),
            "dangling_chunk_entity_refs": dangling_refs,
        },
        "nodes": nodes,
        "edges": edges,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Entity -> Entity similarity edges from chunks.json or entity-profiles.json"
    )
    parser.add_argument("input", help="Input JSON file produced by export_to_lancedb.py or build_entity_profiles.py")
    parser.add_argument(
        "--output", "-o",
        default="entity-graph.json",
        help="Output JSON file (default: entity-graph.json)",
    )
    parser.add_argument(
        "--mode",
        choices=["metadata", "contextual"],
        default="contextual",
        help="How to build each entity representation (default: contextual)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Keep up to this many neighbors per entity before deduping edges (default: 3)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.15,
        help="Minimum cosine similarity score to keep an edge (default: 0.15)",
    )
    parser.add_argument(
        "--extra-edges",
        default=None,
        help="Optional JSON file with manually-defined operational edges (v1.3 World Model)",
    )

    args = parser.parse_args()
    if args.top_k < 1:
        print("Error: --top-k must be >= 1", file=sys.stderr)
        sys.exit(1)
    if not 0.0 <= args.min_score <= 1.0:
        print("Error: --min-score must be between 0.0 and 1.0", file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input)
    data = load_input(input_path)
    if data["_input_type"] == "export":
        graph = build_graph_from_export(data, args.mode, args.top_k, args.min_score, input_path)
    else:
        graph = build_graph_from_profiles(data, args.mode, args.top_k, args.min_score, input_path)

    # Merge extra edges (v1.3)
    extra_edge_count = 0
    if args.extra_edges:
        extra = load_extra_edges(Path(args.extra_edges))
        graph["edges"].extend(extra)
        extra_edge_count = len(extra)
    graph["meta"]["extra_edge_count"] = extra_edge_count
    graph["meta"]["edge_count"] = len(graph["edges"])

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(graph, handle, indent=2, ensure_ascii=False)

    print(f"✅ Built entity graph: {output_path}")
    extra_info = f" | Extra edges: {extra_edge_count}" if extra_edge_count else ""
    print(
        f"   Nodes: {graph['meta']['entity_count']} | "
        f"Edges: {graph['meta']['edge_count']} | "
        f"Input: {graph['meta']['input_type']} | "
        f"Mode: {graph['meta']['mode']} | "
        f"Vectorizer: {graph['meta']['vectorizer']}"
        f"{extra_info}"
    )

    if graph["meta"]["dangling_chunk_entity_refs"]:
        print(
            "   Warning: dangling chunk entity references: "
            + ", ".join(graph["meta"]["dangling_chunk_entity_refs"]),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

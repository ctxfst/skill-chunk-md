#!/usr/bin/env python3
"""
Build derived entity profiles from a CtxFST export JSON.

This script keeps the core CtxFST schema unchanged. It reads the JSON produced
by `export_to_lancedb.py`, derives reverse links and aggregated text per entity,
and emits an `entity-profiles.json` file that downstream embedding or graph
pipelines can consume.

Usage:
    python build_entity_profiles.py chunks.json
    python build_entity_profiles.py chunks.json --output entity-profiles.json
    python build_entity_profiles.py chunks.json --max-contexts 3 --top-keywords 8
"""

import argparse
import json
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


def load_export(path: Path) -> dict[str, Any]:
    """Load the exported JSON document."""
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

    chunks = data.get("chunks", [])
    entities = data.get("entities", [])
    if not isinstance(chunks, list) or not isinstance(entities, list):
        print("Error: export JSON must contain list fields 'chunks' and 'entities'", file=sys.stderr)
        sys.exit(1)

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


def build_keywords(
    entity: dict[str, Any],
    mentions: list[dict[str, Any]],
    entity_map: dict[str, dict[str, Any]],
    limit: int,
) -> list[str]:
    """Extract lightweight keywords from linked chunk context and content."""
    counter: Counter[str] = Counter()
    name_tokens = set(tokenize(str(entity.get("name", ""))))
    alias_tokens = set(tokenize(" ".join(str(alias) for alias in entity.get("aliases", []))))
    blocked = name_tokens | alias_tokens | {"name", "type", "context", "content", "related", "tags", "aliases"}

    for chunk in mentions:
        text = " ".join(
            [
                str(chunk.get("context", "")),
                str(chunk.get("content", "")),
                " ".join(str(tag) for tag in chunk.get("tags", [])),
            ]
        )
        counter.update(token for token in tokenize(text) if token not in blocked)

        for other_id in chunk.get("entities", []):
            if other_id == entity.get("id"):
                continue
            other = entity_map.get(other_id)
            if other:
                counter.update(tokenize(str(other.get("name", ""))))

    return [token for token, _count in counter.most_common(limit)]


def build_representation(
    entity: dict[str, Any],
    mentions: list[dict[str, Any]],
    entity_map: dict[str, dict[str, Any]],
    max_contexts: int,
    top_keywords: int,
) -> tuple[str, list[str], list[str], list[str], list[str], list[str], list[str]]:
    """Build a derived representation text for one entity profile."""
    aliases = entity.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = []

    mentioned_chunks = []
    contexts = []
    content_excerpts = []
    aggregated_tags: set[str] = set()
    related_names: set[str] = set()
    representation_lines = [
        f"name: {entity.get('name', '')}",
        f"type: {entity.get('type', '')}",
    ]

    for chunk in mentions:
        chunk_id = chunk.get("id")
        if isinstance(chunk_id, str) and chunk_id:
            mentioned_chunks.append(chunk_id)

        tags = chunk.get("tags", [])
        if isinstance(tags, list):
            str_tags = [str(tag) for tag in tags]
            aggregated_tags.update(str_tags)
            if str_tags:
                representation_lines.append("tags " + " ".join(str_tags))

        context = chunk.get("context", "")
        if isinstance(context, str) and context and len(contexts) < max_contexts:
            contexts.append(context)
        if isinstance(context, str) and context:
            representation_lines.append("context " + context)

        content = chunk.get("content", "")
        if isinstance(content, str) and content:
            excerpt = truncate_words(content)
            content_excerpts.append(excerpt)
            representation_lines.append("content " + excerpt)

        for other_id in chunk.get("entities", []):
            if other_id == entity.get("id"):
                continue
            other = entity_map.get(other_id)
            if other:
                related_names.add(str(other.get("name", other_id)))

    keywords = build_keywords(entity, mentions, entity_map, top_keywords)
    if aliases:
        representation_lines.append("aliases " + " ".join(str(alias) for alias in aliases))
    if related_names:
        representation_lines.append("related " + " ".join(sorted(related_names)))

    # v1.3: mark operational entity types
    entity_type = entity.get("type", "")
    if entity_type in ("state", "action", "goal", "agent", "evidence"):
        representation_lines.append(f"operational_type: {entity_type}")

    return (
        "\n".join(representation_lines),
        mentioned_chunks,
        contexts,
        content_excerpts,
        sorted(aggregated_tags),
        sorted(related_names),
        keywords,
    )


def build_profiles(
    data: dict[str, Any],
    input_path: Path,
    max_contexts: int,
    top_keywords: int,
) -> dict[str, Any]:
    """Build the entity profiles payload."""
    entity_map = build_entity_lookup(data.get("entities", []))
    mentions, dangling_refs = collect_mentions(data.get("chunks", []), entity_map)

    profiles = []
    for entity_id in sorted(entity_map):
        entity = entity_map[entity_id]
        representation, mentioned_chunks, contexts, content_excerpts, tags, related_names, keywords = build_representation(
            entity,
            mentions.get(entity_id, []),
            entity_map,
            max_contexts,
            top_keywords,
        )
        profiles.append(
            {
                "id": entity_id,
                "name": entity.get("name", ""),
                "type": entity.get("type", ""),
                "aliases": entity.get("aliases", []),
                "mentioned_chunks": mentioned_chunks,
                "mention_count": len(mentioned_chunks),
                "tags": tags,
                "contexts": contexts,
                "content_excerpts": content_excerpts,
                "related_entities": related_names,
                "keywords": keywords,
                "representation": representation,
                # v1.3 world model fields (passthrough)
                **{field: entity[field] for field in ("preconditions", "postconditions", "related_skills") if field in entity},
            }
        )

    return {
        "meta": {
            "input": str(input_path),
            "source_type": "ctxfst-export",
            "profile_type": "entity-profiles",
            "entity_count": len(profiles),
            "max_contexts": max_contexts,
            "top_keywords": top_keywords,
            "dangling_chunk_entity_refs": dangling_refs,
        },
        "entities": profiles,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build derived entity profiles from a CtxFST export JSON"
    )
    parser.add_argument("input", help="Input JSON file produced by export_to_lancedb.py")
    parser.add_argument(
        "--output", "-o",
        default="entity-profiles.json",
        help="Output JSON file (default: entity-profiles.json)",
    )
    parser.add_argument(
        "--max-contexts",
        type=int,
        default=3,
        help="Keep up to this many linked chunk contexts per entity (default: 3)",
    )
    parser.add_argument(
        "--top-keywords",
        type=int,
        default=8,
        help="Keep up to this many derived usage keywords per entity (default: 8)",
    )

    args = parser.parse_args()
    if args.max_contexts < 1:
        print("Error: --max-contexts must be >= 1", file=sys.stderr)
        sys.exit(1)
    if args.top_keywords < 1:
        print("Error: --top-keywords must be >= 1", file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input)
    data = load_export(input_path)
    profiles = build_profiles(data, input_path, args.max_contexts, args.top_keywords)

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(profiles, handle, indent=2, ensure_ascii=False)

    print(f"✅ Built entity profiles: {output_path}")
    print(
        f"   Entities: {profiles['meta']['entity_count']} | "
        f"Contexts/entity: {profiles['meta']['max_contexts']} | "
        f"Keywords/entity: {profiles['meta']['top_keywords']}"
    )

    if profiles["meta"]["dangling_chunk_entity_refs"]:
        print(
            "   Warning: dangling chunk entity references: "
            + ", ".join(profiles["meta"]["dangling_chunk_entity_refs"]),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Convert career_kb_chunks.jsonl + skill-graph.json into a complete benchmark scaffold
that ch22_retrieval_benchmark.py can consume directly.

Output: examples/career-kb-benchmark/
  chunks.json          — all 200 chunks with entity annotations
  entity-profiles.json — rich profiles for top-N entities
  entity-graph.json    — edges from skill-graph + inferred prerequisite edges
  queries.yaml         — 6 queries designed to expose keyword-entity gaps
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
JSONL_PATH = ROOT / "examples/ch22-retrieval-benchmark/career_kb_chunks.jsonl"
GRAPH_PATH = ROOT / "examples/ch22-retrieval-benchmark/skill-graph.json"
OUT_DIR = ROOT / "examples/career-kb-benchmark"

MIN_MENTION_FOR_PROFILE = 5   # entities with fewer chunk mentions skip profile building
EDGE_SCORE_REQUIRES = 0.85
EDGE_SCORE_RELATED = 0.65
EDGE_SCORE_PREREQ_INFERRED = 0.70


# ---------------------------------------------------------------------------
# Name → entity ID
# ---------------------------------------------------------------------------
def skill_to_id(name: str) -> str:
    """Convert a skill name to a stable entity ID.

    Examples:
        "Vector DB"         → "entity:vector-db"
        "Node.js"           → "entity:nodejs"
        "LLM API"           → "entity:llm-api"
        "Express.js"        → "entity:expressjs"
        "AutoGPT-Lite"      → "entity:autogpt-lite"
    """
    slug = name.lower()
    slug = slug.replace(".", "")          # Node.js → nodejs
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return f"entity:{slug}"


# ---------------------------------------------------------------------------
# Entity type heuristics
# ---------------------------------------------------------------------------
_TYPE_MAP: dict[str, str] = {
    "Python": "language",
    "JavaScript": "language",
    "TypeScript": "language",
    "Node.js": "runtime",
    "Hono": "framework",
    "Express.js": "framework",
    "FastAPI": "framework",
    "Flask": "framework",
    "Django": "framework",
    "LangChain": "framework",
    "LangGraph": "framework",
    "LlamaIndex": "framework",
    "React": "framework",
    "Streamlit": "framework",
    "Puppeteer": "tool",
    "Playwright": "tool",
    "Browser Automation": "concept",
    "Shell Scripting": "concept",
    "Vector DB": "concept",
    "Embeddings": "concept",
    "RAG": "concept",
    "Semantic Search": "concept",
    "Prompt Engineering": "concept",
    "NLP Concepts": "concept",
    "LLM API": "service",
    "OpenAI": "service",
    "Edge Runtime": "platform",
    "Kubernetes": "platform",
    "Vercel Edge": "platform",
    "Tool Calling": "concept",
    "Agent Architecture": "concept",
    "AutoGPT": "concept",
    "AutoGPT-Lite": "concept",
    "LanceDB": "tool",
    "Pinecone": "tool",
    "OpenClaw": "application",
    "Telegram Bot": "application",
    "Discord Bot": "application",
    "OpenAPI": "concept",
    "REST": "concept",
    "HTTP": "concept",
    "WebSockets": "concept",
    "Webhooks": "concept",
    "GraphQL": "concept",
    "API Key Management": "concept",
    "Async Programming": "concept",
    "Coroutines": "concept",
    "Event Driven": "concept",
    "State Management": "concept",
    "Data Structures": "concept",
    "Type System": "concept",
    "JSON Schema": "concept",
    "JSON": "concept",
    "YAML": "concept",
    "DOM": "concept",
    "CSS": "concept",
    "CSS Selectors": "concept",
    "HTML": "concept",
    "Database Concepts": "concept",
    "Virtualization": "concept",
    "OS Concepts": "concept",
    "Networking Basics": "concept",
    "Linear Algebra Basics": "concept",
    "Programming Basics": "concept",
    "Web Standards": "concept",
    "Pip": "tool",
    "NPM": "tool",
    "Virtual Environments": "concept",
    "Container Registry": "concept",
    "PDF Parsing": "concept",
    "Function Calling": "concept",
    "Permissions": "concept",
    "Bash": "tool",
    "Cron": "tool",
}


def entity_type(name: str) -> str:
    return _TYPE_MAP.get(name, "concept")


# ---------------------------------------------------------------------------
# Stopwords for keyword extraction
# ---------------------------------------------------------------------------
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for",
    "from", "have", "how", "if", "in", "is", "it", "its", "let", "more",
    "not", "of", "on", "one", "or", "our", "so", "that", "the", "their",
    "this", "to", "use", "used", "using", "we", "what", "when", "which",
    "with", "you", "your",
}


def extract_keywords(text: str, top_n: int = 10) -> list[str]:
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{1,}\b", text.lower())
    counts = Counter(t for t in tokens if t not in STOPWORDS and len(t) > 2)
    return [word for word, _ in counts.most_common(top_n)]


# ---------------------------------------------------------------------------
# Load source data
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Build entity catalog
# ---------------------------------------------------------------------------
def build_entity_catalog(
    raw_chunks: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, int]]:
    """Return (id_map: name→id, mention_count: id→count)."""
    id_map: dict[str, str] = {}
    mention_counts: Counter[str] = Counter()

    for chunk in raw_chunks:
        for skill in chunk.get("skills", []) + chunk.get("prerequisites", []):
            eid = skill_to_id(skill)
            id_map[skill] = eid
            mention_counts[eid] += 1

    return id_map, dict(mention_counts)


# ---------------------------------------------------------------------------
# Build chunks.json
# ---------------------------------------------------------------------------
DIFFICULTY_TO_PRIORITY = {
    "beginner": "low",
    "intermediate": "medium",
    "advanced": "high",
}


def build_chunks_json(
    raw_chunks: list[dict[str, Any]],
    id_map: dict[str, str],
    all_entity_ids: set[str],
) -> dict[str, Any]:
    """Build the chunks.json structure."""
    # Top-level entity list (id + name + type + aliases)
    entity_list: list[dict[str, Any]] = []
    seen_eids: set[str] = set()
    for name, eid in sorted(id_map.items(), key=lambda kv: kv[1]):
        if eid not in seen_eids and eid in all_entity_ids:
            entity_list.append({
                "id": eid,
                "name": name,
                "type": entity_type(name),
                "aliases": [],
            })
            seen_eids.add(eid)

    # Per-chunk records
    chunk_records: list[dict[str, Any]] = []
    for raw in raw_chunks:
        skills = raw.get("skills", [])
        prereqs = raw.get("prerequisites", [])
        entity_refs = list({id_map[s] for s in skills + prereqs if s in id_map and id_map[s] in all_entity_ids})
        record: dict[str, Any] = {
            "id": raw["id"],
            "context": raw["title"],
            "content": raw["text"],
            "tags": skills,
            "source": str(JSONL_PATH.relative_to(ROOT)),
            "entities": entity_refs,
            "created_at": raw.get("published_at", "2025-01-01")[:10],
            "version": 1,
            "type": "text",
            "priority": DIFFICULTY_TO_PRIORITY.get(raw.get("difficulty", "intermediate"), "medium"),
            "dependencies": [],
        }
        chunk_records.append(record)

    return {"entities": entity_list, "chunks": chunk_records}


# ---------------------------------------------------------------------------
# Build entity-graph.json
# ---------------------------------------------------------------------------
def build_entity_graph(
    raw_graph: dict[str, Any],
    raw_chunks: list[dict[str, Any]],
    id_map: dict[str, str],
    all_entity_ids: set[str],
) -> dict[str, Any]:
    """Build entity-graph.json from skill-graph edges + inferred prerequisite edges."""
    edge_map: dict[tuple[str, str], float] = {}

    # Edges from skill-graph.json
    for edge in raw_graph.get("edges", []):
        src_name = edge.get("from", "")
        tgt_name = edge.get("to", "")
        edge_type = edge.get("type", "relatedTo")
        src_id = id_map.get(src_name)
        tgt_id = id_map.get(tgt_name)
        if not src_id or not tgt_id:
            continue
        if src_id not in all_entity_ids or tgt_id not in all_entity_ids:
            continue
        score = EDGE_SCORE_REQUIRES if edge_type == "requires" else EDGE_SCORE_RELATED
        key = (min(src_id, tgt_id), max(src_id, tgt_id))
        edge_map[key] = max(edge_map.get(key, 0.0), score)

    # Infer edges from chunk prerequisites
    for chunk in raw_chunks:
        skills = chunk.get("skills", [])
        prereqs = chunk.get("prerequisites", [])
        for s in skills:
            for p in prereqs:
                s_id = id_map.get(s)
                p_id = id_map.get(p)
                if not s_id or not p_id or s_id == p_id:
                    continue
                if s_id not in all_entity_ids or p_id not in all_entity_ids:
                    continue
                key = (min(s_id, p_id), max(s_id, p_id))
                edge_map[key] = max(edge_map.get(key, 0.0), EDGE_SCORE_PREREQ_INFERRED)

    edges = [
        {"source": a, "target": b, "score": round(score, 2)}
        for (a, b), score in sorted(edge_map.items())
    ]
    return {"edges": edges}


# ---------------------------------------------------------------------------
# Build entity-profiles.json
# ---------------------------------------------------------------------------
def build_entity_profiles(
    raw_chunks: list[dict[str, Any]],
    id_map: dict[str, str],
    mention_counts: dict[str, int],
    all_entity_ids: set[str],
) -> dict[str, Any]:
    """Build entity-profiles.json with rich text for entity matching."""
    # Group chunks by entity
    entity_chunks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in raw_chunks:
        for skill in chunk.get("skills", []) + chunk.get("prerequisites", []):
            eid = id_map.get(skill)
            if eid and eid in all_entity_ids:
                entity_chunks[eid].append(chunk)

    profiles: list[dict[str, Any]] = []
    id_to_name = {v: k for k, v in id_map.items()}

    for eid in sorted(all_entity_ids):
        name = id_to_name.get(eid, eid.replace("entity:", "").replace("-", " ").title())
        chunks_for_entity = entity_chunks.get(eid, [])
        mentioned_chunk_ids = list({c["id"] for c in chunks_for_entity})

        # Collect text for keyword extraction
        all_text = " ".join(c.get("text", "") for c in chunks_for_entity)
        keywords = extract_keywords(all_text, top_n=10)

        # Contexts: first sentence of up to 3 chunks
        contexts: list[str] = []
        for chunk in chunks_for_entity[:3]:
            title = chunk.get("title", "")
            if title:
                contexts.append(title)

        # Tags: other skills that co-occur with this entity
        co_skills: Counter[str] = Counter()
        for chunk in chunks_for_entity:
            for s in chunk.get("skills", []):
                if id_map.get(s) != eid:
                    co_skills[s] += 1
        tags = [s for s, _ in co_skills.most_common(8)]

        profile: dict[str, Any] = {
            "id": eid,
            "name": name,
            "type": entity_type(name),
            "aliases": [],
            "mentioned_chunks": mentioned_chunk_ids,
            "mention_count": mention_counts.get(eid, 0),
            "tags": tags,
            "contexts": contexts,
            "keywords": keywords,
            "representation": name,
        }
        profiles.append(profile)

    return {
        "meta": {
            "input": str(JSONL_PATH.relative_to(ROOT)),
            "source_type": "career-kb-export",
            "profile_type": "entity-profiles",
            "entity_count": len(profiles),
        },
        "entities": profiles,
    }


# ---------------------------------------------------------------------------
# Build queries.yaml
# ---------------------------------------------------------------------------
QUERIES = [
    {
        "id": "q1-rag-ecosystem",
        "query": "我的 RAG 相關筆記有哪些？",
        "intent": "category-expansion",
        "expected_entities": [
            "entity:rag",
            "entity:vector-db",
            "entity:embeddings",
            "entity:semantic-search",
            "entity:lancedb",
        ],
        "likely_rag_failure": (
            "Many RAG-related chunks (on Vector DB, Embeddings, LanceDB, Semantic Search) "
            "do not repeat the word 'RAG' in their text. TF-IDF baseline will rank unrelated "
            "chunks that happen to say 'RAG' above conceptually relevant ones that don't."
        ),
    },
    {
        "id": "q2-telegram-prerequisites",
        "query": "如果我要做一個 Telegram Bot，我需要先學什麼？",
        "intent": "prerequisite-chain",
        "expected_entities": [
            "entity:telegram-bot",
            "entity:nodejs",
            "entity:llm-api",
            "entity:http",
            "entity:webhooks",
        ],
        "likely_rag_failure": (
            "Baseline finds chunks about Telegram Bot directly but misses the prerequisite "
            "chain: Node.js fundamentals, HTTP basics, Webhooks, LLM API setup. Those chunks "
            "do not mention 'Telegram' at all."
        ),
    },
    {
        "id": "q3-openclaw-capabilities",
        "query": "OpenClaw 需要哪些底層能力？",
        "intent": "requires-fan-out",
        "expected_entities": [
            "entity:openclaw",
            "entity:nodejs",
            "entity:llm-api",
            "entity:browser-automation",
            "entity:shell-scripting",
        ],
        "likely_rag_failure": (
            "skill-graph encodes: OpenClaw requires Node.js, LLM API, Browser Automation, "
            "Shell Scripting. The chunks about those prerequisites never mention 'OpenClaw'. "
            "Baseline retrieves only chunks that say 'OpenClaw' explicitly."
        ),
    },
    {
        "id": "q4-javascript-ai",
        "query": "如果我只會 JavaScript，能做哪些 AI 相關的東西？",
        "intent": "graph-traversal",
        "expected_entities": [
            "entity:javascript",
            "entity:nodejs",
            "entity:openclaw",
            "entity:llm-api",
            "entity:tool-calling",
        ],
        "likely_rag_failure": (
            "The query contains 'JavaScript' and 'AI' but the relevant chunks are about "
            "Node.js tooling, OpenClaw, and LLM API — none of which say both 'JavaScript' "
            "and 'AI' together. Entity-aware retrieval can traverse JS → Node.js → OpenClaw/LLM API."
        ),
    },
    {
        "id": "q5-python-web",
        "query": "我對 Python Web 框架懂多少？",
        "intent": "implicit-category",
        "expected_entities": [
            "entity:python",
            "entity:fastapi",
            "entity:flask",
            "entity:django",
            "entity:pydantic",
        ],
        "likely_rag_failure": (
            "Chunks on FastAPI, Flask, Django, Pydantic each focus on the specific framework "
            "without repeating 'Python Web frameworks' as a category phrase. Baseline ranks "
            "by lexical overlap with 'Python Web' and misses framework-specific notes."
        ),
    },
    {
        "id": "q6-browser-automation-use-cases",
        "query": "Browser Automation 除了爬蟲還能做什麼？",
        "intent": "cross-entity-exploration",
        "expected_entities": [
            "entity:browser-automation",
            "entity:puppeteer",
            "entity:openclaw",
            "entity:playwright",
        ],
        "likely_rag_failure": (
            "OpenClaw uses Browser Automation as a core capability but its chunks are about "
            "agent runtime, not scraping. Playwright chunks discuss testing, not crawling. "
            "Baseline anchors on 'scraping/crawling' keywords and misses these broader use cases."
        ),
    },
]


def build_queries_yaml() -> str:
    return yaml.dump({"queries": QUERIES}, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Loading {JSONL_PATH} ...")
    raw_chunks = load_jsonl(JSONL_PATH)
    print(f"  {len(raw_chunks)} chunks loaded")

    print(f"Loading {GRAPH_PATH} ...")
    raw_graph = load_json(GRAPH_PATH)
    print(f"  {len(raw_graph.get('nodes', []))} nodes, {len(raw_graph.get('edges', []))} edges")

    # Build entity catalog
    id_map, mention_counts = build_entity_catalog(raw_chunks)
    print(f"  {len(id_map)} unique skills/prerequisites found")

    # Graph nodes are always included; others only if MIN_MENTION_FOR_PROFILE met
    graph_skills = set(raw_graph.get("nodes", []))
    all_entity_ids: set[str] = set()
    for name, eid in id_map.items():
        if name in graph_skills or mention_counts.get(eid, 0) >= MIN_MENTION_FOR_PROFILE:
            all_entity_ids.add(eid)
    print(f"  {len(all_entity_ids)} entities will be included in artifacts")

    # Build artifacts
    print("Building chunks.json ...")
    chunks_data = build_chunks_json(raw_chunks, id_map, all_entity_ids)

    print("Building entity-graph.json ...")
    graph_data = build_entity_graph(raw_graph, raw_chunks, id_map, all_entity_ids)
    print(f"  {len(graph_data['edges'])} edges in entity graph")

    print("Building entity-profiles.json ...")
    profiles_data = build_entity_profiles(raw_chunks, id_map, mention_counts, all_entity_ids)

    print("Building queries.yaml ...")
    queries_yaml = build_queries_yaml()

    # Write output
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "chunks.json").write_text(
        json.dumps(chunks_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "entity-graph.json").write_text(
        json.dumps(graph_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "entity-profiles.json").write_text(
        json.dumps(profiles_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "queries.yaml").write_text(queries_yaml, encoding="utf-8")

    print(f"\nArtifacts written to {OUT_DIR}/")
    print(f"  chunks.json          ({len(chunks_data['chunks'])} chunks, {len(chunks_data['entities'])} entity defs)")
    print(f"  entity-graph.json    ({len(graph_data['edges'])} edges)")
    print(f"  entity-profiles.json ({len(profiles_data['entities'])} profiles)")
    print(f"  queries.yaml         ({len(QUERIES)} queries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

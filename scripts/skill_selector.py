#!/usr/bin/env python3
"""
Deterministic Skill Selector for CtxFST v1.3 World Model Layer.

Scans SKILL.md files, matches preconditions against the current world state,
and outputs ranked candidate skills. No LLM dependency — purely rule-based.

Library API:
    from skill_selector import scan_skills, select_candidates

CLI Usage:
    python skill_selector.py state.json --skill-dir skills/
    python skill_selector.py state.json --skill-dir skills/ --output candidates.json
    python skill_selector.py state.json --skill-dir skills/ --auto
"""

import argparse
import heapq
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Cost ordering for sorting
# ---------------------------------------------------------------------------

COST_ORDER = {"low": 0, "medium": 1, "high": 2}

# ---------------------------------------------------------------------------
# Relation-aware edge weights for goal proximity (Dijkstra).
#
# Causal edges (REQUIRES / LEADS_TO) cost 1 — they represent direct planning
# dependencies and should dominate routing decisions.
# Soft edges (EVIDENCE / IMPLIES) cost 2 — indirect support, less authoritative.
# Similarity edges (SIMILAR) cost 3 — semantic neighbourhood only, not causal.
# COMPLETED and BLOCKED_BY are skipped (None) — historical / negative edges
# that must not influence forward planning.
# Unknown relation types fall back to _DEFAULT_EDGE_WEIGHT.
# ---------------------------------------------------------------------------

EDGE_WEIGHTS: dict[str, int | None] = {
    "REQUIRES":   1,
    "LEADS_TO":   1,
    "EVIDENCE":   2,
    "IMPLIES":    2,
    "SIMILAR":    3,
    "COMPLETED":  None,   # skip — historical record
    "BLOCKED_BY": None,   # skip — negative planning edge
}
_DEFAULT_EDGE_WEIGHT = 2  # fallback for relation types not listed above

# Sentinel used when a skill's postconditions have no path to the goal in the
# current subgraph.  Placing unknown-proximity skills last within each cost
# bucket keeps routing deterministic without penalising them otherwise.
_UNKNOWN_PROXIMITY = sys.maxsize


# ---------------------------------------------------------------------------
# Library API
# ---------------------------------------------------------------------------


def parse_skill_yaml(path: Path) -> dict[str, Any] | None:
    """Parse the YAML frontmatter of a SKILL.md file.

    Returns the parsed YAML dict, or None if parsing fails.
    """
    if yaml is None:
        print("Error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    if not content.startswith("---"):
        return None

    lines = content.split("\n")
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return None

    try:
        data = yaml.safe_load("\n".join(lines[1:end_idx]))
        if isinstance(data, dict):
            data["_source_path"] = str(path)
            return data
        return None
    except yaml.YAMLError:
        return None


def scan_skills(skill_dir: Path) -> list[dict[str, Any]]:
    """Scan a directory for SKILL.md files and parse their YAML headers.

    Returns a list of parsed YAML dicts, one per skill file.
    """
    skills: list[dict[str, Any]] = []
    if not skill_dir.is_dir():
        print(f"Error: '{skill_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    for skill_path in sorted(skill_dir.rglob("SKILL.md")):
        parsed = parse_skill_yaml(skill_path)
        if parsed and "name" in parsed:
            skills.append(parsed)

    return skills


def check_preconditions(
    active_states: set[str],
    preconditions: list[str],
) -> tuple[bool, list[str]]:
    """Check whether preconditions are satisfied given active states.

    Returns (all_satisfied, list_of_unmet_conditions).
    """
    unmet: list[str] = []
    for cond in preconditions:
        if cond.startswith("NOT "):
            state_id = cond[4:].strip()
            if state_id in active_states:
                unmet.append(cond)
        else:
            if cond not in active_states:
                unmet.append(cond)
    return len(unmet) == 0, unmet


def _goal_hop_distances(state: dict[str, Any]) -> dict[str, int]:
    """Dijkstra from the goal entity over current_subgraph edges.

    Edge traversal costs are determined by ``EDGE_WEIGHTS`` keyed on the
    edge ``relation`` field:

    - REQUIRES / LEADS_TO → 1   (causal planning edges)
    - EVIDENCE / IMPLIES   → 2   (soft causal)
    - SIMILAR              → 3   (semantic only)
    - COMPLETED / BLOCKED_BY → skipped (not planning edges)
    - unknown relation     → ``_DEFAULT_EDGE_WEIGHT``

    Returns a mapping of entity_id → weighted distance from goal.
    Entities not reachable from the goal (or only via skipped edges) are
    absent from the returned dict.
    """
    goal = state.get("goal", "")
    if not goal:
        return {}

    subgraph = state.get("current_subgraph", {})
    edges = subgraph.get("edges", [])
    if not edges:
        return {}

    # Build undirected weighted adjacency, skipping blocked relations
    adjacency: dict[str, list[tuple[str, int]]] = {}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        relation = edge.get("relation", "")
        if not src or not tgt:
            continue
        weight = EDGE_WEIGHTS.get(relation, _DEFAULT_EDGE_WEIGHT)
        if weight is None:  # explicitly skipped relation
            continue
        adjacency.setdefault(src, []).append((tgt, weight))
        adjacency.setdefault(tgt, []).append((src, weight))

    # Dijkstra from goal
    distances: dict[str, int] = {goal: 0}
    heap: list[tuple[int, str]] = [(0, goal)]
    while heap:
        dist, node = heapq.heappop(heap)
        if dist > distances.get(node, _UNKNOWN_PROXIMITY):
            continue
        for neighbor, weight in adjacency.get(node, []):
            new_dist = dist + weight
            if new_dist < distances.get(neighbor, _UNKNOWN_PROXIMITY):
                distances[neighbor] = new_dist
                heapq.heappush(heap, (new_dist, neighbor))

    return distances


def select_candidates(
    state: dict[str, Any],
    skills: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select candidate skills whose preconditions are satisfied.

    Returns a list of candidate dicts sorted by:
    1. Cost (low → medium → high)
    2. Goal proximity — min hop distance of postconditions to goal in
       current_subgraph (closer = better). Falls back to a large sentinel
       when the subgraph is empty or a postcondition is unreachable.
    3. Number of postconditions (more = better, descending)
    4. Name (alphabetical tiebreak)

    Each candidate dict includes:
    - name, description, cost, idempotent
    - preconditions, postconditions, related_skills
    - goal_proximity: int (min hops to goal, or sys.maxsize if unknown)
    - satisfied: True
    - source_path: path to the SKILL.md file
    """
    active_states = set(state.get("active_states", []))
    completed_names = {rec.get("skill") for rec in state.get("completed_skills", [])}
    hop_distances = _goal_hop_distances(state)
    candidates: list[dict[str, Any]] = []

    for skill in skills:
        name = skill.get("name", "")
        preconditions = skill.get("preconditions", [])
        if not isinstance(preconditions, list):
            preconditions = []

        satisfied, unmet = check_preconditions(active_states, preconditions)
        if not satisfied:
            continue

        # Skip already completed non-idempotent skills
        idempotent = skill.get("idempotent", False)
        if name in completed_names and not idempotent:
            continue

        postconditions = skill.get("postconditions", [])
        if not isinstance(postconditions, list):
            postconditions = []

        cost = skill.get("cost", "medium")
        if cost not in COST_ORDER:
            cost = "medium"

        # Goal proximity: min hops among postconditions; sentinel when unknown
        goal_proximity = min(
            (hop_distances[p] for p in postconditions if p in hop_distances),
            default=_UNKNOWN_PROXIMITY,
        )

        candidates.append({
            "name": name,
            "description": skill.get("description", ""),
            "cost": cost,
            "idempotent": idempotent,
            "preconditions": preconditions,
            "postconditions": postconditions,
            "related_skills": skill.get("related_skills", []),
            "postcondition_count": len(postconditions),
            "goal_proximity": goal_proximity,
            "satisfied": True,
            "already_completed": name in completed_names,
            "source_path": skill.get("_source_path", ""),
        })

    # Sort: lowest cost → closest to goal → most postconditions → alphabetical
    candidates.sort(
        key=lambda c: (
            COST_ORDER.get(c["cost"], 1),
            c["goal_proximity"],
            -c["postcondition_count"],
            c["name"],
        )
    )

    return candidates


def select_best(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the single best candidate, or None if no candidates."""
    return candidates[0] if candidates else None


def find_plan(
    state: dict[str, Any],
    skills: list[dict[str, Any]],
    max_depth: int = 5,
) -> list[str] | None:
    """BFS over the skill application graph to find the shortest skill sequence to goal.

    Each BFS node is ``(frozenset(active_states), frozenset(completed_non_idempotent))``.
    Applying a skill transitions active_states by adding its postconditions.
    Non-idempotent skills are tracked so they are not re-applied within the same path.

    Returns an ordered list of skill names (the plan), or ``None`` if no path
    is found within ``max_depth`` steps.

    Falls back gracefully: if the goal is already active, returns ``[]``.
    If no skills are provided, returns ``None``.
    """
    goal = state.get("goal", "")
    if not goal:
        return None

    initial_active = frozenset(state.get("active_states", []))
    if goal in initial_active:
        return []

    # Build idempotency index
    idempotency: dict[str, bool] = {
        s.get("name", ""): bool(s.get("idempotent", False)) for s in skills
    }
    initial_completed = frozenset(
        rec.get("skill", "")
        for rec in state.get("completed_skills", [])
        if not idempotency.get(rec.get("skill", ""), False)
    )

    # BFS: each item is (path, active_states, completed_non_idempotent)
    queue: deque[tuple[list[str], frozenset[str], frozenset[str]]] = deque(
        [([], initial_active, initial_completed)]
    )
    visited: set[tuple[frozenset[str], frozenset[str]]] = {
        (initial_active, initial_completed)
    }

    while queue:
        path, active, completed = queue.popleft()

        if len(path) >= max_depth:
            continue

        for skill in skills:
            name = skill.get("name", "")
            if not name:
                continue

            # Skip non-idempotent completed skills
            if name in completed and not idempotency.get(name, False):
                continue

            # Check preconditions
            preconditions = skill.get("preconditions", [])
            if not isinstance(preconditions, list):
                preconditions = []
            satisfied, _ = check_preconditions(active, preconditions)
            if not satisfied:
                continue

            # Simulate applying skill
            postconditions = skill.get("postconditions", [])
            if not isinstance(postconditions, list):
                postconditions = []

            new_active = active | frozenset(postconditions)
            new_completed = completed | (
                frozenset({name}) if not idempotency.get(name, False) else frozenset()
            )
            new_path = path + [name]

            # Goal reached
            if goal in new_active:
                return new_path

            # Avoid revisiting the same world state
            state_key = (new_active, new_completed)
            if state_key not in visited:
                visited.add(state_key)
                queue.append((new_path, new_active, new_completed))

    return None  # No path found within max_depth


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CtxFST Skill Selector — deterministic, rule-based (v1.3)"
    )
    parser.add_argument("state_file", help="World state JSON file")
    parser.add_argument(
        "--skill-dir",
        required=True,
        help="Directory to scan for SKILL.md files",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output candidates JSON file (default: print to stdout)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-select the best candidate and output only that one",
    )

    args = parser.parse_args()

    # Load state
    state_path = Path(args.state_file)
    try:
        with state_path.open(encoding="utf-8") as handle:
            state = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Error loading state: {exc}", file=sys.stderr)
        sys.exit(1)

    # Scan skills
    skills = scan_skills(Path(args.skill_dir))
    if not skills:
        print("⚠️  No SKILL.md files found in skill directory", file=sys.stderr)
        sys.exit(0)

    # Select candidates
    candidates = select_candidates(state, skills)

    if args.auto:
        best = select_best(candidates)
        if best is None:
            print("❌ No eligible skills found")
            sys.exit(1)
        result = {"selected": best, "total_scanned": len(skills), "total_eligible": len(candidates)}
    else:
        result = {
            "candidates": candidates,
            "total_scanned": len(skills),
            "total_eligible": len(candidates),
            "goal": state.get("goal", ""),
            "active_states": state.get("active_states", []),
        }

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        output_path = Path(args.output)
        with output_path.open("w", encoding="utf-8") as handle:
            handle.write(output_json)
        print(f"✅ Wrote {len(candidates)} candidates to {output_path}")
    else:
        print(output_json)

    # Summary to stderr
    print(
        f"\n📊 Scanned: {len(skills)} skills | Eligible: {len(candidates)}",
        file=sys.stderr,
    )
    if candidates:
        best = candidates[0]
        print(
            f"🏆 Best candidate: {best['name']} (cost={best['cost']}, "
            f"postconditions={best['postcondition_count']})",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

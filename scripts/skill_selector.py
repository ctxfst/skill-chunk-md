#!/usr/bin/env python3
"""
Deterministic Skill Selector for CtxFST v2.0 World Model Layer.

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
from dataclasses import dataclass, field
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
# Explanation types
# ---------------------------------------------------------------------------


@dataclass
class PlanStepTrace:
    """Record of one step within an explained plan."""

    skill_name: str
    preconditions_matched: list[str] = field(default_factory=list)
    postconditions_added: list[str] = field(default_factory=list)


@dataclass
class PlanExplanation:
    """Result of find_plan_with_explanation — plan + human-readable reasoning."""

    plan: list[str]                         # ordered skill names
    steps: list[PlanStepTrace]              # per-step trace
    alternatives: list[list[str]]           # other valid plans (up to top_k-1)
    summary: str                            # ready-to-print explanation


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


def _goal_hop_details(state: dict[str, Any]) -> dict[str, tuple[int, str]]:
    """Dijkstra from goal, returning ``{entity: (weighted_distance, edge_relation)}``.

    The relation stored is the one on the shortest-path edge leaving the entity
    toward the goal, so callers can report *why* an entity is considered close.
    Entities unreachable from goal (or only via skipped relations) are absent.
    """
    goal = state.get("goal", "")
    if not goal:
        return {}

    subgraph = state.get("current_subgraph", {})
    edges = subgraph.get("edges", [])
    if not edges:
        return {}

    # Build weighted adjacency with relation labels
    adjacency: dict[str, list[tuple[str, int, str]]] = {}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        relation = edge.get("relation", "")
        if not src or not tgt:
            continue
        weight = EDGE_WEIGHTS.get(relation, _DEFAULT_EDGE_WEIGHT)
        if weight is None:
            continue
        adjacency.setdefault(src, []).append((tgt, weight, relation))
        adjacency.setdefault(tgt, []).append((src, weight, relation))

    # Dijkstra — track which relation was used on the shortest path
    distances: dict[str, int] = {goal: 0}
    via_relation: dict[str, str] = {goal: ""}
    heap: list[tuple[int, str]] = [(0, goal)]
    while heap:
        dist, node = heapq.heappop(heap)
        if dist > distances.get(node, _UNKNOWN_PROXIMITY):
            continue
        for neighbor, weight, relation in adjacency.get(node, []):
            new_dist = dist + weight
            if new_dist < distances.get(neighbor, _UNKNOWN_PROXIMITY):
                distances[neighbor] = new_dist
                via_relation[neighbor] = relation
                heapq.heappush(heap, (new_dist, neighbor))

    return {entity: (dist, via_relation.get(entity, "")) for entity, dist in distances.items()}


def explain_selection(
    candidates: list[dict[str, Any]],
    state: dict[str, Any],
) -> str:
    """Return a human-readable explanation of why the top candidate was selected.

    Compares the winner against each rejected candidate using cost,
    goal_proximity, and the edge relation that contributed to proximity.
    """
    if not candidates:
        return "No eligible candidates."

    winner = candidates[0]
    hop_details = _goal_hop_details(state)

    def _proximity_desc(skill: dict[str, Any]) -> str:
        parts = []
        for pc in skill.get("postconditions", []):
            if pc in hop_details:
                dist, relation = hop_details[pc]
                label = f"via {relation}" if relation else "direct"
                parts.append(f"{pc} → goal in {dist} ({label})")
            else:
                parts.append(f"{pc} → goal unknown")
        return "; ".join(parts) if parts else "no subgraph proximity"

    lines = [
        f"Selected:  {winner['name']}",
        f"  cost={winner['cost']}  proximity={winner['goal_proximity']}  "
        f"postconditions={winner['postcondition_count']}",
        f"  {_proximity_desc(winner)}",
    ]

    if len(candidates) > 1:
        lines.append("Rejected:")
        for loser in candidates[1:]:
            reasons: list[str] = []
            if COST_ORDER.get(loser["cost"], 1) > COST_ORDER.get(winner["cost"], 1):
                reasons.append(f"cost {loser['cost']} > {winner['cost']}")
            if loser["goal_proximity"] > winner["goal_proximity"]:
                reasons.append(
                    f"proximity {loser['goal_proximity']} > {winner['goal_proximity']} "
                    f"({_proximity_desc(loser)})"
                )
            if loser["postcondition_count"] < winner["postcondition_count"]:
                reasons.append(
                    f"fewer postconditions ({loser['postcondition_count']} < {winner['postcondition_count']})"
                )
            if not reasons:
                reasons.append("same score, lower alphabetical rank")
            lines.append(f"  {loser['name']}: {'; '.join(reasons)}")

    return "\n".join(lines)


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


def _build_step_traces(
    plan: list[str],
    state: dict[str, Any],
    skills_by_name: dict[str, dict[str, Any]],
) -> list[PlanStepTrace]:
    """Simulate running a plan and record which preconditions were satisfied
    and which postconditions were newly added at each step."""
    active: set[str] = set(state.get("active_states", []))
    traces: list[PlanStepTrace] = []
    for name in plan:
        skill = skills_by_name.get(name, {})
        preconditions = skill.get("preconditions", []) or []
        postconditions = skill.get("postconditions", []) or []

        matched = [
            p for p in preconditions
            if (p.startswith("NOT ") and p[4:].strip() not in active)
            or (not p.startswith("NOT ") and p in active)
        ]
        added = [p for p in postconditions if p not in active]
        active.update(postconditions)

        traces.append(PlanStepTrace(
            skill_name=name,
            preconditions_matched=matched,
            postconditions_added=added,
        ))
    return traces


def _find_alternative_plans(
    state: dict[str, Any],
    skills: list[dict[str, Any]],
    best_plan: list[str],
    max_depth: int,
    top_k: int,
) -> list[list[str]]:
    """Find up to top_k-1 alternative plans by excluding one skill at a time
    from the best plan.  Each excluded skill forces the planner to find a
    different route, producing genuinely distinct alternatives."""
    alternatives: list[list[str]] = []
    for skip_name in best_plan:
        filtered = [s for s in skills if s.get("name") != skip_name]
        alt = find_plan(state, filtered, max_depth)
        if alt and alt != best_plan and alt not in alternatives:
            alternatives.append(alt)
        if len(alternatives) >= top_k - 1:
            break
    return alternatives


def _plan_comparison_reason(
    best: list[str],
    alt: list[str],
    skills_by_name: dict[str, dict[str, Any]],
) -> str:
    """One-line reason why best is preferred over alt."""
    if len(alt) > len(best):
        return f"{len(alt)} steps vs {len(best)} — longer"
    if len(alt) < len(best):
        return f"{len(alt)} steps vs {len(best)} — shorter but uses unavailable skills"
    best_cost = sum(COST_ORDER.get(skills_by_name.get(n, {}).get("cost", "medium"), 1) for n in best)
    alt_cost  = sum(COST_ORDER.get(skills_by_name.get(n, {}).get("cost", "medium"), 1) for n in alt)
    if alt_cost > best_cost:
        return f"same length, higher total cost (score {alt_cost} vs {best_cost})"
    if alt_cost < best_cost:
        return f"same length, lower total cost (score {alt_cost} vs {best_cost})"
    return "same length and cost, lower priority"


def find_plan_with_explanation(
    state: dict[str, Any],
    skills: list[dict[str, Any]],
    max_depth: int = 5,
    top_k: int = 3,
) -> PlanExplanation:
    """Find the best plan and explain why it was chosen over alternatives.

    Returns a ``PlanExplanation`` with:
    - ``plan``         — ordered skill names
    - ``steps``        — per-step trace of preconditions satisfied and
                         postconditions newly added
    - ``alternatives`` — up to ``top_k - 1`` other valid plans found by
                         excluding skills from the best plan one at a time
    - ``summary``      — ready-to-print explanation string
    """
    skills_by_name: dict[str, dict[str, Any]] = {
        s.get("name", ""): s for s in skills if s.get("name")
    }
    goal = state.get("goal", "")

    plan = find_plan(state, skills, max_depth)

    if plan is None:
        return PlanExplanation(
            plan=[], steps=[], alternatives=[],
            summary=f"No plan found within {max_depth} steps.",
        )
    if not plan:
        return PlanExplanation(
            plan=[], steps=[], alternatives=[],
            summary="Goal already satisfied — no steps needed.",
        )

    steps = _build_step_traces(plan, state, skills_by_name)
    alternatives = _find_alternative_plans(state, skills, plan, max_depth, top_k)

    # Build summary
    lines = [
        f"Best plan ({len(plan)} step{'s' if len(plan) != 1 else ''}): "
        f"{' → '.join(plan)}",
    ]
    for i, step in enumerate(steps, 1):
        lines.append(f"  Step {i}: {step.skill_name}")
        for p in step.preconditions_matched:
            lines.append(f"    pre  ✓  {p}")
        for p in step.postconditions_added:
            marker = " ← GOAL" if p == goal else ""
            lines.append(f"    post +  {p}{marker}")

    if alternatives:
        lines.append(f"\nAlternatives ({len(alternatives)}):")
        for alt in alternatives:
            reason = _plan_comparison_reason(plan, alt, skills_by_name)
            lines.append(f"  {' → '.join(alt)}  [{reason}]")
    else:
        lines.append("\nNo alternatives found within depth limit.")

    return PlanExplanation(
        plan=plan,
        steps=steps,
        alternatives=alternatives,
        summary="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CtxFST Skill Selector — deterministic, rule-based (v2.0)"
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

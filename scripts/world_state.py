#!/usr/bin/env python3
"""
World State Manager for CtxFST v1.3 World Model Layer.

Provides both a reusable Python API and a CLI for managing runtime session
state in agent loops. The state tracks active conditions, completed skills,
and a goal-relevant subgraph.

Library API:
    from world_state import init_state, load_state, save_state
    from world_state import add_state, remove_state, complete_skill
    from world_state import check_preconditions, show_state

CLI Usage:
    python world_state.py init --goal "entity:learn-kubernetes-path" --output state.json
    python world_state.py add-state state.json "state:has-raw-resume"
    python world_state.py remove-state state.json "state:has-raw-resume"
    python world_state.py complete-skill state.json --skill analyze-resume --result success --summary "Parsed 3 skills"
    python world_state.py check-preconditions state.json --skill-yaml path/to/SKILL.md
    python world_state.py show state.json
    python world_state.py update-subgraph state.json --graph entity-graph.json --depth 2
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Library API
# ---------------------------------------------------------------------------


def init_state(goal: str, session_id: str | None = None) -> dict[str, Any]:
    """Create a fresh world state dictionary."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "session_id": session_id or str(uuid.uuid4()),
        "goal": goal,
        "active_states": [],
        "completed_skills": [],
        "current_subgraph": {"nodes": [], "edges": []},
        "created_at": now,
        "updated_at": now,
    }


def load_state(path: Path) -> dict[str, Any]:
    """Load a world state from a JSON file."""
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
        print("Error: world state root must be a JSON object", file=sys.stderr)
        sys.exit(1)

    return data


def save_state(state: dict[str, Any], path: Path) -> None:
    """Save a world state to a JSON file, updating the timestamp."""
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)


def add_state(state: dict[str, Any], state_id: str) -> bool:
    """Add an active state. Returns True if added, False if already present."""
    active = state.setdefault("active_states", [])
    if state_id in active:
        return False
    active.append(state_id)
    return True


def remove_state(state: dict[str, Any], state_id: str) -> bool:
    """Remove an active state. Returns True if removed, False if not found."""
    active = state.get("active_states", [])
    if state_id not in active:
        return False
    active.remove(state_id)
    return True


def complete_skill(
    state: dict[str, Any],
    skill_name: str,
    result: str = "success",
    summary: str = "",
) -> dict[str, Any]:
    """Record a completed skill execution. Returns the record."""
    record = {
        "skill": skill_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "summary": summary,
    }
    state.setdefault("completed_skills", []).append(record)
    return record


def parse_skill_yaml(path: Path) -> dict[str, Any] | None:
    """Parse the YAML frontmatter of a SKILL.md file."""
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
        return yaml.safe_load("\n".join(lines[1:end_idx]))
    except yaml.YAMLError:
        return None


def check_preconditions(
    state: dict[str, Any],
    preconditions: list[str],
) -> tuple[bool, list[str]]:
    """Check whether all preconditions are satisfied.

    Returns (all_satisfied, list_of_unmet_conditions).

    Preconditions:
    - ``"state:foo"`` → ``state:foo`` must be in active_states
    - ``"NOT state:foo"`` → ``state:foo`` must NOT be in active_states
    """
    active = set(state.get("active_states", []))
    unmet: list[str] = []

    for cond in preconditions:
        if cond.startswith("NOT "):
            state_id = cond[4:].strip()
            if state_id in active:
                unmet.append(cond)
        else:
            if cond not in active:
                unmet.append(cond)

    return len(unmet) == 0, unmet


def update_subgraph(
    state: dict[str, Any],
    graph: dict[str, Any],
    depth: int = 2,
) -> None:
    """Extract a goal-relevant subgraph from an entity graph.

    Performs a BFS from the goal entity up to ``depth`` hops.
    """
    goal = state.get("goal", "")
    nodes_map: dict[str, Any] = {}
    edges_list = graph.get("edges", [])

    # Build adjacency
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in edges_list:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        adjacency.setdefault(src, []).append(edge)
        adjacency.setdefault(tgt, []).append(edge)

    # BFS
    visited: set[str] = set()
    frontier = {goal}
    subgraph_edges: list[dict[str, Any]] = []

    for _ in range(depth):
        next_frontier: set[str] = set()
        for node_id in frontier:
            if node_id in visited:
                continue
            visited.add(node_id)
            for edge in adjacency.get(node_id, []):
                subgraph_edges.append(edge)
                other = edge["target"] if edge["source"] == node_id else edge["source"]
                if other not in visited:
                    next_frontier.add(other)
        frontier = next_frontier

    visited.update(frontier)

    state["current_subgraph"] = {
        "nodes": sorted(visited),
        "edges": subgraph_edges,
    }


def show_state(state: dict[str, Any]) -> str:
    """Format a human-readable summary of the world state."""
    lines = [
        f"Session:  {state.get('session_id', 'N/A')}",
        f"Goal:     {state.get('goal', 'N/A')}",
        f"Created:  {state.get('created_at', 'N/A')}",
        f"Updated:  {state.get('updated_at', 'N/A')}",
        "",
        f"Active states ({len(state.get('active_states', []))}):",
    ]
    for s in state.get("active_states", []):
        lines.append(f"  ✓ {s}")
    if not state.get("active_states"):
        lines.append("  (none)")

    lines.append("")
    completed = state.get("completed_skills", [])
    lines.append(f"Completed skills ({len(completed)}):")
    for rec in completed:
        icon = "✅" if rec.get("result") == "success" else "❌" if rec.get("result") == "failed" else "⚠️"
        lines.append(f"  {icon} {rec.get('skill', '?')} [{rec.get('result', '?')}] {rec.get('summary', '')}")
    if not completed:
        lines.append("  (none)")

    subgraph = state.get("current_subgraph", {})
    sg_nodes = subgraph.get("nodes", [])
    sg_edges = subgraph.get("edges", [])
    lines.append("")
    lines.append(f"Subgraph: {len(sg_nodes)} nodes, {len(sg_edges)} edges")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cli_init(args: argparse.Namespace) -> None:
    state = init_state(args.goal)
    output = Path(args.output)
    save_state(state, output)
    print(f"✅ Initialized world state: {output}")
    print(f"   Session: {state['session_id']}")
    print(f"   Goal: {state['goal']}")


def cli_add_state(args: argparse.Namespace) -> None:
    path = Path(args.state_file)
    state = load_state(path)
    added = add_state(state, args.state_id)
    save_state(state, path)
    if added:
        print(f"✅ Added state: {args.state_id}")
    else:
        print(f"⚠️  State already active: {args.state_id}")


def cli_remove_state(args: argparse.Namespace) -> None:
    path = Path(args.state_file)
    state = load_state(path)
    removed = remove_state(state, args.state_id)
    save_state(state, path)
    if removed:
        print(f"✅ Removed state: {args.state_id}")
    else:
        print(f"⚠️  State not found: {args.state_id}")


def cli_complete_skill(args: argparse.Namespace) -> None:
    path = Path(args.state_file)
    state = load_state(path)
    record = complete_skill(state, args.skill, args.result, args.summary)
    save_state(state, path)
    print(f"✅ Recorded skill completion: {record['skill']} [{record['result']}]")


def cli_check_preconditions(args: argparse.Namespace) -> None:
    path = Path(args.state_file)
    state = load_state(path)
    skill_meta = parse_skill_yaml(Path(args.skill_yaml))
    if skill_meta is None:
        print(f"Error: could not parse YAML from '{args.skill_yaml}'", file=sys.stderr)
        sys.exit(1)

    preconditions = skill_meta.get("preconditions", [])
    if not preconditions:
        print(f"✅ Skill '{skill_meta.get('name', '?')}' has no preconditions — always eligible")
        return

    satisfied, unmet = check_preconditions(state, preconditions)
    if satisfied:
        print(f"✅ All preconditions met for '{skill_meta.get('name', '?')}'")
    else:
        print(f"❌ Unmet preconditions for '{skill_meta.get('name', '?')}':")
        for cond in unmet:
            print(f"   ✗ {cond}")
        sys.exit(1)


def cli_show(args: argparse.Namespace) -> None:
    path = Path(args.state_file)
    state = load_state(path)
    print(show_state(state))


def cli_update_subgraph(args: argparse.Namespace) -> None:
    state_path = Path(args.state_file)
    graph_path = Path(args.graph)
    state = load_state(state_path)

    try:
        with graph_path.open(encoding="utf-8") as handle:
            graph = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Error loading graph: {exc}", file=sys.stderr)
        sys.exit(1)

    update_subgraph(state, graph, args.depth)
    save_state(state, state_path)
    sg = state["current_subgraph"]
    print(f"✅ Updated subgraph: {len(sg['nodes'])} nodes, {len(sg['edges'])} edges")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CtxFST World State Manager (v1.3)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Create a new world state")
    p_init.add_argument("--goal", required=True, help="Goal entity ID")
    p_init.add_argument("--output", "-o", default="world-state.json", help="Output file")

    # add-state
    p_add = subparsers.add_parser("add-state", help="Add an active state")
    p_add.add_argument("state_file", help="World state JSON file")
    p_add.add_argument("state_id", help="State entity ID to add")

    # remove-state
    p_rm = subparsers.add_parser("remove-state", help="Remove an active state")
    p_rm.add_argument("state_file", help="World state JSON file")
    p_rm.add_argument("state_id", help="State entity ID to remove")

    # complete-skill
    p_cs = subparsers.add_parser("complete-skill", help="Record a completed skill")
    p_cs.add_argument("state_file", help="World state JSON file")
    p_cs.add_argument("--skill", required=True, help="Skill name")
    p_cs.add_argument("--result", choices=["success", "failed", "partial"], default="success")
    p_cs.add_argument("--summary", default="", help="Brief result summary")

    # check-preconditions
    p_cp = subparsers.add_parser("check-preconditions", help="Check skill preconditions")
    p_cp.add_argument("state_file", help="World state JSON file")
    p_cp.add_argument("--skill-yaml", required=True, help="Path to SKILL.md file")

    # show
    p_show = subparsers.add_parser("show", help="Display current state")
    p_show.add_argument("state_file", help="World state JSON file")

    # update-subgraph
    p_sg = subparsers.add_parser("update-subgraph", help="Extract goal-relevant subgraph")
    p_sg.add_argument("state_file", help="World state JSON file")
    p_sg.add_argument("--graph", required=True, help="Entity graph JSON file")
    p_sg.add_argument("--depth", type=int, default=2, help="BFS depth (default: 2)")

    args = parser.parse_args()

    dispatch = {
        "init": cli_init,
        "add-state": cli_add_state,
        "remove-state": cli_remove_state,
        "complete-skill": cli_complete_skill,
        "check-preconditions": cli_check_preconditions,
        "show": cli_show,
        "update-subgraph": cli_update_subgraph,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

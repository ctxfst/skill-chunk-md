#!/usr/bin/env python3
"""
Agent Loop Runtime for CtxFST v1.3 World Model Layer.

Orchestrates the closed loop: read world state → select skill → execute →
write postconditions back → repeat until the goal is reached.

Library API:
    from agent_loop import run_loop, DryRunExecutor, CallbackExecutor
    from agent_loop import ExecutionResult, LoopResult

CLI Usage:
    python agent_loop.py state.json --skill-dir skills/ --dry-run
    python agent_loop.py state.json --skill-dir skills/ --interactive
    python agent_loop.py state.json --skill-dir skills/ --graph entity-graph.json
    python agent_loop.py state.json --skill-dir skills/ --max-iter 10
    python agent_loop.py state.json --skill-dir skills/ -o result.json
"""

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from world_state import (
    add_state,
    complete_skill,
    load_state,
    remove_state,
    save_state,
    show_state,
)
from skill_selector import find_plan, scan_skills, select_best, select_candidates


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    """Result of executing a single skill."""

    result: str  # "success" | "failed" | "partial"
    summary: str = ""
    new_states: list[str] = field(default_factory=list)
    remove_states: list[str] = field(default_factory=list)


@dataclass
class StepRecord:
    """Record of one iteration of the agent loop."""

    iteration: int
    skill_name: str
    skill_cost: str
    execution_result: str
    summary: str
    states_added: list[str] = field(default_factory=list)
    states_removed: list[str] = field(default_factory=list)


@dataclass
class LoopResult:
    """Result of the entire agent loop run."""

    iterations: int
    goal_reached: bool
    terminated_reason: str  # goal_reached | no_candidates | max_iterations | execution_failure
    final_state: dict[str, Any] = field(default_factory=dict)
    history: list[StepRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Executor Protocol & Implementations
# ---------------------------------------------------------------------------


class Executor(Protocol):
    """Protocol for skill executors."""

    def execute(self, skill: dict[str, Any], state: dict[str, Any]) -> ExecutionResult: ...


class DryRunExecutor:
    """Simulate execution: always succeeds, applies postconditions automatically."""

    def execute(self, skill: dict[str, Any], state: dict[str, Any]) -> ExecutionResult:
        postconditions = skill.get("postconditions", [])
        return ExecutionResult(
            result="success",
            summary=f"[dry-run] Would execute '{skill.get('name', '?')}'",
            new_states=list(postconditions),
        )


class InteractiveExecutor:
    """Pause at each step and ask the user to confirm, skip, or abort."""

    def execute(self, skill: dict[str, Any], state: dict[str, Any]) -> ExecutionResult:
        name = skill.get("name", "?")
        postconditions = skill.get("postconditions", [])
        print(f"\n--- Skill: {name} ---", file=sys.stderr)
        print(f"  Description: {skill.get('description', '')}", file=sys.stderr)
        print(f"  Cost: {skill.get('cost', '?')}", file=sys.stderr)
        print(f"  Postconditions: {postconditions}", file=sys.stderr)
        while True:
            choice = input("  Execute? [y]es / [s]kip / [a]bort: ").strip().lower()
            if choice in ("y", "yes"):
                return ExecutionResult(
                    result="success",
                    summary=f"User confirmed '{name}'",
                    new_states=list(postconditions),
                )
            if choice in ("s", "skip"):
                return ExecutionResult(result="partial", summary=f"User skipped '{name}'")
            if choice in ("a", "abort"):
                return ExecutionResult(result="failed", summary="User aborted")


class CallbackExecutor:
    """Wrap a user-provided callable as an Executor."""

    def __init__(self, fn: Any) -> None:
        self._fn = fn

    def execute(self, skill: dict[str, Any], state: dict[str, Any]) -> ExecutionResult:
        return self._fn(skill, state)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log(iteration: int, message: str) -> None:
    print(f"[Step {iteration}] {message}", file=sys.stderr)


def _append_completed_edges(
    graph: dict[str, Any],
    skill: dict[str, Any],
    exec_result: ExecutionResult,
) -> int:
    """Append COMPLETED edges to the graph. Returns the number of edges added."""
    edges = graph.setdefault("edges", [])
    now = datetime.now(timezone.utc).isoformat()
    name = skill.get("name", "?")
    added = 0
    for target in exec_result.new_states:
        edges.append({
            "source": name,
            "target": target,
            "relation": "COMPLETED",
            "score": 1.0,
            "shared_chunk_count": 0,
            "properties": {
                "timestamp": now,
                "status": "active" if exec_result.result == "success" else exec_result.result,
                "result_summary": exec_result.summary,
            },
        })
        added += 1
    return added


def format_loop_result(result: LoopResult) -> str:
    """Format a human-readable summary of the loop result."""
    icon = "✅" if result.goal_reached else "❌"
    lines = [
        f"{icon} Loop finished: {result.terminated_reason}",
        f"   Iterations: {result.iterations}",
        f"   Goal reached: {result.goal_reached}",
        "",
    ]
    for step in result.history:
        s_icon = "✅" if step.execution_result == "success" else "⚠️" if step.execution_result == "partial" else "❌"
        lines.append(f"  {s_icon} Step {step.iteration}: {step.skill_name} [{step.execution_result}]")
        if step.states_added:
            for s in step.states_added:
                lines.append(f"       + {s}")
        if step.states_removed:
            for s in step.states_removed:
                lines.append(f"       - {s}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core Loop
# ---------------------------------------------------------------------------


def run_loop(
    state: dict[str, Any],
    skills: list[dict[str, Any]],
    executor: Executor,
    graph: dict[str, Any] | None = None,
    max_iterations: int = 20,
    stop_on_failure: bool = True,
    lookahead: int = 0,
) -> LoopResult:
    """Run the agent loop until the goal is reached or termination.

    When ``lookahead > 0`` the planner runs BFS over the skill application
    graph (``find_plan``) at each iteration to find the shortest path to the
    goal within ``lookahead`` steps, then executes only the first step.
    This turns the loop from greedy single-step into a replanning lookahead
    planner.  If no plan is found, the loop falls back to greedy selection.
    When ``lookahead == 0`` (default) the loop uses the original greedy mode.
    """
    goal = state.get("goal", "")
    history: list[StepRecord] = []
    # Build name→dict index once for O(1) lookup during lookahead execution
    skills_by_name: dict[str, dict[str, Any]] = {
        s.get("name", ""): s for s in skills if s.get("name")
    }

    for iteration in range(1, max_iterations + 1):
        # Check goal
        if goal and goal in state.get("active_states", []):
            return LoopResult(
                iterations=iteration - 1,
                goal_reached=True,
                terminated_reason="goal_reached",
                final_state=state,
                history=history,
            )

        # Select next skill — lookahead or greedy
        skill: dict[str, Any] | None = None

        if lookahead > 0:
            plan = find_plan(state, skills, max_depth=lookahead)
            if plan:
                _log(iteration, f"Plan ({len(plan)} step{'s' if len(plan) != 1 else ''}): "
                                 f"{' → '.join(plan)}")
                skill = skills_by_name.get(plan[0])

        if skill is None:
            # Greedy fallback (also used when lookahead==0)
            candidates = select_candidates(state, skills)
            if not candidates:
                return LoopResult(
                    iterations=iteration - 1,
                    goal_reached=False,
                    terminated_reason="no_candidates",
                    final_state=state,
                    history=history,
                )
            skill = select_best(candidates)

        assert skill is not None
        _log(iteration, f"Selecting: {skill['name']} (cost={skill.get('cost', '?')}, "
                         f"postconditions={len(skill.get('postconditions', []))})")

        # Execute
        try:
            exec_result = executor.execute(skill, state)
        except Exception as exc:
            exec_result = ExecutionResult(result="failed", summary=str(exc))

        # Apply state changes
        states_added: list[str] = []
        states_removed: list[str] = []

        if exec_result.result in ("success", "partial"):
            new_states = exec_result.new_states
            if not new_states and exec_result.result == "success":
                new_states = list(skill.get("postconditions", []))

            for s in new_states:
                if add_state(state, s):
                    states_added.append(s)

            for s in exec_result.remove_states:
                if remove_state(state, s):
                    states_removed.append(s)

            complete_skill(state, skill["name"], exec_result.result, exec_result.summary)

            if graph is not None and new_states:
                _append_completed_edges(graph, skill, exec_result)

        else:
            complete_skill(state, skill["name"], "failed", exec_result.summary)

        # Record
        step = StepRecord(
            iteration=iteration,
            skill_name=skill["name"],
            skill_cost=skill["cost"],
            execution_result=exec_result.result,
            summary=exec_result.summary,
            states_added=states_added,
            states_removed=states_removed,
        )
        history.append(step)

        result_icon = "✅" if exec_result.result == "success" else "⚠️" if exec_result.result == "partial" else "❌"
        _log(iteration, f"Result: {result_icon} {exec_result.result} — {exec_result.summary}")
        for s in states_added:
            _log(iteration, f"  + {s}")

        # Stop on failure
        if exec_result.result == "failed" and stop_on_failure:
            return LoopResult(
                iterations=iteration,
                goal_reached=False,
                terminated_reason="execution_failure",
                final_state=state,
                history=history,
            )

    # Max iterations
    return LoopResult(
        iterations=max_iterations,
        goal_reached=goal in state.get("active_states", []),
        terminated_reason="goal_reached" if goal in state.get("active_states", []) else "max_iterations",
        final_state=state,
        history=history,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CtxFST Agent Loop Runtime (v1.3)"
    )
    parser.add_argument("state_file", help="World state JSON file")
    parser.add_argument("--skill-dir", required=True, help="Directory to scan for SKILL.md files")
    parser.add_argument("--graph", default=None, help="Entity graph JSON (enables COMPLETED edge writeback)")
    parser.add_argument("--max-iter", type=int, default=20, help="Maximum iterations (default: 20)")
    parser.add_argument("--continue-on-failure", action="store_true", help="Continue after execution failures")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution (default)")
    parser.add_argument("--interactive", action="store_true", help="Pause at each step for user confirmation")
    parser.add_argument("--lookahead", type=int, default=0,
                        help="Enable multi-step planning: BFS up to N steps ahead (0 = greedy, default)")
    parser.add_argument("--output", "-o", default=None, help="Output loop result JSON file")

    args = parser.parse_args()

    # Load state
    state_path = Path(args.state_file)
    state = load_state(state_path)

    # Scan skills
    skills = scan_skills(Path(args.skill_dir))
    if not skills:
        print("⚠️  No SKILL.md files found", file=sys.stderr)
        sys.exit(0)

    # Load graph
    graph: dict[str, Any] | None = None
    if args.graph:
        graph_path = Path(args.graph)
        try:
            with graph_path.open(encoding="utf-8") as handle:
                graph = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"Error loading graph: {exc}", file=sys.stderr)
            sys.exit(1)

    # Select executor
    executor: Executor
    if args.interactive:
        executor = InteractiveExecutor()
    else:
        executor = DryRunExecutor()

    # Run
    stop_on_failure = not args.continue_on_failure
    result = run_loop(state, skills, executor, graph, args.max_iter, stop_on_failure,
                      lookahead=args.lookahead)

    # Save state
    save_state(state, state_path)

    # Save graph
    if graph is not None and args.graph:
        graph_path = Path(args.graph)
        with graph_path.open("w", encoding="utf-8") as handle:
            json.dump(graph, handle, indent=2, ensure_ascii=False)
        print(f"📊 Updated graph: {graph_path}", file=sys.stderr)

    # Output
    print(format_loop_result(result))

    if args.output:
        output_path = Path(args.output)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(result), handle, indent=2, ensure_ascii=False, default=str)
        print(f"📄 Wrote result: {output_path}", file=sys.stderr)

    # Final state
    print("\n" + show_state(state))

    sys.exit(0 if result.goal_reached else 1)


if __name__ == "__main__":
    main()

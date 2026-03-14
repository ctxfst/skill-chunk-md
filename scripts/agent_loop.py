#!/usr/bin/env python3
"""
Agent Loop Runtime for CtxFST v2.0 World Model Layer.

Orchestrates the closed loop: read world state → select skill → execute →
write postconditions back → repeat until the goal is reached.

Library API:
    from agent_loop import run_loop, DryRunExecutor, CallbackExecutor
    from agent_loop import ExecutionResult, LoopResult, critique_plan

CLI Usage:
    python agent_loop.py state.json --skill-dir skills/ --dry-run
    python agent_loop.py state.json --skill-dir skills/ --interactive
    python agent_loop.py state.json --skill-dir skills/ --graph entity-graph.json
    python agent_loop.py state.json --skill-dir skills/ --max-iter 10
    python agent_loop.py state.json --skill-dir skills/ --lookahead 5 --explain
    python agent_loop.py state.json --skill-dir skills/ --lookahead 5 --critique
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
from skill_selector import (
    PlanExplanation,
    check_preconditions,
    explain_selection,
    find_plan,
    find_plan_with_explanation,
    scan_skills,
    select_best,
    select_candidates,
)


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


_CRITIQUE_HELP = (
    "Commands: [a]ccept  [s]kip <skill>  [f]orce <skill>  [r]eset  [q]uit"
)


def critique_plan(
    explanation: PlanExplanation,
    state: dict[str, Any],
    skills: list[dict[str, Any]],
    max_depth: int,
) -> list[str] | None:
    """Present a plan for human critique in an interactive loop.

    The human may accept, skip a skill, force a specific first step, reset
    all constraints, or quit (abort the loop entirely).

    Returns the accepted plan (list of skill names) or ``None`` if the user
    aborted with ``q``.

    Commands
    --------
    a              Accept — proceed with current plan
    s <skill>      Skip — exclude skill and replan
    f <skill>      Force — require skill as the next step (preconditions checked)
    r              Reset — clear all constraints and replan from scratch
    q              Quit — abort the loop
    """
    skills_by_name: dict[str, dict[str, Any]] = {
        s.get("name", ""): s for s in skills if s.get("name")
    }
    skipped: set[str] = set()
    current = explanation

    while True:
        # Display plan
        print(file=sys.stderr)
        for line in current.summary.splitlines():
            print(f"  {line}", file=sys.stderr)
        print(file=sys.stderr)

        if not current.plan:
            print("  ⚠️  No valid plan under current constraints.", file=sys.stderr)

        print(_CRITIQUE_HELP, file=sys.stderr)

        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n🛑 Planning aborted.", file=sys.stderr)
            return None

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""

        # --- accept ---
        if cmd in ("a", "accept"):
            if not current.plan:
                print("❌ Nothing to accept — replan first or [r]eset.", file=sys.stderr)
                continue
            print(f"✅ Accepted: {' → '.join(current.plan)}", file=sys.stderr)
            return current.plan

        # --- quit ---
        elif cmd in ("q", "quit"):
            print("🛑 Planning aborted.", file=sys.stderr)
            return None

        # --- reset ---
        elif cmd in ("r", "reset"):
            skipped = set()
            current = find_plan_with_explanation(state, skills, max_depth)
            print("🔄 Constraints reset.", file=sys.stderr)

        # --- skip ---
        elif cmd in ("s", "skip"):
            if not arg:
                print("  Usage: s <skill-name>", file=sys.stderr)
                continue
            if arg not in skills_by_name:
                print(f"  ❌ Unknown skill: '{arg}'", file=sys.stderr)
                continue
            skipped.add(arg)
            filtered = [sk for sk in skills if sk.get("name") not in skipped]
            current = find_plan_with_explanation(state, filtered, max_depth)
            if not current.plan:
                print(f"  ⚠️  No plan without '{arg}'. Use [r]eset to undo.", file=sys.stderr)
            else:
                print(f"  ♻️  Replanning without '{arg}'...", file=sys.stderr)

        # --- force ---
        elif cmd in ("f", "force"):
            if not arg:
                print("  Usage: f <skill-name>", file=sys.stderr)
                continue
            skill = skills_by_name.get(arg)
            if skill is None:
                print(f"  ❌ Unknown skill: '{arg}'", file=sys.stderr)
                continue
            active = set(state.get("active_states", []))
            satisfied, unmet = check_preconditions(active, skill.get("preconditions", []))
            if not satisfied:
                print(f"  ❌ Cannot force '{arg}' — unmet preconditions: {unmet}", file=sys.stderr)
                continue

            # Simulate applying forced skill, then find tail plan for remainder
            sim_active = active | set(skill.get("postconditions", []))
            sim_state = {**state, "active_states": list(sim_active)}
            available = [sk for sk in skills if sk.get("name") not in skipped and sk.get("name") != arg]
            tail = find_plan_with_explanation(sim_state, available, max(1, max_depth - 1))

            forced_plan = [arg] + (tail.plan or [])
            goal = state.get("goal", "")
            lines = [
                f"Forced plan ({len(forced_plan)} step{'s' if len(forced_plan) != 1 else ''}): "
                f"{' → '.join(forced_plan)}",
                f"  Step 1: {arg} [forced by user]",
            ]
            for i, name in enumerate(tail.plan or [], 2):
                lines.append(f"  Step {i}: {name}")
            if not tail.plan:
                lines.append("  ⚠️  No continuation found after forced step.")
            if tail.alternatives:
                lines.append(f"\nAlternatives ({len(tail.alternatives)}):")
                for alt in tail.alternatives:
                    lines.append(f"  {arg} → {' → '.join(alt)}")
            current = PlanExplanation(
                plan=forced_plan, steps=[], alternatives=[], summary="\n".join(lines)
            )
            print(f"  🔒 Forcing '{arg}' as first step...", file=sys.stderr)

        else:
            print(f"  Unknown command. {_CRITIQUE_HELP}", file=sys.stderr)


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
    explain: bool = False,
    critique: bool = False,
) -> LoopResult:
    """Run the agent loop until the goal is reached or termination.

    When ``lookahead > 0`` the planner runs BFS over the skill application
    graph (``find_plan``) at each iteration to find the shortest path to the
    goal within ``lookahead`` steps, then executes only the first step.

    When ``critique=True`` (requires ``lookahead > 0``), the planner presents
    its plan to the user before each execution step for interactive feedback
    (accept / skip / force / reset / quit). Quitting sets
    ``terminated_reason="user_aborted"``.  ``critique`` implies ``explain``.

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
            if critique:
                # Interactive: show plan + collect human feedback before executing
                explanation = find_plan_with_explanation(state, skills, max_depth=lookahead)
                accepted = critique_plan(explanation, state, skills, lookahead)
                if accepted is None:
                    return LoopResult(
                        iterations=iteration - 1,
                        goal_reached=False,
                        terminated_reason="user_aborted",
                        final_state=state,
                        history=history,
                    )
                plan = accepted or None
            elif explain:
                explanation = find_plan_with_explanation(state, skills, max_depth=lookahead)
                for line in explanation.summary.splitlines():
                    _log(iteration, line)
                plan = explanation.plan or None
            else:
                plan = find_plan(state, skills, max_depth=lookahead)
                if plan:
                    _log(iteration, f"Plan ({len(plan)} step{'s' if len(plan) != 1 else ''}): "
                                     f"{' → '.join(plan)}")

            if plan:
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
            if explain:
                _log(iteration, explain_selection(candidates, state))
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
        description="CtxFST Agent Loop Runtime (v2.0)"
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
    parser.add_argument("--explain", action="store_true",
                        help="Log relation-specific explanations for each selection and plan")
    parser.add_argument("--critique", action="store_true",
                        help="Pause before each execution step for interactive plan critique "
                             "(implies --lookahead 5 if --lookahead not set)")
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

    # --critique implies lookahead (default 5 if unset)
    effective_lookahead = args.lookahead or (5 if args.critique else 0)

    # Run
    stop_on_failure = not args.continue_on_failure
    result = run_loop(state, skills, executor, graph, args.max_iter, stop_on_failure,
                      lookahead=effective_lookahead, explain=args.explain,
                      critique=args.critique)

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

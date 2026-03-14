#!/usr/bin/env python3
"""
End-to-end tests for the CtxFST agent loop runtime.

Tests cover:
1. Happy path — 3-step chain reaches goal
2. Goal already satisfied — loop exits immediately
3. No candidates — preconditions never satisfied
4. Stop on failure (default)
5. Continue on failure
6. Max iterations guard
7. Graph writeback — COMPLETED edges appended correctly
8. Goal proximity routing — closer skill ranks first
9. Idempotent skill re-execution allowed

Run:
    python tests/test_agent_loop.py
    python tests/test_agent_loop.py -v
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Allow importing from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from agent_loop import (
    CallbackExecutor,
    DryRunExecutor,
    ExecutionResult,
    LoopResult,
    run_loop,
)
from world_state import init_state, add_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(
    name: str,
    preconditions: list[str] | None = None,
    postconditions: list[str] | None = None,
    cost: str = "low",
    idempotent: bool = False,
) -> dict:
    return {
        "name": name,
        "description": f"Test skill {name}",
        "preconditions": preconditions or [],
        "postconditions": postconditions or [],
        "cost": cost,
        "idempotent": idempotent,
        "related_skills": [],
        "postcondition_count": len(postconditions or []),
        "_source_path": f"tests/{name}/SKILL.md",
    }


def _make_state(goal: str, active: list[str] | None = None) -> dict:
    state = init_state(goal)
    for s in active or []:
        add_state(state, s)
    return state


def _always_fail(skill, state) -> ExecutionResult:
    return ExecutionResult(result="failed", summary="forced failure")


def _always_partial(skill, state) -> ExecutionResult:
    return ExecutionResult(result="partial", summary="partial", new_states=skill.get("postconditions", []))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHappyPath(unittest.TestCase):
    """3-step chain: analyze → match → generate → goal reached."""

    def setUp(self):
        self.state = _make_state(
            goal="entity:learn-kubernetes-path",
            active=["entity:has-raw-resume"],
        )
        self.skills = [
            _make_skill("analyze-resume",
                        preconditions=["entity:has-raw-resume"],
                        postconditions=["entity:has-parsed-resume", "entity:has-skill-inventory"]),
            _make_skill("match-skills",
                        preconditions=["entity:has-skill-inventory"],
                        postconditions=["entity:has-skill-gap-analysis"],
                        cost="medium"),
            _make_skill("generate-plan",
                        preconditions=["entity:has-skill-gap-analysis"],
                        postconditions=["entity:learn-kubernetes-path"],
                        cost="high"),
        ]

    def test_goal_reached(self):
        result = run_loop(self.state, self.skills, DryRunExecutor())
        self.assertTrue(result.goal_reached)
        self.assertEqual(result.terminated_reason, "goal_reached")

    def test_correct_iteration_count(self):
        result = run_loop(self.state, self.skills, DryRunExecutor())
        self.assertEqual(result.iterations, 3)

    def test_skills_executed_in_order(self):
        result = run_loop(self.state, self.skills, DryRunExecutor())
        names = [s.skill_name for s in result.history]
        self.assertEqual(names, ["analyze-resume", "match-skills", "generate-plan"])

    def test_all_postconditions_in_active_states(self):
        run_loop(self.state, self.skills, DryRunExecutor())
        active = set(self.state["active_states"])
        for expected in [
            "entity:has-parsed-resume",
            "entity:has-skill-inventory",
            "entity:has-skill-gap-analysis",
            "entity:learn-kubernetes-path",
        ]:
            self.assertIn(expected, active)

    def test_completed_skills_recorded(self):
        run_loop(self.state, self.skills, DryRunExecutor())
        recorded = [r["skill"] for r in self.state["completed_skills"]]
        self.assertEqual(recorded, ["analyze-resume", "match-skills", "generate-plan"])


class TestGoalAlreadySatisfied(unittest.TestCase):
    """Goal is in active_states before the first iteration."""

    def test_exits_immediately(self):
        state = _make_state(
            goal="entity:goal",
            active=["entity:goal"],
        )
        result = run_loop(state, [], DryRunExecutor())
        self.assertTrue(result.goal_reached)
        self.assertEqual(result.terminated_reason, "goal_reached")
        self.assertEqual(result.iterations, 0)
        self.assertEqual(result.history, [])


class TestNoCandidates(unittest.TestCase):
    """No skill has satisfied preconditions from the start."""

    def test_terminates_no_candidates(self):
        state = _make_state(goal="entity:goal")
        skills = [
            _make_skill("needs-missing",
                        preconditions=["entity:does-not-exist"],
                        postconditions=["entity:goal"]),
        ]
        result = run_loop(state, skills, DryRunExecutor())
        self.assertFalse(result.goal_reached)
        self.assertEqual(result.terminated_reason, "no_candidates")
        self.assertEqual(result.iterations, 0)

    def test_empty_skill_list(self):
        state = _make_state(goal="entity:goal")
        result = run_loop(state, [], DryRunExecutor())
        self.assertFalse(result.goal_reached)
        self.assertEqual(result.terminated_reason, "no_candidates")


class TestStopOnFailure(unittest.TestCase):
    """stop_on_failure=True (default): loop halts on first failed execution."""

    def test_stops_after_failure(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        skills = [
            _make_skill("step1",
                        preconditions=["entity:start"],
                        postconditions=["entity:mid"]),
            _make_skill("step2",
                        preconditions=["entity:mid"],
                        postconditions=["entity:goal"]),
        ]
        result = run_loop(state, skills, CallbackExecutor(_always_fail), stop_on_failure=True)
        self.assertFalse(result.goal_reached)
        self.assertEqual(result.terminated_reason, "execution_failure")
        self.assertEqual(result.iterations, 1)
        # step2 was never attempted
        names = [s.skill_name for s in result.history]
        self.assertNotIn("step2", names)

    def test_failure_recorded_in_completed_skills(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        skills = [_make_skill("fail-skill", preconditions=["entity:start"], postconditions=["entity:goal"])]
        run_loop(state, skills, CallbackExecutor(_always_fail), stop_on_failure=True)
        self.assertEqual(self.state if False else state["completed_skills"][0]["result"], "failed")


class TestContinueOnFailure(unittest.TestCase):
    """stop_on_failure=False: loop continues after a failed execution."""

    def test_continues_past_failure(self):
        state = _make_state(goal="entity:goal", active=["entity:start", "entity:alt"])

        call_log: list[str] = []

        def selective_executor(skill, state) -> ExecutionResult:
            call_log.append(skill["name"])
            if skill["name"] == "bad-skill":
                return ExecutionResult(result="failed", summary="forced")
            return ExecutionResult(
                result="success",
                summary="ok",
                new_states=skill.get("postconditions", []),
            )

        skills = [
            _make_skill("bad-skill", preconditions=["entity:start"], postconditions=["entity:mid"]),
            _make_skill("good-skill", preconditions=["entity:alt"], postconditions=["entity:goal"]),
        ]
        result = run_loop(
            state, skills, CallbackExecutor(selective_executor), stop_on_failure=False
        )
        self.assertTrue(result.goal_reached)
        self.assertIn("bad-skill", call_log)
        self.assertIn("good-skill", call_log)


class TestMaxIterations(unittest.TestCase):
    """Loop terminates when max_iterations is reached."""

    def test_max_iterations_termination(self):
        # Idempotent skill that never produces the goal
        state = _make_state(goal="entity:unreachable", active=["entity:start"])
        skills = [
            _make_skill("loop-skill",
                        preconditions=["entity:start"],
                        postconditions=["entity:other"],
                        idempotent=True),
        ]
        result = run_loop(state, skills, DryRunExecutor(), max_iterations=3)
        self.assertFalse(result.goal_reached)
        self.assertEqual(result.terminated_reason, "max_iterations")
        self.assertEqual(result.iterations, 3)

    def test_max_iterations_one(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        skills = [
            _make_skill("s1", preconditions=["entity:start"], postconditions=["entity:mid"]),
            _make_skill("s2", preconditions=["entity:mid"], postconditions=["entity:goal"]),
        ]
        result = run_loop(state, skills, DryRunExecutor(), max_iterations=1)
        self.assertFalse(result.goal_reached)
        self.assertEqual(result.iterations, 1)


class TestGraphWriteback(unittest.TestCase):
    """COMPLETED edges are appended to the graph after each successful execution."""

    def test_completed_edges_appended(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        skills = [
            _make_skill("skill-a",
                        preconditions=["entity:start"],
                        postconditions=["entity:mid", "entity:side"]),
            _make_skill("skill-b",
                        preconditions=["entity:mid"],
                        postconditions=["entity:goal"]),
        ]
        graph: dict = {"meta": {}, "nodes": [], "edges": []}
        run_loop(state, skills, DryRunExecutor(), graph=graph)

        relations = [(e["source"], e["target"], e["relation"]) for e in graph["edges"]]
        self.assertIn(("skill-a", "entity:mid",  "COMPLETED"), relations)
        self.assertIn(("skill-a", "entity:side", "COMPLETED"), relations)
        self.assertIn(("skill-b", "entity:goal", "COMPLETED"), relations)

    def test_failed_skill_produces_no_edges(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        skills = [_make_skill("bad", preconditions=["entity:start"], postconditions=["entity:goal"])]
        graph: dict = {"meta": {}, "nodes": [], "edges": []}
        run_loop(state, skills, CallbackExecutor(_always_fail), graph=graph, stop_on_failure=False)
        completed = [e for e in graph["edges"] if e["relation"] == "COMPLETED"]
        self.assertEqual(completed, [])

    def test_completed_edge_properties(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        skills = [_make_skill("s", preconditions=["entity:start"], postconditions=["entity:goal"])]
        graph: dict = {"meta": {}, "nodes": [], "edges": []}
        run_loop(state, skills, DryRunExecutor(), graph=graph)

        edge = graph["edges"][0]
        self.assertEqual(edge["relation"], "COMPLETED")
        self.assertIn("timestamp", edge["properties"])
        self.assertEqual(edge["properties"]["status"], "active")


class TestGoalProximityRouting(unittest.TestCase):
    """skill_selector routes by goal proximity when subgraph is populated."""

    def test_closer_skill_ranked_first(self):
        from skill_selector import select_candidates, _goal_hop_distances

        # goal <-1- entity:mid <-1- entity:far
        state = _make_state(goal="entity:goal", active=["entity:start"])
        state["current_subgraph"] = {
            "nodes": ["entity:goal", "entity:mid", "entity:far"],
            "edges": [
                {"source": "entity:goal", "target": "entity:mid", "relation": "REQUIRES"},
                {"source": "entity:mid",  "target": "entity:far", "relation": "REQUIRES"},
            ],
        }

        skills_raw = [
            {"name": "far-skill",   "preconditions": [], "postconditions": ["entity:far"],  "cost": "low", "idempotent": False},
            {"name": "close-skill", "preconditions": [], "postconditions": ["entity:mid"],  "cost": "low", "idempotent": False},
        ]

        hops = _goal_hop_distances(state)
        self.assertEqual(hops["entity:mid"], 1)
        self.assertEqual(hops["entity:far"], 2)

        from skill_selector import scan_skills  # not needed here — use select_candidates directly
        # Patch postcondition_count (select_candidates expects it pre-set only via scan_skills;
        # replicate what scan_skills does)
        for s in skills_raw:
            s["postcondition_count"] = len(s["postconditions"])
            s["_source_path"] = ""

        candidates = select_candidates(state, skills_raw)
        self.assertEqual(candidates[0]["name"], "close-skill")
        self.assertEqual(candidates[0]["goal_proximity"], 1)
        self.assertEqual(candidates[1]["name"], "far-skill")
        self.assertEqual(candidates[1]["goal_proximity"], 2)

    def test_unknown_proximity_falls_back_gracefully(self):
        from skill_selector import select_candidates, _UNKNOWN_PROXIMITY

        state = _make_state(goal="entity:goal", active=[])
        # Empty subgraph → all proximities are unknown
        state["current_subgraph"] = {"nodes": [], "edges": []}

        skills_raw = [
            {"name": "b", "preconditions": [], "postconditions": ["x"], "cost": "low", "idempotent": False, "postcondition_count": 1, "_source_path": ""},
            {"name": "a", "preconditions": [], "postconditions": ["y", "z"], "cost": "low", "idempotent": False, "postcondition_count": 2, "_source_path": ""},
        ]
        candidates = select_candidates(state, skills_raw)
        # Falls back to postcondition_count sort: a (2) before b (1)
        self.assertEqual(candidates[0]["name"], "a")
        for c in candidates:
            self.assertEqual(c["goal_proximity"], _UNKNOWN_PROXIMITY)


class TestIdempotentReexecution(unittest.TestCase):
    """Idempotent skills may be re-selected after completion."""

    def test_idempotent_skill_reruns(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        # Only one idempotent skill that never produces the goal
        skills = [
            _make_skill("refresh",
                        preconditions=["entity:start"],
                        postconditions=["entity:data"],
                        idempotent=True),
        ]
        result = run_loop(state, skills, DryRunExecutor(), max_iterations=3)
        self.assertEqual(result.iterations, 3)
        names = [s.skill_name for s in result.history]
        self.assertEqual(names.count("refresh"), 3)

    def test_non_idempotent_skill_not_rerun(self):
        state = _make_state(goal="entity:goal", active=["entity:start"])
        skills = [
            _make_skill("one-shot",
                        preconditions=["entity:start"],
                        postconditions=["entity:data"],
                        idempotent=False),
        ]
        result = run_loop(state, skills, DryRunExecutor(), max_iterations=5)
        # After first run, one-shot is completed and not eligible again → no_candidates
        self.assertEqual(result.terminated_reason, "no_candidates")
        self.assertEqual(result.iterations, 1)


# ---------------------------------------------------------------------------
# Relation-aware routing tests
# ---------------------------------------------------------------------------

class TestRelationSpecificExplanations(unittest.TestCase):
    """explain_selection and find_plan_with_explanation produce correct reasoning."""

    # --- explain_selection ---

    def test_explain_selection_no_candidates(self):
        from skill_selector import explain_selection
        result = explain_selection([], _make_state(goal="entity:goal"))
        self.assertEqual(result, "No eligible candidates.")

    def test_explain_selection_single_winner(self):
        from skill_selector import explain_selection, select_candidates
        state = _make_state(goal="entity:goal", active=[])
        state["current_subgraph"] = {"nodes": [], "edges": []}
        skills_raw = [
            {"name": "only", "preconditions": [], "postconditions": ["entity:x"],
             "cost": "low", "idempotent": False, "postcondition_count": 1, "_source_path": ""},
        ]
        candidates = select_candidates(state, skills_raw)
        explanation = explain_selection(candidates, state)
        self.assertIn("Selected:  only", explanation)
        self.assertNotIn("Rejected", explanation)

    def test_explain_selection_shows_rejected(self):
        from skill_selector import explain_selection, select_candidates
        state = _make_state(goal="entity:goal", active=[])
        state["current_subgraph"] = {"nodes": [], "edges": []}
        skills_raw = [
            {"name": "cheap", "preconditions": [], "postconditions": ["entity:x"],
             "cost": "low",  "idempotent": False, "postcondition_count": 1, "_source_path": ""},
            {"name": "pricey", "preconditions": [], "postconditions": ["entity:y"],
             "cost": "high", "idempotent": False, "postcondition_count": 1, "_source_path": ""},
        ]
        candidates = select_candidates(state, skills_raw)
        explanation = explain_selection(candidates, state)
        self.assertIn("Selected:  cheap", explanation)
        self.assertIn("Rejected", explanation)
        self.assertIn("pricey", explanation)
        self.assertIn("cost high > low", explanation)

    def test_explain_selection_names_edge_relation(self):
        """When subgraph exists, explanation names the edge relation (REQUIRES/SIMILAR)."""
        from skill_selector import explain_selection, select_candidates
        state = _make_state(goal="entity:goal", active=[])
        state["current_subgraph"] = {
            "nodes": [],
            "edges": [
                {"source": "entity:goal", "target": "entity:causal",  "relation": "REQUIRES"},
                {"source": "entity:goal", "target": "entity:similar", "relation": "SIMILAR"},
            ],
        }
        state["completed_skills"] = []
        skills_raw = [
            {"name": "skill-similar", "preconditions": [], "postconditions": ["entity:similar"],
             "cost": "low", "idempotent": False, "postcondition_count": 1, "_source_path": ""},
            {"name": "skill-causal",  "preconditions": [], "postconditions": ["entity:causal"],
             "cost": "low", "idempotent": False, "postcondition_count": 1, "_source_path": ""},
        ]
        candidates = select_candidates(state, skills_raw)
        explanation = explain_selection(candidates, state)
        # Winner is skill-causal (REQUIRES = weight 1 < SIMILAR = weight 3)
        self.assertIn("skill-causal", explanation.split("Selected:")[1].split("\n")[0])
        self.assertIn("REQUIRES", explanation)

    # --- find_plan_with_explanation ---

    def test_explanation_plan_matches_find_plan(self):
        from skill_selector import find_plan, find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        expected = find_plan(state, skills, max_depth=5)
        result = find_plan_with_explanation(state, skills, max_depth=5)
        self.assertEqual(result.plan, expected)

    def test_explanation_no_plan_summary(self):
        from skill_selector import find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=[])
        result = find_plan_with_explanation(state, [], max_depth=5)
        self.assertEqual(result.plan, [])
        self.assertIn("No plan found", result.summary)

    def test_explanation_goal_already_active(self):
        from skill_selector import find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=["entity:goal"])
        result = find_plan_with_explanation(state, [], max_depth=5)
        self.assertIn("already satisfied", result.summary)

    def test_step_traces_correct(self):
        from skill_selector import find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        result = find_plan_with_explanation(state, skills, max_depth=5)
        self.assertEqual(len(result.steps), 2)
        self.assertEqual(result.steps[0].skill_name, "s1")
        self.assertIn("entity:a", result.steps[0].preconditions_matched)
        self.assertIn("entity:b", result.steps[0].postconditions_added)
        self.assertEqual(result.steps[1].skill_name, "s2")
        self.assertIn("entity:goal", result.steps[1].postconditions_added)

    def test_step_traces_only_new_postconditions(self):
        """Already-active entities must not appear in postconditions_added."""
        from skill_selector import find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=["entity:a", "entity:b"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b", "entity:goal"]),
        ]
        result = find_plan_with_explanation(state, skills, max_depth=5)
        # entity:b already active → not in postconditions_added
        self.assertNotIn("entity:b", result.steps[0].postconditions_added)
        self.assertIn("entity:goal", result.steps[0].postconditions_added)

    def test_alternatives_are_different_plans(self):
        from skill_selector import find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("route1", preconditions=["entity:a"], postconditions=["entity:goal"]),
            _make_skill("detour1", preconditions=["entity:a"], postconditions=["entity:mid"]),
            _make_skill("detour2", preconditions=["entity:mid"], postconditions=["entity:goal"]),
        ]
        result = find_plan_with_explanation(state, skills, max_depth=5, top_k=3)
        self.assertGreater(len(result.alternatives), 0)
        for alt in result.alternatives:
            self.assertNotEqual(alt, result.plan)

    def test_summary_contains_goal_marker(self):
        from skill_selector import find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [_make_skill("s1", preconditions=["entity:a"], postconditions=["entity:goal"])]
        result = find_plan_with_explanation(state, skills, max_depth=5)
        self.assertIn("← GOAL", result.summary)

    def test_summary_contains_alternative_reason(self):
        from skill_selector import find_plan_with_explanation
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("short",  preconditions=["entity:a"], postconditions=["entity:goal"], cost="low"),
            _make_skill("detour1", preconditions=["entity:a"], postconditions=["entity:mid"], cost="low"),
            _make_skill("detour2", preconditions=["entity:mid"], postconditions=["entity:goal"], cost="low"),
        ]
        result = find_plan_with_explanation(state, skills, max_depth=5, top_k=3)
        # best = ["short"], alternative = ["detour1","detour2"] — longer
        self.assertTrue(any("longer" in r for alt in result.alternatives
                            for r in [result.summary]))

    # --- run_loop integration ---

    def test_run_loop_explain_does_not_change_result(self):
        """explain=True must not affect the outcome — only the log output."""
        state_a = _make_state(goal="entity:goal", active=["entity:a"])
        state_b = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        r_plain   = run_loop(state_a, skills, DryRunExecutor(), explain=False)
        r_explain = run_loop(state_b, skills, DryRunExecutor(), explain=True)
        self.assertEqual(r_plain.goal_reached,  r_explain.goal_reached)
        self.assertEqual(r_plain.iterations,    r_explain.iterations)
        self.assertEqual([s.skill_name for s in r_plain.history],
                         [s.skill_name for s in r_explain.history])

    def test_run_loop_explain_with_lookahead(self):
        """explain=True + lookahead > 0 uses find_plan_with_explanation."""
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:goal"]),
        ]
        result = run_loop(state, skills, DryRunExecutor(), lookahead=3, explain=True)
        self.assertTrue(result.goal_reached)


class TestMultiStepPlanning(unittest.TestCase):
    """find_plan returns the shortest skill sequence; run_loop with lookahead uses it."""

    # --- find_plan unit tests ---

    def test_finds_3_step_chain(self):
        from skill_selector import find_plan
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:c"]),
            _make_skill("s3", preconditions=["entity:c"], postconditions=["entity:goal"]),
        ]
        plan = find_plan(state, skills, max_depth=5)
        self.assertEqual(plan, ["s1", "s2", "s3"])

    def test_returns_empty_when_goal_already_active(self):
        from skill_selector import find_plan
        state = _make_state(goal="entity:goal", active=["entity:goal"])
        plan = find_plan(state, [], max_depth=5)
        self.assertEqual(plan, [])

    def test_returns_none_when_no_path(self):
        from skill_selector import find_plan
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [_make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"])]
        plan = find_plan(state, skills, max_depth=5)
        self.assertIsNone(plan)

    def test_returns_none_when_depth_exceeded(self):
        from skill_selector import find_plan
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        plan = find_plan(state, skills, max_depth=1)  # chain needs 2 steps
        self.assertIsNone(plan)

    def test_finds_shortest_path_when_multiple_routes(self):
        """
        Two routes to goal:
          long:  a → b → c → goal  (3 steps)
          short: a → goal          (1 step)
        BFS should return the 1-step route.
        """
        from skill_selector import find_plan
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("long-s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("long-s2", preconditions=["entity:b"], postconditions=["entity:c"]),
            _make_skill("long-s3", preconditions=["entity:c"], postconditions=["entity:goal"]),
            _make_skill("short",   preconditions=["entity:a"], postconditions=["entity:goal"]),
        ]
        plan = find_plan(state, skills, max_depth=5)
        self.assertEqual(plan, ["short"])

    def test_does_not_reuse_non_idempotent_skill(self):
        """A non-idempotent skill must not appear twice in the plan."""
        from skill_selector import find_plan
        # Only path: s1 (non-idempotent) → s2.  Can't loop via s1 again.
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"],    postconditions=["entity:b"], idempotent=False),
            _make_skill("s2", preconditions=["entity:b"],    postconditions=["entity:goal"]),
        ]
        plan = find_plan(state, skills, max_depth=5)
        self.assertEqual(plan, ["s1", "s2"])
        self.assertEqual(plan.count("s1"), 1)

    def test_skips_already_completed_non_idempotent(self):
        """find_plan respects skills already completed in state."""
        from skill_selector import find_plan
        state = _make_state(goal="entity:goal", active=["entity:a", "entity:b"])
        state["completed_skills"] = [{"skill": "s1", "result": "success"}]
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"], idempotent=False),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        plan = find_plan(state, skills, max_depth=5)
        # s1 already done and non-idempotent → plan starts from s2
        self.assertEqual(plan, ["s2"])

    # --- run_loop integration with lookahead ---

    def test_lookahead_reaches_goal(self):
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        result = run_loop(state, skills, DryRunExecutor(), lookahead=5)
        self.assertTrue(result.goal_reached)
        self.assertEqual(result.iterations, 2)

    def test_lookahead_falls_back_to_greedy_when_no_plan(self):
        """When find_plan returns None, loop falls back to greedy and still progresses."""
        state = _make_state(goal="entity:unreachable", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"], idempotent=True),
        ]
        # lookahead=1: find_plan can't see goal in 1 step → None → greedy picks s1
        result = run_loop(state, skills, DryRunExecutor(), lookahead=1, max_iterations=2)
        self.assertEqual(result.iterations, 2)
        names = [s.skill_name for s in result.history]
        self.assertEqual(names.count("s1"), 2)

    def test_lookahead_zero_is_greedy(self):
        """lookahead=0 must behave identically to the original greedy loop."""
        state_a = _make_state(goal="entity:goal", active=["entity:a"])
        state_b = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        r_greedy   = run_loop(state_a, skills, DryRunExecutor(), lookahead=0)
        r_lookahead = run_loop(state_b, skills, DryRunExecutor(), lookahead=5)
        self.assertEqual(r_greedy.iterations,          r_lookahead.iterations)
        self.assertEqual(r_greedy.goal_reached,        r_lookahead.goal_reached)
        self.assertEqual([s.skill_name for s in r_greedy.history],
                         [s.skill_name for s in r_lookahead.history])


class TestRelationAwareRouting(unittest.TestCase):
    """_goal_hop_distances uses EDGE_WEIGHTS to distinguish causal vs. similar edges."""

    def _state_with_edges(self, edges: list[dict]) -> dict:
        state = _make_state(goal="entity:goal", active=[])
        state["current_subgraph"] = {"nodes": [], "edges": edges}
        return state

    def test_requires_costs_1(self):
        from skill_selector import _goal_hop_distances
        state = self._state_with_edges([
            {"source": "entity:goal", "target": "entity:mid", "relation": "REQUIRES"},
        ])
        hops = _goal_hop_distances(state)
        self.assertEqual(hops["entity:mid"], 1)

    def test_leads_to_costs_1(self):
        from skill_selector import _goal_hop_distances
        state = self._state_with_edges([
            {"source": "entity:mid", "target": "entity:goal", "relation": "LEADS_TO"},
        ])
        hops = _goal_hop_distances(state)
        self.assertEqual(hops["entity:mid"], 1)

    def test_similar_costs_3(self):
        from skill_selector import _goal_hop_distances
        state = self._state_with_edges([
            {"source": "entity:goal", "target": "entity:near", "relation": "SIMILAR"},
        ])
        hops = _goal_hop_distances(state)
        self.assertEqual(hops["entity:near"], 3)

    def test_completed_is_skipped(self):
        from skill_selector import _goal_hop_distances
        state = self._state_with_edges([
            {"source": "entity:old-skill", "target": "entity:goal", "relation": "COMPLETED"},
        ])
        hops = _goal_hop_distances(state)
        # COMPLETED is skipped — entity:old-skill must not be reachable from goal
        self.assertNotIn("entity:old-skill", hops)

    def test_blocked_by_is_skipped(self):
        from skill_selector import _goal_hop_distances
        state = self._state_with_edges([
            {"source": "entity:goal", "target": "entity:blocker", "relation": "BLOCKED_BY"},
        ])
        hops = _goal_hop_distances(state)
        self.assertNotIn("entity:blocker", hops)

    def test_causal_beats_similar_at_same_hop_count(self):
        """requires-skill (dist=1) ranks before similar-skill (dist=3), same cost."""
        from skill_selector import select_candidates
        state = self._state_with_edges([
            {"source": "entity:goal", "target": "entity:causal", "relation": "REQUIRES"},
            {"source": "entity:goal", "target": "entity:similar", "relation": "SIMILAR"},
        ])
        state["active_states"] = []
        state["completed_skills"] = []

        skills_raw = [
            {"name": "skill-similar", "preconditions": [], "postconditions": ["entity:similar"],
             "cost": "low", "idempotent": False, "postcondition_count": 1, "_source_path": ""},
            {"name": "skill-causal",  "preconditions": [], "postconditions": ["entity:causal"],
             "cost": "low", "idempotent": False, "postcondition_count": 1, "_source_path": ""},
        ]
        candidates = select_candidates(state, skills_raw)
        self.assertEqual(candidates[0]["name"], "skill-causal")
        self.assertEqual(candidates[0]["goal_proximity"], 1)
        self.assertEqual(candidates[1]["name"], "skill-similar")
        self.assertEqual(candidates[1]["goal_proximity"], 3)

    def test_dijkstra_finds_shorter_mixed_path(self):
        """
        Two paths to entity:mid from goal:
          goal -REQUIRES(1)-> entity:mid          total = 1
          goal -SIMILAR(3)-> entity:hop -REQUIRES(1)-> entity:mid  total = 4
        Dijkstra should report distance 1, not 4.
        """
        from skill_selector import _goal_hop_distances
        state = self._state_with_edges([
            {"source": "entity:goal", "target": "entity:mid",  "relation": "REQUIRES"},
            {"source": "entity:goal", "target": "entity:hop",  "relation": "SIMILAR"},
            {"source": "entity:hop",  "target": "entity:mid",  "relation": "REQUIRES"},
        ])
        hops = _goal_hop_distances(state)
        self.assertEqual(hops["entity:mid"], 1)

    def test_completed_edge_does_not_pollute_proximity(self):
        """
        A COMPLETED edge from skill to goal must not make the skill appear
        close to the goal in future planning.
        """
        from skill_selector import _goal_hop_distances
        state = self._state_with_edges([
            {"source": "entity:done-skill", "target": "entity:goal", "relation": "COMPLETED"},
            {"source": "entity:goal", "target": "entity:real",      "relation": "REQUIRES"},
        ])
        hops = _goal_hop_distances(state)
        self.assertNotIn("entity:done-skill", hops)
        self.assertEqual(hops["entity:real"], 1)


# ---------------------------------------------------------------------------
# Interactive plan critique tests
# ---------------------------------------------------------------------------

class TestInteractivePlanCritique(unittest.TestCase):
    """critique_plan() collects human feedback and returns accepted plan or None."""

    def _setup(self):
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
            _make_skill("alt", preconditions=["entity:a"], postconditions=["entity:goal"], cost="high"),
        ]
        return state, skills

    def _explanation(self, state, skills, max_depth=5):
        from skill_selector import find_plan_with_explanation
        return find_plan_with_explanation(state, skills, max_depth=max_depth)

    # --- critique_plan unit tests ---

    def test_accept_returns_plan(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        with patch("builtins.input", return_value="a"):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertEqual(result, expl.plan)

    def test_quit_returns_none(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        with patch("builtins.input", return_value="q"):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertIsNone(result)

    def test_eof_returns_none(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        with patch("builtins.input", side_effect=EOFError):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertIsNone(result)

    def test_skip_replans_without_skill(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        # Best plan is s1→s2. Skip s1 → should find alt→goal
        with patch("builtins.input", side_effect=["s s1", "a"]):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertIsNotNone(result)
        self.assertNotIn("s1", result)

    def test_skip_unknown_skill_stays_in_loop(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        # Unknown skill → stays in loop; then accept
        with patch("builtins.input", side_effect=["s nonexistent", "a"]):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertEqual(result, expl.plan)

    def test_reset_restores_original_plan(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        original_plan = list(expl.plan)
        # Skip s1 (replans), then reset (back to original), then accept
        with patch("builtins.input", side_effect=["s s1", "r", "a"]):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertEqual(result, original_plan)

    def test_force_valid_skill(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        # alt has preconditions=["entity:a"] which is active → can be forced
        with patch("builtins.input", side_effect=["f alt", "a"]):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "alt")

    def test_force_unmet_preconditions_stays_in_loop(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        # s2 requires entity:b which is not active → force should fail
        with patch("builtins.input", side_effect=["f s2", "a"]):
            result = critique_plan(expl, state, skills, max_depth=5)
        # After failed force, accepted original plan
        self.assertEqual(result, expl.plan)

    def test_force_unknown_skill_stays_in_loop(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        with patch("builtins.input", side_effect=["f ghost", "a"]):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertEqual(result, expl.plan)

    def test_invalid_command_stays_in_loop(self):
        from agent_loop import critique_plan
        state, skills = self._setup()
        expl = self._explanation(state, skills)
        with patch("builtins.input", side_effect=["???", "a"]):
            result = critique_plan(expl, state, skills, max_depth=5)
        self.assertEqual(result, expl.plan)

    # --- run_loop integration ---

    def test_run_loop_critique_accept_reaches_goal(self):
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        with patch("builtins.input", return_value="a"):
            result = run_loop(state, skills, DryRunExecutor(), lookahead=5, critique=True)
        self.assertTrue(result.goal_reached)
        self.assertEqual(result.terminated_reason, "goal_reached")

    def test_run_loop_critique_quit_returns_user_aborted(self):
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [_make_skill("s1", preconditions=["entity:a"], postconditions=["entity:goal"])]
        with patch("builtins.input", return_value="q"):
            result = run_loop(state, skills, DryRunExecutor(), lookahead=5, critique=True)
        self.assertFalse(result.goal_reached)
        self.assertEqual(result.terminated_reason, "user_aborted")

    def test_run_loop_critique_skip_then_accept_uses_alternative(self):
        state = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1",  preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2",  preconditions=["entity:b"], postconditions=["entity:goal"]),
            _make_skill("alt", preconditions=["entity:a"], postconditions=["entity:goal"], cost="high"),
        ]
        # Skip s1 → forces alt route; accept; then loop hits goal
        with patch("builtins.input", side_effect=["s s1", "a"]):
            result = run_loop(state, skills, DryRunExecutor(), lookahead=5, critique=True)
        self.assertTrue(result.goal_reached)
        # alt was used as first (and only) step
        self.assertEqual(result.history[0].skill_name, "alt")

    def test_run_loop_critique_does_not_change_non_critique_result(self):
        """critique=False must give same outcome as critique=True with auto-accept."""
        state_a = _make_state(goal="entity:goal", active=["entity:a"])
        state_b = _make_state(goal="entity:goal", active=["entity:a"])
        skills = [
            _make_skill("s1", preconditions=["entity:a"], postconditions=["entity:b"]),
            _make_skill("s2", preconditions=["entity:b"], postconditions=["entity:goal"]),
        ]
        r_normal = run_loop(state_a, skills, DryRunExecutor(), lookahead=5)
        with patch("builtins.input", return_value="a"):
            r_critique = run_loop(state_b, skills, DryRunExecutor(), lookahead=5, critique=True)
        self.assertEqual(r_normal.goal_reached,  r_critique.goal_reached)
        self.assertEqual(r_normal.iterations,    r_critique.iterations)
        self.assertEqual([s.skill_name for s in r_normal.history],
                         [s.skill_name for s in r_critique.history])


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)

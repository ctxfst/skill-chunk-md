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
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)

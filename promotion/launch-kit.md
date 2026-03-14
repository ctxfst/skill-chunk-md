# ctxfst Launch Kit

Reusable copy for GitHub, Hacker News, Reddit, Discord, and X.

## Core positioning

`ctxfst` is a **semantic world model substrate** for RAG and agents. It keeps `entities`, `context`, `content`, and operational metadata (`state`, `action`, `goal`, `preconditions`, `postconditions`) structured so the same document powers vector retrieval, graph workflows, deterministic agent planning, and human-in-the-loop plan critique — on one stable, backward-compatible backbone.

## Short repo description

Context-first Markdown → CtxFST world model: structured `<Chunk>` tags, canonical entities, JSON export, entity-graph building, deterministic agent loop with goal-aware + relation-aware routing, multi-step lookahead planning, relation-specific explanations, and interactive plan critique.

## One-paragraph project description

`ctxfst` is a structured document format that turns Markdown into a **semantic world model** for RAG and agents. It separates `entities`, `context`, and `content`, and lets entities represent both descriptive knowledge (skills, tools) and operational nodes (states, actions, goals) with `preconditions`/`postconditions`. A complete reference runtime is included: validate, export to JSON, build entity graphs with similarity and causal edges, then run a deterministic agent loop that uses BFS lookahead planning, Dijkstra-weighted goal-proximity routing (causal edges cost 1, similarity edges cost 3), and relation-specific explanations for every selection decision. The loop supports interactive plan critique — humans can accept, skip, force, or reset the plan before each execution step — making it a human-in-the-loop planning interface, not just a demo.

## Problem this solves

- Normal chunking loses the surrounding meaning of a passage.
- Context is usually buried in one opaque embedding string with no structure to inspect or update.
- Graph pipelines must re-extract noisy entities from raw text every time.
- Agent world models are usually ad-hoc Python dicts with no shared format, no causal edges, and no planning surface.
- Most agent selectors are LLM calls with no determinism, no explainability, and no human override.
- Teams need one format that works across authoring, validation, export, graph derivation, agent planning, and human review.

## Why this is different

- `ctxfst` stores `context` as structured metadata, not prepended text.
- `entities[]` gives you canonical graph nodes up front, including **operational types** (`state`, `action`, `goal`, `agent`, `evidence`).
- `chunks[].entities` and `chunks[].dependencies` create explicit chunk-to-entity and chunk-to-chunk edges.
- `preconditions` / `postconditions` on entities let the graph builder auto-infer causal edges (`REQUIRES`, `LEADS_TO`).
- **Relation-aware routing**: the skill selector runs Dijkstra with `REQUIRES`/`LEADS_TO` at weight 1, `SIMILAR` at weight 3, `COMPLETED`/`BLOCKED_BY` skipped — causal-path skills rank above semantically-similar ones.
- **Multi-step lookahead**: `find_plan()` runs BFS over the skill application graph to find the shortest sequence to the goal, replanning after every execution step.
- **Relation-specific explanations**: every selection decision names the edge relation that contributed to proximity, so you can audit why `skill-A` beat `skill-B`.
- **Interactive plan critique**: before each execution step, humans can `skip` a skill, `force` a different first step (precondition-checked), or `reset` constraints — the planner replans on every command.
- **66 end-to-end tests** cover happy path, failure tolerance, goal-aware routing, relation-aware routing, multi-step planning, explanation output, and all critique commands.
- **No LLM required** at any stage of the planning loop — purely deterministic and inspectable.

## Proof points from the included demos

**Career demo (structure benchmark)** — one plain Markdown profile → :

- 5 structured chunks
- 4 canonical entities
- 6 derived `Entity → Entity` similarity edges
- `chunks.json` + `entity-profiles.json` + `entity-graph.json`, all from one source document

**World model demo (agent benchmark)** — one CtxFST document → :

- operational entities for `state`, `action`, `goal`, `agent`, `evidence`
- auto-inferred `REQUIRES`/`LEADS_TO` causal edges from `preconditions`/`postconditions`
- `world-state.json` session consumed by the full agent loop

**Agent loop demo (runtime benchmark)** — 3 chained SKILL.md files → :

```
[Step 1] Plan (3 steps): analyze-resume → match-skills → generate-plan
[Step 1]   Step 1: analyze-resume
[Step 1]     pre  ✓  entity:has-raw-resume
[Step 1]     post +  entity:has-parsed-resume
[Step 1]     post +  entity:has-skill-inventory
...
[Step 3]     post +  entity:learn-kubernetes-path ← GOAL
✅ Loop finished: goal_reached  Iterations: 3
```

---

## GitHub release draft

### Release title

`v2.1.0 — Complete Agent Runtime: Lookahead Planning, Relation-Aware Routing, Explanations, and Interactive Plan Critique`

### Release notes

This release completes the `ctxfst` agent runtime by closing the full planner→executor→world-state loop and adding four major capabilities on top of the v2.0 world model foundation.

**Closed-loop agent runtime (`agent_loop.py`)**
- Orchestrates the full cycle: read world state → select skill → execute → write postconditions back → repeat
- Three executor modes: `DryRunExecutor`, `InteractiveExecutor`, `CallbackExecutor`
- Terminates cleanly on: goal reached, no candidates, max iterations, execution failure, user abort
- Optional `COMPLETED` edge writeback to `entity-graph.json` after each successful step

**Goal-aware + relation-aware routing (`skill_selector.py`)**
- `_goal_hop_distances`: Dijkstra over `current_subgraph` with relation-specific weights
- `EDGE_WEIGHTS`: `REQUIRES`/`LEADS_TO` = 1, `EVIDENCE`/`IMPLIES` = 2, `SIMILAR` = 3, `COMPLETED`/`BLOCKED_BY` = skipped
- Sort order: `cost → goal_proximity → postcondition_count → name`

**Multi-step lookahead planning (`find_plan`)**
- BFS over the skill application graph `(active_states, completed_non_idempotent)` as state nodes
- Returns the **shortest** skill sequence to the goal within `max_depth` steps
- Replanning at each iteration: adapts after partial failures and unexpected postconditions
- Falls back to greedy when no path found within depth limit
- `--lookahead N` CLI flag

**Relation-specific explanations (`explain_selection`, `find_plan_with_explanation`)**
- `explain_selection`: names the edge relation (REQUIRES vs SIMILAR) that drove each ranking decision
- `find_plan_with_explanation`: per-step trace of preconditions satisfied and postconditions added, plus alternatives with comparison reasons
- `--explain` CLI flag

**Interactive plan critique (`critique_plan`)**
- Presents plan + explanation before each execution step
- Five commands: `a` accept, `s <skill>` skip+replan, `f <skill>` force (precondition-checked), `r` reset, `q` quit
- `--critique` CLI flag (auto-enables `--lookahead 5`)
- `terminated_reason="user_aborted"` when user quits

**66 end-to-end tests** (`tests/test_agent_loop.py`)
- All critique commands tested with `unittest.mock.patch('builtins.input')`
- Covers happy path, failure modes, idempotency, graph writeback, goal proximity, relation weights, multi-step planning, explanation output

Start here:
- `skill-chunk-md/README.md`
- `skill-chunk-md/scripts/agent_loop.py` — CLI entry point for the full runtime
- `skill-chunk-md/tests/test_agent_loop.py` — end-to-end test suite
- `skill-chunk-md/assets/examples/career/` — structure benchmark
- `skill-chunk-md/assets/examples/world-model-example.md` — agent benchmark

---

## Hacker News

### Title options

- `Show HN: ctxfst — Markdown → agent-ready world model with deterministic lookahead planning`
- `Show HN: ctxfst v2.1 — semantic world model format with relation-aware routing and human-in-the-loop plan critique`
- `ctxfst: one document format for RAG, graph pipelines, and deterministic agent planning (no LLM required)`

### Post body

I built `ctxfst`, a semantic world model format that turns Markdown into documents that can power vector RAG, graph-based retrieval, and deterministic agent planning — from the same source file.

The core insight: if you store `entities` (including `state`, `action`, `goal`) with `preconditions`/`postconditions` as structured fields, you get a document that is simultaneously:

- a retrieval chunk set (for vector search)
- a graph node catalog (for entity traversal)
- a planning surface (for agent skill selection)

The reference runtime now includes a complete closed-loop agent:

1. **Format + validation** — `<Chunk>` tags + YAML frontmatter + JSON Schema
2. **Export pipeline** — `chunks.json` → `entity-profiles.json` → `entity-graph.json`
3. **Relation-aware routing** — Dijkstra over the entity graph where `REQUIRES`/`LEADS_TO` cost 1 and `SIMILAR` costs 3, so skills on the causal path rank above semantically-similar ones
4. **Multi-step lookahead planning** — BFS over the skill application graph to find the shortest sequence to goal, replanning after every execution step
5. **Relation-specific explanations** — every selection names which edge relation drove the ranking
6. **Interactive plan critique** — before each execution step, humans can skip a skill, force a different route (precondition-checked), or reset constraints

No LLM involved in the planning loop. Fully deterministic and testable — 66 end-to-end tests included.

I would especially appreciate feedback from people building GraphRAG or agentic workflows: is making `preconditions`/`postconditions` a first-class field in the document format the right abstraction boundary for world models?

---

## Reddit

### Title

`ctxfst v2.1: Markdown → deterministic agent world model with lookahead planning and human-in-the-loop critique (no LLM needed)`

### Post

I've been building `ctxfst`, a structured document format that tries to fix two annoying problems at once:

1. Normal RAG chunking loses context too early.
2. Agent world models are undocumented ad-hoc Python dicts that break silently.

The idea: store `entities` (including `state`, `action`, `goal`) with `preconditions`/`postconditions` as first-class YAML fields. That single change makes the document usable for vector retrieval, entity graph traversal, *and* agent planning — without rewriting anything.

The reference runtime now includes a complete loop:

**Planning layer (no LLM)**
- `find_plan()` — BFS over the skill application graph, returns the shortest skill sequence to goal
- Relation-aware routing — Dijkstra with `REQUIRES`/`LEADS_TO` at weight 1, `SIMILAR` at weight 3 — causal-path skills rank above semantic-neighbor skills
- Replanning at each step — adapts after partial failures

**Explanation layer**
- Every selection names the edge relation that drove the ranking decision
- Per-step trace: which preconditions were satisfied, which postconditions were newly added

**Human-in-the-loop critique**
- Before each execution step, you can: `skip` a skill and replan, `force` a different first step (preconditions are checked), or `reset` all constraints
- The planner replans immediately on every command
- Tested with mocked inputs — 66 end-to-end tests total

The whole planning loop runs without any LLM call. Deterministic, inspectable, and testable.

Demos included: career profile → entity graph, world model example → `REQUIRES`/`LEADS_TO` edges, 3-skill chain → agent loop reaching goal in 3 iterations with full explanation output.

Would love feedback from people on r/MachineLearning, r/LangChain, or r/LocalLLaMA building agentic workflows about whether the world model abstraction boundary is useful.

---

## Discord showcase

Built an open-source reference runtime for `ctxfst` — a semantic world model document format for RAG and agents. The new release closes the full planning loop: BFS lookahead planning, relation-aware Dijkstra routing (causal edges cost 1, similarity edges cost 3), relation-specific explanations that name *why* a skill was chosen, and interactive plan critique where humans can skip skills, force alternatives, or reset constraints before each execution step. No LLM in the planning loop — fully deterministic, 66 end-to-end tests. Works with LanceDB, Lance Graph, HelixDB, LightRAG, HippoRAG. Demo goes from 1 Markdown file → chunks → entity graph → agent loop reaching goal with full explanation trace.

---

## X thread

### Post 1

Most agent planners are LLM calls wrapped in a loop.

`ctxfst` ships a deterministic agent runtime built on structured document fields:
- `preconditions` / `postconditions` in YAML frontmatter
- causal edge inference from the entity graph
- BFS lookahead that finds the shortest skill path to goal

No LLM needed in the planning loop.

### Post 2

The routing is relation-aware.

`REQUIRES`/`LEADS_TO` edges cost 1.
`SIMILAR` edges cost 3.
`COMPLETED`/`BLOCKED_BY` are skipped entirely.

Dijkstra picks the causal path to goal, not the nearest semantic neighbor.

Every selection names the edge relation that drove the decision.

### Post 3

The planner also explains itself.

Before each execution step you see:

```
Best plan (3 steps): analyze-resume → match-skills → generate-plan
  Step 1: analyze-resume
    pre  ✓  entity:has-raw-resume
    post +  entity:has-parsed-resume  ← via REQUIRES (weight 1)
```

And the alternatives it considered — with reasons why they lost.

### Post 4

And if the plan is wrong, you can fix it.

```
Commands: [a]ccept  [s]kip <skill>  [f]orce <skill>  [r]eset  [q]uit
> s match-skills
♻️  Replanning without 'match-skills'...
> f alt-route
🔒 Forcing 'alt-route' as first step...
> a
✅ Accepted: alt-route → generate-plan
```

The planner replans on every command. Preconditions are checked before any force.

### Post 5

The full runtime is in one repo:

- format spec + JSON Schema (v2.0)
- export pipeline → `chunks.json` + `entity-graph.json`
- deterministic agent loop with 66 end-to-end tests
- works with LanceDB, HelixDB, LightRAG, HippoRAG

Coming next: integration examples and `ctxc` — a compiler that auto-generates CtxFST documents from raw notes.

If you are building GraphRAG or agent workflows, what is the right abstraction boundary for world models?

---

## Coming soon (teaser)

### Integration examples

Walkthroughs showing `ctxfst` wired into:
- **LanceDB** — vector search over `chunks.json` with entity filtering
- **Lance Graph** — entity-graph traversal with `REQUIRES`/`LEADS_TO` edges
- **HelixDB** — hybrid vector + graph queries on the same entity catalog
- **LightRAG / HippoRAG** — drop-in replacement for their entity extraction layer

### `ctxc` compiler (upcoming)

A CLI tool that takes raw Markdown notes and automatically produces a valid CtxFST document — handling chunking, entity extraction, normalization, and frontmatter generation without manual tagging. Lowers the authoring barrier from "know the format" to "just write Markdown."

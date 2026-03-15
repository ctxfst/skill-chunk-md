# ctxfst Launch Kit

Reusable copy for GitHub, Hacker News, Reddit, Discord, and X.

Two audiences, two angles:
- **Angle A (Developer)**: semantic world model for RAG, graph pipelines, and deterministic agent planning
- **Angle B (AI User)**: debuggable AI memory — see what your AI remembers, find errors, fix them

---

## Core positioning

`ctxfst` is a **semantic world model substrate** for RAG and agents. It keeps `entities`, `context`, `content`, and operational metadata (`state`, `action`, `goal`, `preconditions`, `postconditions`) structured so the same document powers vector retrieval, graph workflows, deterministic agent planning, and human-in-the-loop plan critique — on one stable, backward-compatible backbone.

Because the format is human-readable Markdown + YAML, it also serves as **the first debuggable AI memory layer**: you can open it, search it with keyword / vector / entity graph, find errors, and fix them — turning AI memory from a black box into an inspectable artifact.

## Short repo description

Context-first Markdown → CtxFST world model: structured `<Chunk>` tags, canonical entities, JSON export, entity-graph building, deterministic agent loop with goal-aware + relation-aware routing, multi-step lookahead planning, relation-specific explanations, interactive plan critique, and debuggable memory loop for OpenClaw integration.

## One-paragraph project description

`ctxfst` is a structured document format that turns Markdown into a **semantic world model** for RAG and agents. It separates `entities`, `context`, and `content`, and lets entities represent both descriptive knowledge (skills, tools) and operational nodes (states, actions, goals) with `preconditions`/`postconditions`. A complete reference runtime is included: validate, export to JSON, build entity graphs with similarity and causal edges, then run a deterministic agent loop that uses BFS lookahead planning, Dijkstra-weighted goal-proximity routing (causal edges cost 1, similarity edges cost 3), and relation-specific explanations for every selection decision. The loop supports interactive plan critique — humans can accept, skip, force, or reset the plan before each execution step — making it a human-in-the-loop planning interface, not just a demo. The same structured format also enables a **debuggable memory loop**: export AI memory → convert to CtxFST → search with entity graph / vector / keyword to find errors → fix source-of-truth → reindex → AI behavior changes.

## Problem this solves

- Normal chunking loses the surrounding meaning of a passage.
- Context is usually buried in one opaque embedding string with no structure to inspect or update.
- Graph pipelines must re-extract noisy entities from raw text every time.
- Agent world models are usually ad-hoc Python dicts with no shared format, no causal edges, and no planning surface.
- Most agent selectors are LLM calls with no determinism, no explainability, and no human override.
- Teams need one format that works across authoring, validation, export, graph derivation, agent planning, and human review.
- **AI memory is a black box**: users spend hours training personal AI assistants (family preferences, work habits, communication patterns), but when the AI remembers something wrong, there is no way to see what it recorded, find the error, or fix it. The more you invest in training, the more painful a wrong memory becomes — and today most memory systems offer no observability and no repair path.

## Why this is different

- `ctxfst` stores `context` as structured metadata, not prepended text.
- `entities[]` gives you canonical graph nodes up front, including **operational types** (`state`, `action`, `goal`, `agent`, `evidence`).
- `chunks[].entities` and `chunks[].dependencies` create explicit chunk-to-entity and chunk-to-chunk edges.
- `preconditions` / `postconditions` on entities let the graph builder auto-infer causal edges (`REQUIRES`, `LEADS_TO`).
- **Relation-aware routing**: the skill selector runs Dijkstra with `REQUIRES`/`LEADS_TO` at weight 1, `SIMILAR` at weight 3, `COMPLETED`/`BLOCKED_BY` skipped — causal-path skills rank above semantically-similar ones.
- **Multi-step lookahead**: `find_plan()` runs BFS over the skill application graph to find the shortest sequence to the goal, replanning after every execution step.
- **Relation-specific explanations**: every selection decision names the edge relation that contributed to proximity, so you can audit why `skill-A` beat `skill-B`.
- **Interactive plan critique**: before each execution step, humans can `skip` a skill, `force` a different first step (precondition-checked), or `reset` constraints — the planner replans on every command.
- **Debuggable memory**: because the format is human-readable Markdown + YAML with canonical entities, AI memory becomes inspectable. Three search modes (FTS for exact facts, vector for semantic conflicts, entity graph for structural contradictions) let you pinpoint exactly which memory is wrong and why.
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

**OpenClaw memory debug demo (debuggable memory benchmark)** — OpenClaw SQLite memory → CtxFST → find and fix wrong memory → reindex → AI behavior changes:

```
# 1. AI remembers wrong: "小明 likes beef" (actually he doesn't eat beef)
openclaw "What should 小明 eat for dinner?"
→ AI recommends beef dishes ❌

# 2. Export memory, convert to CtxFST → entity:小明 + entity:牛肉 + pref:like
# 3. Three-way search finds the error:
#    FTS: locates the chunk containing "小明 likes beef"
#    Vector: no conflicting memory found (no "avoids beef" exists)
#    Graph: missing "avoid" edge — only "like" present
# 4. Fix source Markdown: "小明 does not eat beef (confirmed 2026-03)"
# 5. Delete index + rebuild:
rm ~/.openclaw/memory/main.sqlite*
openclaw memory index --force

# 6. Verify:
openclaw "What should 小明 eat for dinner?"
→ AI avoids beef dishes ✅
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

### Angle A: Developer (GraphRAG / Agent)

#### Title options

- `Show HN: ctxfst — Markdown → agent-ready world model with deterministic lookahead planning`
- `Show HN: ctxfst v2.1 — semantic world model format with relation-aware routing and human-in-the-loop plan critique`
- `ctxfst: one document format for RAG, graph pipelines, and deterministic agent planning (no LLM required)`

#### Post body

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

### Angle B: AI User (Debuggable Memory)

#### Title options

- `Show HN: ctxfst — Make AI memory debuggable: see what it remembers, find errors, fix them`
- `Show HN: Your AI assistant remembers things wrong and you can't fix it. ctxfst changes that.`
- `ctxfst: a structured format that turns black-box AI memory into something you can inspect and repair`

#### Post body

If you use a long-term memory AI assistant — for family coordination, personal notes, work habits — you've probably hit this wall: the AI remembers something wrong, and you can't fix it.

A friend put OpenClaw in a family group chat to track preferences, schedules, and meal planning. One day it recorded "小明 likes beef." Actually, he doesn't eat beef. From then on, every dinner suggestion included beef. My friend knew the answer was wrong but couldn't find *where* that memory lived or how to correct it.

This is not an edge case. In AI communities, the most common complaint about long-term memory isn't "it can't find things" — it's "it remembers wrong things and I have no way to fix them." People spend hours training their AI, and the more they invest, the more painful a wrong memory becomes.

`ctxfst` is a structured document format (Markdown + YAML) that makes AI memory inspectable and repairable. The idea:

1. **Export** AI memory (e.g., from OpenClaw's SQLite) into CtxFST format — each memory becomes a chunk with canonical entities and structured context
2. **Search with three methods** to find errors:
   - FTS / keyword: find the exact chunk that says "likes beef"
   - Vector / semantic: find memories that semantically conflict ("likes beef" vs "avoids red meat")
   - Entity graph: find structural contradictions (entity:小明 connected to both "like" and "avoid" for entity:beef)
3. **Fix the source** — edit the Markdown, not just argue with the chatbot
4. **Reindex** — the AI's next response uses the corrected memory

The key difference from just "editing a text file" is that CtxFST gives you *structured search across your AI's entire memory*. You go from "something feels wrong" to "this specific chunk, about this entity, recorded on this date, contradicts this other memory" — and then you fix it.

The same format also powers a full deterministic agent runtime (entity graphs, BFS planning, Dijkstra routing, human-in-the-loop critique) — but the memory debugging use case is where most non-developer users feel the pain first.

Would love to hear from anyone using OpenClaw, MemGPT, or any long-term memory system: how do you handle wrong memories today?

---

## Reddit

### Angle A: Developer

#### Subreddits: r/MachineLearning, r/LangChain, r/LocalLLaMA

#### Title

`ctxfst v2.1: Markdown → deterministic agent world model with lookahead planning and human-in-the-loop critique (no LLM needed)`

#### Post

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

### Angle B: AI User (Debuggable Memory)

#### Subreddits: r/OpenClaw, r/ChatGPT, r/LocalLLaMA, r/selfhosted, r/artificial

#### Title

`Your AI remembers things wrong and you can't fix it. I built a format that makes AI memory inspectable and repairable.`

#### Post

How many of you have hit this: you spend weeks training your AI assistant on your preferences, family info, work habits — and then it remembers something wrong, and there's no way to correct it?

A friend uses OpenClaw in a family group chat. The AI recorded "小明 likes beef" — but 小明 doesn't eat beef. Every dinner suggestion after that included beef. He knew it was wrong but couldn't find where the AI stored that belief or how to change it.

I've heard this complaint from dozens of people in AI communities. The pain isn't "AI can't find information." The pain is "AI remembers wrong information and I can't see what it remembers, can't search for contradictions, and can't fix the source."

I built `ctxfst`, a structured document format (Markdown + YAML) designed to make AI memory debuggable:

**The loop:**
1. Export memory from your AI system (e.g., OpenClaw SQLite) into CtxFST
2. Each memory becomes a chunk with named entities and structured context — you can *read* it
3. Search three ways: keyword (find "beef"), vector (find semantic conflicts), entity graph (find contradictions in relationships)
4. Fix the source Markdown
5. Reindex → AI behavior changes

The point isn't "edit a text file." The point is you can go from "something feels off" to "this specific memory, about this person, recorded on this date, says the opposite of what's true" — and then fix it at the source.

You don't need to understand the format to find problems. It's like looking at code when you're not a developer — you don't need to write it, but when you see `entity:小明` connected to `pref: like` and `entity:beef`, you know that's wrong.

Currently works with OpenClaw. The same format also powers a full agent runtime (entity graphs, deterministic planning, human-in-the-loop critique) for developers who want the deeper capabilities.

For anyone using OpenClaw, MemGPT, Khoj, or any long-term memory system: how do you deal with wrong memories today? Curious if this resonates.

---

## Discord showcase

### Angle A: Developer

Built an open-source reference runtime for `ctxfst` — a semantic world model document format for RAG and agents. The new release closes the full planning loop: BFS lookahead planning, relation-aware Dijkstra routing (causal edges cost 1, similarity edges cost 3), relation-specific explanations that name *why* a skill was chosen, and interactive plan critique where humans can skip skills, force alternatives, or reset constraints before each execution step. No LLM in the planning loop — fully deterministic, 66 end-to-end tests. Works with LanceDB, Lance Graph, HelixDB, LightRAG, HippoRAG. Demo goes from 1 Markdown file → chunks → entity graph → agent loop reaching goal with full explanation trace.

### Angle B: AI User

Your AI assistant remembers things wrong and you can't fix it — sound familiar? `ctxfst` is a structured format that makes AI memory inspectable and repairable. Export memory from OpenClaw → convert to human-readable entities + chunks → search with keyword / vector / entity graph to find exactly what's wrong → fix the source → reindex → AI behavior changes. Three search modes catch different types of errors: FTS finds wrong facts, vector search finds semantic contradictions, entity graph finds broken relationships. Demo: AI records "小明 likes beef" (wrong) → export → CtxFST shows `entity:小明 + pref:like + entity:beef` → fix to "doesn't eat beef" → reindex → AI stops recommending beef. Works with OpenClaw today.

---

## X thread

### Angle A: Developer

#### Post 1

Most agent planners are LLM calls wrapped in a loop.

`ctxfst` ships a deterministic agent runtime built on structured document fields:
- `preconditions` / `postconditions` in YAML frontmatter
- causal edge inference from the entity graph
- BFS lookahead that finds the shortest skill path to goal

No LLM needed in the planning loop.

#### Post 2

The routing is relation-aware.

`REQUIRES`/`LEADS_TO` edges cost 1.
`SIMILAR` edges cost 3.
`COMPLETED`/`BLOCKED_BY` are skipped entirely.

Dijkstra picks the causal path to goal, not the nearest semantic neighbor.

Every selection names the edge relation that drove the decision.

#### Post 3

The planner also explains itself.

Before each execution step you see:

```
Best plan (3 steps): analyze-resume → match-skills → generate-plan
  Step 1: analyze-resume
    pre  ✓  entity:has-raw-resume
    post +  entity:has-parsed-resume  ← via REQUIRES (weight 1)
```

And the alternatives it considered — with reasons why they lost.

#### Post 4

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

#### Post 5

The full runtime is in one repo:

- format spec + JSON Schema (v2.0)
- export pipeline → `chunks.json` + `entity-graph.json`
- deterministic agent loop with 66 end-to-end tests
- works with LanceDB, HelixDB, LightRAG, HippoRAG

If you are building GraphRAG or agent workflows, what is the right abstraction boundary for world models?

### Angle B: AI User (Debuggable Memory)

#### Post 1

Your AI assistant remembers things wrong.

You spent hours teaching it your family's preferences. Then it recorded one thing incorrectly, and now every recommendation is off.

You know it's wrong. But you can't see what it remembers. You can't search for the error. You can't fix the source.

This is the #1 complaint in every AI memory community I've been in.

#### Post 2

The problem isn't "AI can't find information."

The problem is: AI memory is a black box.

- No way to see what it recorded
- No way to search for contradictions
- No way to fix the source

You can tell it "that's wrong" in chat. It apologizes. Next conversation, same mistake.

#### Post 3

I built `ctxfst` to make AI memory debuggable.

Export → convert to structured entities + chunks → search three ways:

- Keyword: find the exact wrong fact
- Vector: find semantic contradictions
- Entity graph: find broken relationships

Go from "something feels off" to "this specific memory is wrong" → fix it → AI behavior changes.

#### Post 4

Real example:

AI records "小明 likes beef." Actually, he doesn't eat beef.

Export → CtxFST shows:
```
entity:小明 → pref:like → entity:beef
```

You see the error immediately. Fix source → reindex → AI stops recommending beef.

You don't need to write code. You just need to *see* the memory.

#### Post 5

`ctxfst` is open source. Works with OpenClaw today.

The same format also powers a full agent runtime — entity graphs, deterministic planning, human-in-the-loop critique — for developers who want the deeper layer.

But the entry point for most people is simpler:

Your AI remembers things wrong. Now you can see why, and fix it.

---

## Coming soon (teaser)

### Completed

- **CH22: Retrieval benchmark** — entity-aware retrieval vs pure text similarity, with measurable results
- **CH23: Debuggable memory loop** — full five-step demo: OpenClaw memory export → CtxFST → three-way search → fix → reindex → AI behavior changes

### Next chapters

- **CH24: Export / import CLI** — `ctxfst export` and `ctxfst import` commands for OpenClaw memory
- **CH25: Relation-aware memory repair** — using entity graph edges to automatically suggest which memories conflict
- **CH26: Memory diff, conflict, and provenance** — version tracking, conflict resolution policy, and "who changed what when"

### Integration examples

Walkthroughs showing `ctxfst` wired into:
- **LanceDB** — vector search over `chunks.json` with entity filtering
- **Lance Graph** — entity-graph traversal with `REQUIRES`/`LEADS_TO` edges
- **HelixDB** — hybrid vector + graph queries on the same entity catalog
- **LightRAG / HippoRAG** — drop-in replacement for their entity extraction layer

### `ctxc` compiler (upcoming)

A CLI tool that takes raw Markdown notes and automatically produces a valid CtxFST document — handling chunking, entity extraction, normalization, and frontmatter generation without manual tagging. Lowers the authoring barrier from "know the format" to "just write Markdown."

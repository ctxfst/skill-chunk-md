# CtxFST Specification (v3.0)

CtxFST links notes to **recurring problem shapes**. The graph has two kinds of nodes, notes (or chunks) and shape cards, and one kind of edge: *this note is another instance of this card's problem shape*. Edges are confirmed by a person. Each confirmation or rejection sharpens the card for the next run.

v3.0 removes the entity layer (`entities[]`, entity graph, world state, agent loop). The previous version is kept on the `legacy-entity-graph` branch.

---

## 1. Why

The design comes from controlled comparisons: 72 personal notes, 4 hand-verified recurring themes, Voyage embeddings, and GLM-5.3-Flash as the judge. The main measure is per-card ranking AUC, computed leave-one-out: how often a card ranks its own members above other notes (0.5 = chance).

| Method | Mean card AUC |
|---|---:|
| Nearest confirmed instance (embedding) | 0.682 |
| Card probe, confirmed instances only | 0.744 |
| LLM judge against the card + instance examples | 0.780 |
| Card probe + judge | 0.830 |
| Card probe with reviewed rejections | 0.834 |
| **Card probe with reviewed rejections + judge** | **0.866** |

Reviewed rejections are simulated: the 20 non-members nearest each card's instances. Note text is embedded without generated footers (see `build --cut-at`). An earlier run that left footers with topic labels in the text scored higher (0.883 for the probe with rejections), because the labels leaked topic information. Strip anything generated from the notes before embedding.

Methods that tried to *describe* notes in a comparable form all failed, because "the same problem" is the reader's judgment and is not a field in the note:

| Description method | Result |
|---|---|
| Entity overlap (v2) | 0.51 pair AUC, i.e. chance. When a problem recurs, its tools and objects have changed. |
| Four-slot structure (actor / action / obstacle / outcome) | Below raw text (0.629 vs 0.656 pair AUC); averaging both gained only 0.006, and its LLM judging was at chance |
| One-sentence structure summaries | Worse than raw text |
| LLM note↔note "same structure?" judging, no card | Accept precision 18%, equal to the base rate |

What works is supervision: a card with examples, plus the reviewer's rejections. Caveats:
- The sample is small.
- The cards were written after reading their members, so absolute numbers are optimistic. Compare methods relative to each other, not by their absolute values.

---

## 2. Objects

### Unit
A unit is a note file, or one chunk of it when the note has `%% chunk-start %%` markers ([chunk-syntax.md](chunk-syntax.md)). Unit IDs are relative paths without `.md`, plus `#chunk-id` for a chunk. Plain Markdown is a valid input. The unit text starts with the note title (`# title`), because some notes are a title and nothing else. Notes with less than 20 characters of body (`link --min-body`), such as link-only clippings, are never proposed as candidates, but they can still be confirmed instances.

Prefer whole notes or sections over small chunks. A shape needs the whole story: who wanted what, what blocked it, and what happened.

### Shape card
A hand-written Markdown file ([shape-cards.md](shape-cards.md)) with:
- the problem shape
- the core tension
- near misses
- triggers
- an **instance table** of confirmed notes
- a **rejected** list of notes a reviewer turned down

The card is the single source of truth for both. The tool appends to these two sections only when the reviewer runs `review`.

### Probe
A probe is one direction per card in embedding space: `mean(instances) − 0.5 · mean(rejected)`, i.e. Rocchio relevance feedback. A card with no instances yet uses the embedding of its own text. Scoring a whole corpus is one matrix–vector product.

### Shape link
A `(card, unit)` candidate in `links.json` has:
- the probe score
- an optional judge verdict (`accept` / `borderline` / `reject`) and the roles that did not match
- `known` (`instance`, `rejected`, or null)

---

## 3. Linking

For each card:
1. **Probe.** Score every unit. Drop known instances and rejected units, and keep the top *k*.
2. **Judge (optional).** Units are judged in batches of 8 against the card text and its instance table. Rows for units in the current batch are hidden, so a unit is never judged against itself. It adds about 0.03–0.09 mean card AUC both before and after rejections (0.744 → 0.830 and 0.834 → 0.866). `--no-judge` skips the LLM when cost matters more than the last few points.
3. **Review.** `review.md` lists candidates: accepted first, then by probe score. The reviewer marks `[x]` (confirm) or `[-]` (reject). `review` then appends confirmed notes to the instance table (with empty description columns for the reviewer to fill) and rejected notes to the rejected section.

The judge is a filter, not an edge writer. Its accept precision was 53–58%.

---

## 4. Files

`scripts/shape_layer.py` writes the following files into the index directory:

| File | Content |
|---|---|
| `units.json` | `{unit_id: {text, body_chars}}`: `# title` plus the first 1,200 characters, shown to the judge; body length without title or links |
| `vectors.npz` | `ids`, `raw` (L2-normalized embeddings of the first 4,000 characters) |
| `links.json` | `[{card, unit, verdict, mismatch, probe, known}]` |
| `review.md` | checklist per card (`<!-- card: id -->` marks each section) |
| `cache/` | embedding and judge caches, keyed by content hash |

`scripts/export_to_lancedb.py` still exports chunk records (`id`, `context`, `content`, `tags`, optional temporal fields) for vector databases; see [`schema.json`](../schema.json).

---

## 5. Evaluation

`shape_layer.py eval INDEX --cards CARDS --gold gold.json [--simulate-review N]`

- `gold.json` maps `{unit_id: [card_id, ...]}`. Units absent from it count as distractors.
- For each card, the command reports leave-one-out AUC for four rankings: nearest instance, probe, judge (from `links.json`), and judge + probe. It also reports judge accept precision and recall, and the number of gold units accepted into a wrong card.
- `--simulate-review N` treats the N non-gold units nearest a card's instances as rejected. This approximates a card that has been through review.
- Run `link --all` first to get judge columns.

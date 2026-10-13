# skill-chunk-md

> **Find the notes where you hit the same problem before, even when everything on the surface has changed.**

`skill-chunk-md` is the reference implementation of CtxFST v3. It links Markdown notes to **shape cards**. A shape card is a hand-written description of a problem that keeps coming back in different years, with different objects and different tools.

```
note ──is another instance of──▶ shape card
```

That is the whole graph: no entities, and no note↔note edges. You confirm every edge, and every confirmation or rejection sharpens the card.

## Why not chunks + entities (or any extracted structure)

We tested on 72 personal notes with 4 hand-verified recurring themes. The score is per-card ranking AUC, leave-one-out: how often a card ranks its own notes above other notes (0.5 = chance).

| Method | Mean card AUC |
|---|---:|
| Nearest confirmed note (embedding) | 0.682 |
| LLM judge against the card + examples | 0.780 |
| Card probe with your rejections | 0.834 |
| **Card probe with your rejections + LLM judge** | **0.866** |

Methods that try to describe notes in a comparable form all failed:
- **Entity overlap (v2)**: 0.51 pair AUC, which is chance. When a problem returns years later, its tools and objects have changed.
- **Four-slot structure** (actor / action / obstacle / outcome): did not beat plain text embeddings.
- **LLM note↔note "same structure?" judging**: precision equal to the base rate.

"The same problem" is your judgment, not a field in the note, so the index has to learn it from you. Details are in [references/ctxfst-spec.md](references/ctxfst-spec.md). The v2 code (entity graph, world state, agent loop) is on the `legacy-entity-graph` branch.

## How it works

1. **build**: embed every note (or chunk). No LLM.
2. **link**: each card is a *probe*, the mean of its confirmed notes minus half the mean of its rejected ones. It ranks the whole index in one matrix product.
   - The top candidates go to an optional LLM judge, which compares them with the card and its past instances.
   - `--no-judge` skips the LLM; the probe alone with rejections loses about 0.03 AUC.
3. **review**: mark lines in `review.md` with `[x]` (confirm) or `[-]` (reject), then run `review`.
   - Confirmed notes join the card's instance table.
   - Rejected notes join its rejected list.
   - The next `link` uses both.

## Quickstart

```bash
pip install numpy pyyaml

cat > .env <<'END'
CTXFST_EMBED_KEY=…                          # Voyage by default
CTXFST_LLM_URL=https://…/chat/completions   # judge only; any OpenAI-compatible endpoint
CTXFST_LLM_MODEL=…
CTXFST_LLM_KEY=…
END

python3 scripts/shape_layer.py --env .env build ~/notes --out index --exclude 'private/*'
python3 scripts/shape_layer.py --env .env link index --cards ~/notes/shapes
# mark index/review.md with [x] / [-]
python3 scripts/shape_layer.py review index --cards ~/notes/shapes
python3 scripts/shape_layer.py --env .env link index --cards ~/notes/shapes --no-judge
```

Note text is sent to the configured APIs. Anything matching `--exclude` is never read. If your notes carry generated footers (related links, auto summaries), cut them with `--cut-at REGEX`: they leak topic labels into the embeddings.

## Shape cards

```markdown
# Someone without scale borrows a capability only organizations had

## Problem shape
## Core tension
## Near misses          ← look-alikes that are not this shape
## Triggers
## Instances            ← confirmed notes: examples + probe positives
| Year | Note | Object that time | Means that time |
|---|---|---|---|
| 2012-05 | [[journal/2012-05-team-wiki]] | a 5-person team | shared wiki pages |
## Rejected             ← probe negatives
- [[work/2021-crm-comparison]]
```

Chinese headings (`問題形狀`, `核心張力`, `最像但不同的線`, `觸發條件`, `化身清單`, `退回`) work too. See [references/shape-cards.md](references/shape-cards.md).

## Measuring changes

```bash
python3 scripts/shape_layer.py --env .env link index --cards shapes --all
python3 scripts/shape_layer.py eval index --cards shapes --gold gold.json --simulate-review 20
```

`gold.json` maps `{unit_id: [card_id, ...]}`. `eval` reports:
- Per-card leave-one-out AUC for four rankings: nearest note, probe, judge, and judge + probe.
- Judge precision and recall.
- Gold notes accepted into the wrong card.

`--simulate-review N` treats the N non-gold notes nearest each card as rejected, which approximates a card that has been reviewed.

## Chunk markers

A long note can be split with Obsidian-compatible markers. Each chunk then becomes its own unit (`path#chunk-id`). For shapes, prefer whole notes or sections, because a shape needs the whole story.

```markdown
%% chunk-start id="work:migration-2014" %%
…
%% chunk-end %%
```

| Script | Purpose |
|---|---|
| `scripts/validate_chunks.py` | check marker syntax and frontmatter |
| `scripts/export_to_lancedb.py` | export chunk records for vector databases ([schema.json](schema.json)) |
| `scripts/contextualize_chunks.py` | write `context` fields with Claude |

## Files

| Path | Content |
|---|---|
| `SKILL.md` | instructions for the agent |
| `scripts/shape_layer.py` | build, similar, link, review, eval |
| `tests/test_shape_layer.py` | offline tests |
| `references/ctxfst-spec.md` | v3 spec, probe, file formats, evidence |
| `references/shape-cards.md` | card format and writing guide |
| `references/chunk-syntax.md`, `references/semantic-chunking.md` | chunk markers |

## License

MIT. Maintained by [ctxfst](https://github.com/ctxfst).

---
name: skill-chunk-md
description: "Link Markdown notes to recurring problem shapes (CtxFST v3). Use when building a knowledge base that should surface 'the same kind of problem I had years ago' instead of 'notes about the same topic': writing shape cards, building the embedding index, ranking notes with a card's probe, judging candidates against a card, reviewing and feeding back confirmations and rejections, evaluating against a gold set, or adding %% chunk-start %% / %% chunk-end %% markers to split long notes."
---

# Skill Chunk MD

CtxFST v3 links notes to **shape cards**. A shape card is a hand-written description of a problem that keeps coming back with different objects and tools. The only edge is *note → card*, and a person confirms every edge.

Each card works as a probe in embedding space: the mean of its confirmed notes minus half the mean of its rejected notes. Every review makes the probe sharper.

There are no entities, no extracted structure, and no note↔note edges. Methods that try to describe notes in a comparable form (entities, four-slot structure, structure summaries) find the same *topic*, not the same *problem*. Supervision from the reviewer is what worked. The evidence is in [references/ctxfst-spec.md](references/ctxfst-spec.md).

## When to use which step

| The user wants to… | Do |
|---|---|
| Find notes with the same problem shape as a known pattern | Check the card, then `build`, `link`, and `review` |
| Turn a recurring pattern they noticed into a card | Write a card ([references/shape-cards.md](references/shape-cards.md)) |
| Find notes similar to one note | `build`, then `similar` (plain embedding similarity, i.e. same topic) |
| Measure whether a change helped | `link --all`, then `eval` with a gold file |
| Split a long note into passages | Add chunk markers ([references/chunk-syntax.md](references/chunk-syntax.md)) |

## Workflow

### 1. Configure

Set the `CTXFST_*` variables, or put them in a file and pass it with `--env`:

```
CTXFST_EMBED_KEY=…                  # Voyage by default; CTXFST_EMBED_URL / _MODEL to change
CTXFST_LLM_URL=…/chat/completions   # judge only; any OpenAI-compatible endpoint
CTXFST_LLM_MODEL=…
CTXFST_LLM_KEY=…
```

Note text is sent to these APIs. Ask the user which folders are private, and pass those with `--exclude`.

### 2. Build the index

```bash
python3 scripts/shape_layer.py --env .env build NOTES_DIR --out INDEX --exclude 'private/*'
```

This step only computes embeddings, with no LLM. If the notes carry generated blocks (related-note lists, auto summaries, tags added by other tools), pass `--cut-at REGEX` to truncate each note at the first matching line. Generated topic labels leak into the embeddings and inflate results. Results are cached by content hash, so a rebuild only embeds notes that changed.

### 3. Write shape cards

Cards come from the person, not the model. A card needs:
- **Problem shape**: the roles, not the topic.
- **Core tension**.
- **Near misses**: look-alikes that are not this shape, and how to tell them apart.
- **Triggers**.
- **Instance table**: confirmed examples with a wikilink each.
- **Rejected list**: filled in by `review`.

Help the user phrase the card, but do not invent instances or motives.

### 4. Link

```bash
python3 scripts/shape_layer.py --env .env link INDEX --cards CARDS_DIR --top 40
```

- The card's probe ranks every unit, and the top 40 new ones become candidates.
- By default an LLM judges each candidate against the card, with instance rows as examples. A unit's own row is hidden from it.
- `--no-judge` skips the LLM. It costs about 0.03 mean card AUC once a card has rejections, and about 0.09 before.
- Output goes to `INDEX/review.md` and `INDEX/links.json`.

### 5. Review

The user marks each line in `review.md` with `[x]` (confirm) or `[-]` (reject), then:

```bash
python3 scripts/shape_layer.py review INDEX --cards CARDS_DIR
```

- Confirmed notes are appended to the card's instance table with the description columns empty. Ask the user to fill them in, because those columns are what the judge learns from.
- Rejected notes go to the card's rejected list.
- Run `link` again afterwards.

Encourage rejecting. Rejections are the cheapest signal, and the biggest gain measured (mean card AUC 0.744 → 0.834 for the probe alone). The judge's precision is about 55%, so present its verdicts as a reading order, not as conclusions. If one card keeps pulling in wrong notes, suggest splitting it.

## Rules

- Never write note↔note edges, and never use an LLM to judge two notes against each other. Without a card as an anchor, that judge's precision equaled the base rate.
- Do not extract structure (entities, slots, summaries) to match on. Every such method tested lost to plain text embeddings.
- Only the person confirms or rejects. The judge's verdicts are candidates.

## Chunk markers (optional)

Long notes that mix several problems can be split:

```markdown
%% chunk-start id="work:migration-2014" %%
…passage…
%% chunk-end %%
```

- Chunk IDs use the form `category:kebab-topic`.
- Frontmatter `chunks:` entries (`id`, `context`, `tags`, `created_at`) are optional metadata.
- `scripts/validate_chunks.py` checks marker syntax.
- `scripts/export_to_lancedb.py` exports chunk records.
- `scripts/contextualize_chunks.py` writes `context` fields with Claude.
- More detail: [references/chunk-syntax.md](references/chunk-syntax.md) and [references/semantic-chunking.md](references/semantic-chunking.md).

## Resources

- `scripts/shape_layer.py`: build, similar, link, review, eval
- `references/ctxfst-spec.md`: v3 spec, probe, file formats, evidence
- `references/shape-cards.md`: card format and writing guide
- `references/chunk-syntax.md`, `references/semantic-chunking.md`: chunk markers

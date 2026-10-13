# Shape Cards

A shape card describes a problem that keeps coming back in different years, with different objects. It is the anchor the judge compares notes against. Card quality decides link quality: in testing, one card that was written too broadly accepted 9 wrong notes for every right one, even with examples.

One card per file, in a cards directory. The filename stem is the card ID.

## Sections

The parser accepts either the Chinese or the English heading. A section is matched by its heading prefix, so `## 最像但不同的線（判別欄）` works.

| Heading | Alias | Given to judge | Content |
|---|---|---|---|
| `# <title>` | | yes | One sentence naming the shape |
| `## 問題形狀` | `## Problem shape` | yes | The roles: who acts, on what, wanting what, blocked by what |
| `## 核心張力` | `## Core tension` | yes | The two pulls that make it recur |
| `## 最像但不同的線` | `## Near misses` | yes | Shapes that look alike but are not this one, and how to tell them apart |
| `## 觸發條件` | `## Triggers` | yes | When it tends to show up |
| `## 化身清單` | `## Instances` | yes, as examples | Table of confirmed instances (below); also the probe's positives |
| `## 退回` | `## Rejected` | no | `- [[note]]` list of notes a reviewer turned down; the probe's negatives |

Any other section (evidence, history, notes) is ignored.

## Instance table

```markdown
## 化身清單

| Year | Note | Object that time | Means that time |
|---|---|---|---|
| 2012-05 | [[journal/2012-05-team-wiki]] | a 5-person team | shared wiki pages |
| 2019-11 | [[work/meeting-notes-search]] | meeting notes | tags + full-text search |
```

- Each row needs one `[[wikilink]]` to the note. The link resolves against unit IDs by full path first, then by basename.
- The other columns are free-form. They are what makes the examples useful. The column that varies between instances (the object, the means) teaches the judge what may change while the shape stays the same.
- When judging a batch, the judge never sees the rows of the notes in that batch.
- `shape_layer.py review` appends confirmed notes as rows with only the link filled in. Fill in the other columns afterwards: a row without them still trains the probe but teaches the judge little.

## Rejected list

```markdown
## 退回

- [[work/2021-crm-comparison]]
```

Rejections are the cheapest signal you have. In testing, adding the notes a reviewer would have rejected raised mean card AUC from 0.744 to 0.834, about as much as adding the LLM judge. Reject freely; you can delete a line later if you change your mind.

## Writing a good card

- Name roles, not topics. "Someone without scale borrows a capability only organizations had" is a shape. "AI in education" is a topic, and the judge will match on the topic.
- Fill in the near-miss section. It is the judge's main defense against same-topic, different-shape notes.
- Keep at least 5 instances that differ in object and era. With only same-era, same-topic examples, the judge learns the topic.
- If a card keeps accepting wrong notes, it is probably two shapes. Split it.
- A new card with no instances is ranked by its own text, which mostly finds the topic. Confirm two or three instances in the first review and the probe takes over.

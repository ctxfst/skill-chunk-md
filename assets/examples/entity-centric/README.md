# Entity-Centric Mode Example

This directory demonstrates the **Entity-Centric convention** for CtxFST: **one file = one entity**.

Each `entity-<id-suffix>.ctxfst.md` file is a self-contained dossier on a single entity:

- Its `entities:` frontmatter array holds exactly one entry — the **owner**.
- All chunks are observations about that owner.
- Chunks may reference other entities by ID; those entities live in their own files.

## Why this layout

Standard CtxFST (many entities + many chunks per file) is great for **note-shaped** documents such as a single long profile or a benchmark document. The entity-centric convention is better when you want:

- **Debuggability** — open one file, see everything you know about one entity.
- **Incremental append** — a new observation updates exactly one file.
- **1:1 mapping to a graph node** — filesystem layout becomes the node index; `relations.json`-style edges live elsewhere.

Typical use cases: memory systems, knowledge bases that grow over time, agents that need a stable per-entity file to point at.

## Files in this example

| File | Owner entity | Cross-refs |
|------|--------------|-----------|
| [`entity-python.ctxfst.md`](./entity-python.ctxfst.md) | `entity:python` | `entity:fastapi` |
| [`entity-fastapi.ctxfst.md`](./entity-fastapi.ctxfst.md) | `entity:fastapi` | `entity:python`, `entity:docker` |
| [`entity-docker.ctxfst.md`](./entity-docker.ctxfst.md) | `entity:docker` | `entity:fastapi` |

## Naming convention

```
entity-<id-suffix>.ctxfst.md
```

Where `id-suffix` is the part after `entity:`. For example, `entity:fastapi` → `entity-fastapi.ctxfst.md`.

## Validating

Validate each file individually:

```bash
python3 scripts/validate_chunks.py assets/examples/entity-centric/entity-python.ctxfst.md --entity-centric
```

Or validate the whole directory with cross-file entity resolution:

```bash
python3 scripts/validate_chunks.py assets/examples/entity-centric/ --entity-centric --entity-registry assets/examples/entity-centric/
```

The `--entity-centric` flag enforces:

1. `entities:` contains exactly one entity.
2. The filename matches the owner entity (`entity-<id-suffix>.ctxfst.md`).
3. Every chunk's `entities:` list includes the owner.

The `--entity-registry <dir>` flag (optional) resolves cross-file entity references by scanning every `entity-*.ctxfst.md` file in the given directory. Without it, references to external entities are warned on but not errored.

## Relationship to standard CtxFST

This convention does **not** change the CtxFST schema. An entity-centric file is still a valid CtxFST document — it simply has `len(entities) == 1`. The same validation, export, and graph-building tools all work; they just operate on one entity per file rather than many.

You can mix both styles in the same project.

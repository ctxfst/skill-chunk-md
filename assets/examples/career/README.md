# Career Demo

This demo packages the full `ctxfst` flow around a professional profile:

1. Raw Markdown resume-style notes
2. Converted `ctxfst` document with `entities[]` and `chunks[]`
3. Exported `chunks.json`
4. Derived `entity-profiles.json`
5. Derived `entity-graph.json`

## Files

- `profile.md` - plain Markdown input
- `profile.ctxfst.md` - converted CtxFST document
- `chunks.json` - exported structured payload
- `entity-profiles.json` - derived entity profiles for embedding or graph pipelines
- `entity-graph.json` - downstream `Entity -> Entity` similarity graph

## Run it yourself

From `skill-chunk-md/`:

```bash
python3 scripts/validate_chunks.py assets/examples/career/profile.ctxfst.md
python3 scripts/export_to_lancedb.py assets/examples/career/profile.ctxfst.md --output assets/examples/career/chunks.json --pretty
python3 scripts/build_entity_profiles.py assets/examples/career/chunks.json --output assets/examples/career/entity-profiles.json
python3 scripts/build_entity_graph.py assets/examples/career/entity-profiles.json --output assets/examples/career/entity-graph.json
```

## What this demo shows

- `Python`, `FastAPI`, `Pandas`, and `Go` become canonical entities
- project and skill sections become chunk records with clean metadata
- chunk-to-entity links stay in the `ctxfst` document
- entity profiles are derived later as a pipeline layer
- entity-to-entity similarity edges are derived after that by the graph builder

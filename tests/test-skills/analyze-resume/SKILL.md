---
name: analyze-resume
description: "Parse raw resume and extract skill evidence"
preconditions:
  - "entity:has-raw-resume"
  - "NOT entity:has-parsed-resume"
postconditions:
  - "entity:has-parsed-resume"
  - "entity:has-skill-inventory"
related_skills:
  - "match-skills"
cost: low
idempotent: true
---

# Analyze Resume

Parse a raw resume document, extract structured skill evidence, and produce a skill inventory.

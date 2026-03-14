---
name: match-skills
description: "Match extracted skills against target career path"
preconditions:
  - "entity:has-skill-inventory"
postconditions:
  - "entity:has-skill-gap-analysis"
related_skills:
  - "generate-plan"
cost: medium
idempotent: false
---

# Match Skills

Compare the skill inventory against a target career path and produce a gap analysis.

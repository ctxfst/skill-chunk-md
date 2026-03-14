---
name: generate-plan
description: "Generate a personalized learning plan to close skill gaps"
preconditions:
  - "entity:has-skill-gap-analysis"
postconditions:
  - "entity:learn-kubernetes-path"
related_skills: []
cost: high
idempotent: false
---

# Generate Plan

Create a step-by-step learning plan that addresses identified skill gaps for the target path.

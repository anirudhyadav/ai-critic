---
mode: dockerfile_review
focus: Dockerfile security and best practices
strictness: high
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm each finding is a real problem, not intentional (e.g. root user in a scratch container)
- Look for additional issues the analyst missed: layer ordering inefficiencies, cache-busting problems
- Check build argument handling — ARG values before FROM are not available in later stages unless re-declared
- Look for missing LABEL metadata (maintainer, version)

## Disagreement Standard
Disagree if the finding applies only to development images explicitly labelled as such.

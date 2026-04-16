---
mode: pr_review
focus: pull request review
strictness: medium
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm any regression risk the analyst flagged
- Look for integration issues: does the change interact with other parts of the system in ways not covered by the diff?
- Check whether the test coverage added (if any) actually exercises the new logic

## Disagreement Standard
If the analyst flagged a false positive (the change is safe), disagree with a one-line reason.

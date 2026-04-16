---
mode: test_quality
focus: test quality
strictness: medium
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm any meaningless assertion the analyst flagged — check if there is compensating logic elsewhere
- Look for missing test scenarios the analyst did not mention
- Check if the overall test suite has any structural gaps (e.g. no integration tests at all)

## Disagreement Standard
If a test looks weak but does cover a real path adequately, downgrade the risk rather than disagreeing outright.

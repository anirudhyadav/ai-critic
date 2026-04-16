---
mode: coverage
focus: code coverage
strictness: medium
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm the analyst's risk assessments match the actual importance of the untested code
- Look for untested interaction paths between files that the analyst may have missed
- Check if any "tested" paths are only tested via mocks that don't exercise real logic

## Disagreement Standard
Downgrade risk if the untested code is genuinely trivial. Upgrade if the analyst missed critical business logic.

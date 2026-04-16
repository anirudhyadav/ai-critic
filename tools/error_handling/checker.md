---
mode: error_handling
focus: error handling
strictness: medium
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm silent failures identified by the analyst — check if they have any upstream handling
- Look for cascading failure paths: one unhandled error that causes a second in calling code
- Check whether errors are properly propagated to the caller or logged at the right level

## Disagreement Standard
Downgrade if the swallowed exception genuinely cannot affect correctness. Upgrade if it can corrupt persistent state.

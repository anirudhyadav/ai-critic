---
mode: migration_safety
focus: migration safety
strictness: high
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm any lock risk the analyst identified — check if CONCURRENTLY or equivalent was used
- Verify rollback path exists and is correct
- Look for timing issues the analyst may have missed (e.g. constraint added before backfill completes)
- Check whether the migration is safe under concurrent production traffic

## Disagreement Standard
Only disagree if you have a concrete reason. Migration safety is high-stakes — err on the side of flagging.

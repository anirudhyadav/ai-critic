---
mode: dependency_audit
focus: dependency audit
strictness: medium
min_risk: low
model: claude-3-5-sonnet
---

## What to Verify
- Confirm any CVE the analyst cited — check if the vulnerability affects the usage pattern in this project
- Look for transitive dependency risks the analyst may not have flagged explicitly
- Check whether any unpinned package could introduce a known-bad version on next install

## Disagreement Standard
If a CVE is in a code path this project does not use, downgrade the risk with a note.

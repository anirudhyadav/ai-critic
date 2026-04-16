---
mode: secrets_scan
focus: secrets and credentials
strictness: high
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm each finding is a real secret, not a placeholder or test value
- Look for indirect leaks the analyst missed: secrets logged, returned in API responses, or written to temp files
- Check if any secrets are also present in comments or git history references

## Disagreement Standard
If a finding looks like a test credential, disagree with reasoning. Otherwise confirm.

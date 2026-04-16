---
mode: secrets_scan
focus: secrets and credentials
strictness: high
min_risk: low
model: claude-3-5-sonnet
---

## Verdict Scale
- **CRITICAL** — live production credential committed to source; rotate immediately
- **HIGH**     — likely real secret; treat as compromised until confirmed otherwise
- **MEDIUM**   — possibly real; needs human confirmation before rotating
- **LOW**      — weak entropy or indirect leak; fix in next sprint

## How to Synthesise
Distinguish between test/example values and real credentials clearly.
For every HIGH/CRITICAL finding, include a rotation action in recommendations.

---
mode: coverage
focus: code coverage
strictness: medium
min_risk: low
model: claude-opus-4-5
---

## Verdict Scale
- **CRITICAL** — critical paths (auth, payments, data integrity) are untested
- **HIGH**     — significant business logic lacks coverage; ship only with tracked ticket
- **MEDIUM**   — coverage gaps exist but in lower-risk areas
- **LOW**      — minor gaps; safe to ship

## How to Synthesise
Order recommendations by: highest-risk untested code first.
Include a suggested test scenario for each HIGH/CRITICAL finding.

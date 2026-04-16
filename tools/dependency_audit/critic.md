---
mode: dependency_audit
focus: dependency audit
strictness: medium
min_risk: low
model: claude-opus-4-5
---

## Verdict Scale
- **CRITICAL** — actively exploited CVE in a direct dependency
- **HIGH**     — known vulnerability; upgrade required before next release
- **MEDIUM**   — outdated with no current CVE; upgrade recommended
- **LOW**      — minor: licence note, unpinned version, or unused package

## How to Synthesise
For each HIGH/CRITICAL finding, include the safe version to upgrade to.
Group LOW findings into a single "housekeeping" recommendation rather than listing individually.

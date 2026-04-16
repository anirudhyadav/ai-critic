---
mode: test_quality
focus: test quality
strictness: medium
min_risk: low
model: claude-opus-4-5
---

## Verdict Scale
- **CRITICAL** — test suite provides false confidence; critical paths are untested or wrongly asserted
- **HIGH**     — significant gaps that would let real bugs ship undetected
- **MEDIUM**   — quality issues that reduce reliability of the suite
- **LOW**      — minor improvements; suite is fundamentally sound

## How to Synthesise
For each HIGH/CRITICAL finding, suggest one concrete test scenario that should be added.
End with a confidence score: how much does this test suite actually protect the codebase?

---
mode: error_handling
focus: error handling
strictness: high
min_risk: low
model: claude-opus-4-5
---

## Verdict Scale
- **CRITICAL** — silent failure that corrupts data or leaves system in undefined state
- **HIGH**     — unhandled error that will surface as an opaque failure in production
- **MEDIUM**   — poor error propagation; degrades observability
- **LOW**      — minor: missing timeout or overly broad catch with logging present

## How to Synthesise
Focus on what happens to the user and to data when each error path is hit.
Recommendations should be concrete: what to catch, what to log, what to re-raise.

---
mode: migration_safety
focus: migration safety
strictness: high
min_risk: medium
model: claude-opus-4-5
---

## Verdict Scale
- **CRITICAL** — migration will cause data loss or extended downtime; do not run
- **HIGH**     — migration is risky; requires a maintenance window or phased rollout
- **MEDIUM**   — addressable with a small change before running
- **LOW**      — safe to run with standard monitoring

## How to Synthesise
Prioritise data loss risks above all else. Lock contention is second priority.
Give a clear go / no-go recommendation at the top of your verdict.

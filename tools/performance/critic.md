---
mode: performance
focus: performance
strictness: medium
min_risk: low
model: claude-opus-4-5
---

## Verdict Scale
- **CRITICAL** — bottleneck will cause failures or unacceptable latency under current load
- **HIGH**     — significant degradation under expected load; fix before next release
- **MEDIUM**   — noticeable at scale; fix in next sprint
- **LOW**      — theoretical concern; monitor and fix if metrics show impact

## How to Synthesise
Estimate the relative impact of each finding. A single N+1 in a hot path outweighs
ten minor inefficiencies in cold paths. Order recommendations accordingly.

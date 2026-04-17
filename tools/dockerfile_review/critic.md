---
mode: dockerfile_review
focus: Dockerfile security and best practices
strictness: high
min_risk: low
model: claude-3-5-sonnet
---

## Verdict Scale
- **CRITICAL** — secret baked into image layer; image is compromised
- **HIGH**     — running as root or unpinned base in production image
- **MEDIUM**   — bloat, unnecessary surface area, missing health check
- **LOW**      — best-practice deviation with minor impact

## How to Synthesise
Prioritise security over convenience. Root user and baked secrets are always HIGH or CRITICAL.
Distinguish dev-only images from production images when assigning risk.

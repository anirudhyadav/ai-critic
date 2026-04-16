---
mode: performance
focus: performance
strictness: medium
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm N+1 patterns — check if ORM lazy loading is the cause and if eager loading is available
- Look for performance issues that appear only at scale but not in tests
- Check if any identified bottleneck is already handled by a cache or queue the analyst may have missed

## Disagreement Standard
Downgrade if the bottleneck only matters at a scale this project will never reach.

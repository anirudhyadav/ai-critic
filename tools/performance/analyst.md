---
mode: performance
focus: performance
strictness: medium
min_risk: low
model: claude-opus-4-5
---

## What to Check
- N+1 database queries: loops that execute a query per iteration
- Missing database indexes implied by query patterns in the code
- Blocking I/O on the main thread or in async contexts
- Nested loops with O(n²) or worse complexity on potentially large datasets
- Large objects loaded fully into memory when streaming would suffice
- Missing caching for expensive, repeated computations
- Redundant network calls that could be batched or cached
- Synchronous calls inside what should be async code paths

## Ignore
- Micro-optimisations on code that runs once at startup
- Style preferences about algorithm choice where performance difference is negligible

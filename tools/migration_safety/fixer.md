---
model: claude-opus-4-5
---

## Constraints
- Apply ONLY the changes listed in the recommendations
- For index creation: add CONCURRENTLY where the recommendation requires it
- Never remove a column or table — skip any such recommendation with a clear reason
- If a down migration (rollback) is missing, add one
- Do not modify data-affecting SQL without explicit instruction in the recommendation
- Preserve existing migration structure and comments exactly

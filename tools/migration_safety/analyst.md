---
mode: migration_safety
focus: migration safety
strictness: high
min_risk: low
model: claude-opus-4-5
---

## What to Check
- Data loss: column drops, table truncations, type changes that lose precision
- Lock contention: adding NOT NULL columns, building indexes without CONCURRENTLY
- Missing rollback path: irreversible operations with no down migration
- Zero-downtime risk: migrations that require the app to be offline
- Constraint timing: foreign keys or unique constraints added before data is clean
- ORM migration hygiene: auto-generated migrations that do more than intended

## Ignore
- Whitespace and formatting in migration files
- Comment style

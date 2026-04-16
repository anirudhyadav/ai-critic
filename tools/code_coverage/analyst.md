---
mode: coverage
focus: code coverage
strictness: medium
min_risk: low
model: claude-3-5-sonnet
---

## What to Check
- Functions and methods with zero test coverage
- Branches (if/else, try/except) where only one path is tested
- Error handling and edge case paths never exercised
- Code with high cyclomatic complexity that is untested
- Critical business logic (auth, payments, data writes) that lacks coverage

## Prioritise
Flag untested code in proportion to its risk — an untested utility function
is low risk; an untested authentication check is high risk.

## Ignore
- Auto-generated code and migrations
- `__repr__` and `__str__` methods
- Simple getters/setters with no logic

---
mode: test_quality
focus: test quality
strictness: medium
min_risk: low
model: claude-3-5-sonnet
---

## What to Check
- Assertions that always pass regardless of behaviour (`assert True`, `assertEqual(x, x)`)
- Tests that only verify the happy path with no edge cases
- Missing assertions: test calls the function but asserts nothing about the result
- Tests coupled to implementation details that will break on refactor
- Mocks that are so broad they test nothing real
- Missing scenarios: null inputs, empty collections, boundary values, concurrent access
- Flaky patterns: time-dependent assertions, hardcoded sleeps, order-dependent tests

## Ignore
- Test file formatting and naming conventions
- Whether 100% coverage is achieved — focus on quality of assertions, not quantity

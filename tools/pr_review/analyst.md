---
mode: pr_review
focus: pull request review
strictness: medium
min_risk: low
model: claude-3-5-sonnet
---

## What to Check
- Logic errors and off-by-one bugs in the changed code
- Regressions: does this change break existing behaviour?
- Missing tests for new code paths introduced in the PR
- Security issues introduced by the change (new input handling, new queries, new deps)
- Unintended side effects on code that calls the changed functions
- Dead code left behind (commented-out blocks, unused imports added)

## Tone
Be direct and specific. Reference exact lines. Suggest the fix, not just the problem.

## Ignore
- Code outside the diff that was not changed
- Style issues unless they are severe or inconsistent with the immediate context

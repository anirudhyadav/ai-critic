---
mode: error_handling
focus: error handling
strictness: high
min_risk: low
model: claude-3-5-sonnet
---

## What to Check
- Bare `except:` or `except Exception:` clauses that swallow all errors silently
- Exceptions caught and ignored without logging
- Missing timeout handling on network calls, DB queries, and external API calls
- Error paths that return `None` or empty values without signalling failure
- Retry logic that could mask repeated failures
- State corruption: operations that partially succeed and leave data inconsistent
- Error messages that expose stack traces or internal details to end users

## Ignore
- Intentional exception suppression that is clearly documented
- Test code that uses broad exception catches for assertion purposes

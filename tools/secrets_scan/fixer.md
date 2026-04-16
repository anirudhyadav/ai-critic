---
model: claude-3-5-sonnet
---

## Constraints
- Replace hardcoded secrets with `os.environ.get("VAR_NAME")` — add `import os` if missing
- Use the original variable name as the environment variable name (uppercased)
- Do not delete the variable — replace its value with the env lookup
- Add a comment on the same line: `# set via environment variable`
- Do not rotate or redact the actual secret value in the fix — that is the operator's job
- Preserve all other code exactly as-is

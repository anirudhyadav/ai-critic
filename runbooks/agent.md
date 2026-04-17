# Runbook — aicritic Agent Mode

## Overview

Agent mode lets you describe a task in plain English. Claude Opus drives the
pipeline autonomously — loading files, running analysis, applying fixes,
verifying with tests, and opening PRs — without you stringing together flags.

```
User: "review my PR and fix anything high-risk"
    │
    ▼
Claude Opus decides the sequence:
  → get_changed_files(ref="HEAD~1")
  → run_analysis(tool="security_review")
  → apply_fixes(min_risk="high")
  → run_shell("ruff check .")   ← optional verification
  → open_pr()                   ← only if task requested it
    │
    ▼
Final summary streamed back to terminal / Copilot Chat
```

---

## CLI usage

```bash
python aicritic.py agent "<task>" <target> [flags]
```

### Examples

```bash
# Review only changed files, fix high-risk issues, open a PR
python aicritic.py agent \
  "review my PR and fix high-risk issues, then open a PR" \
  . --min-risk high

# Scan a directory for secrets, fix them
python aicritic.py agent \
  "scan for hardcoded secrets and fix them" \
  ./src --tool secrets_scan

# Full security review, verify with tests, set a new baseline
python aicritic.py agent \
  "security review, run pytest after fixing, then save a baseline" \
  ./src

# Dockerfile hardening
python aicritic.py agent \
  "review Dockerfiles for security issues and fix what you can" \
  . --tool dockerfile_review --lang dockerfile
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--tool NAME` | security_review | Default tool profile if the agent doesn't infer one |
| `--min-risk LEVEL` | low | Default minimum risk threshold for fixes |
| `--roles DIR` | — | Custom roles directory |
| `--max-steps N` | 12 | Hard ceiling on tool-call iterations |

---

## Copilot Chat usage

Add `@agent` anywhere in your message to activate agent mode:

```
@aicritic @agent review my changes and fix the critical issues

@aicritic @agent scan for secrets in the pasted code
```python
AWS_SECRET_ACCESS_KEY = "real_key_here"
```
```

Without `@agent`, `@aicritic` runs the standard one-shot pipeline
(Sonnet → Gemini → Opus, no fixer, no PR).

---

## What the agent can do

| Capability | How triggered |
|---|---|
| Load changed files only | Task mentions "PR", "changes", "diff" |
| Run security / secrets / performance / IaC review | Task keywords match tool profiles |
| Apply literal + LLM fixes | Task says "fix", "remediate", "patch" |
| Run linter or test suite | Task says "verify", "run tests", "check lint" |
| Open a pull request | Task explicitly says "open a PR" or "pull request" |
| Save a baseline | Task says "save baseline" or "set baseline" |

---

## How it stops

The agent terminates when either:

1. Claude delivers a final answer without calling any more tools (normal completion)
2. `--max-steps` is reached (safety ceiling — increase with `--max-steps 20` for complex tasks)

The step log is printed at the end so you can see exactly what was executed.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Agent loops on "no files loaded" | Target path wrong or empty | Check path exists and contains source files |
| `apply_fixes` called before `run_analysis` | Agent skipped analysis | Add "first analyse, then fix" to your task description |
| PR fails with `401 Unauthorized` | Token missing repo write scope | Regenerate PAT with `repo` permission |
| Agent hits max steps | Complex task with many files | Use `--max-steps 20` or break task into two runs |
| `run_shell` returns exit 1 | Linter / tests fail after fixes | Review the shell output in the step log; fixes may need manual review |
| Copilot Chat doesn't enter agent mode | `@agent` not in message | Include `@agent` anywhere in the message |

---

## Security notes

- Fixes are backed up to `.aicritic_backup/<timestamp>/` before any file is written
- `run_shell` executes in the target directory — do not point the agent at untrusted code
- `open_pr` requires explicit user intent in the task description; it is not called speculatively
- `AICRITIC_DEV_MODE=true` skips ECDSA signature check for Copilot Extension (dev only)

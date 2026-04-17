# Agent Mode

Tell aicritic what you want in plain English. It figures out the steps,
calls the right tools, and reports back.

```bash
python aicritic.py agent "review my PR and fix high-risk issues" src/
```

---

## I want to review my changed files and get a report

```bash
python aicritic.py agent "review what I changed since main" src/
python aicritic.py agent "check what changed and summarise the risks" src/
```

aicritic detects that this is a diff-scoped task, loads only the changed files,
runs the full pipeline, and gives you a summary.

---

## I want it to find and fix issues automatically

```bash
# Fix HIGH and CRITICAL, leave MEDIUM alone
python aicritic.py agent "fix all high-risk security issues in src/" src/

# Fix and run tests to verify nothing broke
python aicritic.py agent "fix high-risk issues in src/ and run pytest after" src/

# Fix and open a GitHub PR
python aicritic.py agent "review my PR and fix high-risk issues, then open a PR" src/
```

Before applying fixes, it tells you what it found and what it's about to change.

---

## I want a security report without any changes

```bash
python aicritic.py agent "give me a full security report on this codebase" src/
python aicritic.py agent "scan for hardcoded secrets — just report, don't fix anything" .
```

---

## I want it to review my design and suggest refactors

```bash
python aicritic.py agent "review my code for design issues" src/
python aicritic.py agent "find God classes and suggest how to split them" src/
python aicritic.py agent "check for anti-patterns and refactor opportunities" src/
```

The agent calls the `refactor` tool which runs the design pattern advisor:
complexity metrics, anti-pattern detection, and pattern opportunities with
before/after using your actual class and method names.

---

## I want to set a new baseline (ignore existing issues, only track new ones)

```bash
python aicritic.py agent "set a new baseline for the current findings" src/
```

---

## What happens when it runs

You see each tool call and its result as it works:

```
  → get_changed_files(ref='main')
     3 file(s) loaded: db.py, auth.py, config.py

  → run_analysis(tool='security_review')
     3 findings: 1 HIGH, 1 MEDIUM, 1 LOW

Found 3 issues. Here's what I found before applying any fixes:
  - [HIGH]   db.py:23     — SQL injection
  - [MEDIUM] auth.py:45   — Password in log
  - [LOW]    config.py:5  — Hardcoded timeout

  → apply_fixes(min_risk='high')
     Applied: 1 literal patch in db.py

  → run_shell(command='python -m pytest')
     Exit code: 0 — tests pass

  → open_pr(title='Fix SQL injection in db.py')
     Pull request opened: https://github.com/org/repo/pull/42

Fixed 1 HIGH issue. PR: https://github.com/org/repo/pull/42
```

---

## Tips for better results

**Be specific about what to fix:**
```bash
# Vague — may try to fix everything
"fix the issues"

# Better — only fixes what you decided to address
"fix HIGH and CRITICAL issues, leave MEDIUM for now"
```

**Tell it when to stop:**
```bash
"review my PR — don't apply any fixes, just report"
"scan for secrets and open a PR only if you find any"
```

**Ask it to verify after fixing:**
```bash
"fix high-risk issues in src/ and run pytest after each fix"
```

---

## All flags

| Flag | Default | What it does |
|------|---------|-------------|
| `task` | required | Natural language description of the task |
| `target` | required | File or directory to work on |
| `--tool` | `security_review` | Default analysis profile |
| `--min-risk` | `low` | Default risk threshold for fixes |
| `--max-steps` | `12` | Hard limit on tool iterations |
| `--roles` | — | Custom roles directory |

---

## Available tools the agent can call

| Tool | What it does |
|------|-------------|
| `get_changed_files(ref)` | Load files changed since a git ref |
| `read_files(languages)` | Load all source files from the target |
| `read_file(path)` | Read a single file |
| `write_file(path, content)` | Write a file |
| `run_analysis(tool)` | Run the full Sonnet → Gemini → Opus pipeline |
| `apply_fixes(min_risk)` | Apply critic recommendations to source files |
| `refactor` | Run design pattern advisor (complexity + anti-patterns + opportunities) |
| `open_pr(title)` | Create branch, push, open PR with inline review comments |
| `run_shell(command)` | Run a shell command (tests, linter, syntax check) |
| `save_baseline(path)` | Save current findings as a baseline |

The agent decides which tools to call and in what order based on your task.

---

## Using agent mode in VS Code Copilot Chat

Prefix your message with `@agent`:

```
@aicritic @agent review my PR and fix high-risk issues
@aicritic @agent scan for hardcoded secrets in the backend
@aicritic @agent check what I changed since main
@aicritic @agent review my code for design issues
```

Progress streams into the chat as it works.

---

## Troubleshooting

**`Agent reached maximum steps without completing the task`**
The task was too large for the default 12-step limit. Add `--max-steps 20`:
```bash
python aicritic.py agent "..." src/ --max-steps 20
```

**Agent applies fixes you didn't want**
Be explicit in your task: `"review and report, do not apply any fixes"`.
The agent follows task instructions precisely.

**Agent doesn't find the right files**
If your task is about changed files, mention it: `"review the files I changed since main"`.
Otherwise it loads all files from the target directory.

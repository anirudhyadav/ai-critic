# Runbook — aicritic Agent Mode

## Overview

Agent mode lets you describe a task in plain English. Claude Opus drives the
aicritic pipeline autonomously — reading files, running analysis, applying fixes,
opening PRs, and running shell commands — until the task is complete or the
safety ceiling is reached.

```
You: "review my PR and fix high-risk security issues"
    │
    ▼
Claude Opus
    ├─ calls get_changed_files(ref="main")
    ├─ calls run_analysis(tool="security_review")
    ├─ tells you: "Found 2 HIGH issues: SQL injection at db.py:23, hardcoded key at config.py:5"
    ├─ calls apply_fixes(min_risk="high")
    ├─ calls run_shell(command="python -m pytest")   ← verifies fix didn't break tests
    └─ calls open_pr(title="Fix SQL injection and remove hardcoded key")
       → posts inline review comments on each finding
       → returns PR URL
```

---

## CLI usage

```bash
python aicritic.py agent "<task>" <target> [options]
```

### Examples

```bash
# Security review + fix + PR
python aicritic.py agent "review my PR and fix high-risk issues" src/

# Scan a specific area
python aicritic.py agent "scan for hardcoded secrets" .

# Changed files only
python aicritic.py agent "check what changed since main" src/ --tool pr_review

# High-risk fixes with test verification
python aicritic.py agent "fix all high-risk security issues, run pytest after" src/

# Just analyse, no fixes
python aicritic.py agent "give me a security report on this codebase" src/

# Baseline
python aicritic.py agent "set a new baseline for the current findings" src/
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `task` | *(required)* | Natural language description of the task |
| `target` | *(required)* | File or directory to operate on |
| `--tool` | `security_review` | Default analysis profile |
| `--min-risk` | `low` | Default risk threshold |
| `--max-steps` | `12` | Safety ceiling on tool iterations |
| `--roles` | — | Custom roles directory |

### Output

The agent prints each tool call and its result as it works:

```
  → get_changed_files(ref='main')
     3 file(s) loaded: db.py, auth.py, config.py

  → run_analysis(tool='security_review')
     3 findings: 1 HIGH, 1 MEDIUM, 1 LOW

Found 3 issues. Before I fix them:
  - [HIGH] db.py:23 — SQL injection
  - [MEDIUM] auth.py:45 — Password in log
  - [LOW] config.py:5 — Hardcoded timeout

  → apply_fixes(min_risk='high')
     Applied: 1 literal patch in db.py

  → run_shell(command='python -m pytest')
     Exit code: 0 — tests pass

  → open_pr(title='Fix SQL injection in db.py')
     Pull request opened: https://github.com/org/repo/pull/42

Analysis complete. Fixed 1 HIGH issue (SQL injection in db.py:23).
PR: https://github.com/org/repo/pull/42
```

---

## Copilot Chat usage

In VS Code Copilot Chat, prefix your message with `@agent`:

```
@aicritic @agent review my PR and fix high-risk issues
@aicritic @agent scan for hardcoded secrets in the backend
@aicritic @agent check what I changed since main
@aicritic @agent give me a full security report
```

The agent streams progress and its final summary directly into the chat.

---

## Available tools

Claude can call any of these tools during a session:

| Tool | What it does |
|------|-------------|
| `get_changed_files(ref)` | List files changed between a git ref and HEAD |
| `read_files(languages)` | Load source files from the target path |
| `read_file(path)` | Read a single file |
| `write_file(path, content)` | Write a file (small targeted edits) |
| `run_analysis(tool, skip_checker)` | Run Sonnet → Gemini → Opus pipeline |
| `apply_fixes(min_risk)` | Apply critic recommendations to source files |
| `open_pr(title)` | Create branch, push, open PR with inline review comments |
| `run_shell(command, timeout)` | Run a shell command (linter, tests, syntax check) |
| `save_baseline(path)` | Save current findings as a baseline |

**Claude decides which tools to call and in what order** based on the task
description and workflow rules embedded in its system prompt.

---

## Workflow rules (built-in)

The agent's system prompt enforces these rules automatically:

1. For PR-scoped tasks ("review my changes"): call `get_changed_files` first.
   Otherwise: call `read_files` to load the full target.
2. Always call `run_analysis` before `apply_fixes` or `open_pr`.
3. Before `apply_fixes`, summarise findings to the user — let them see what
   will change before it changes.
4. Only call `open_pr` when the task explicitly requests a pull request.
5. After `apply_fixes`, optionally call `run_shell` with a test/lint command
   if one is obvious from context.
6. Only call `save_baseline` when explicitly asked.
7. Finish with a concise summary: what was analysed, what was found, what
   was fixed, PR URL (if opened).

---

## Safety

**`--max-steps N`** — hard ceiling on tool iterations (default 12). If the agent
hasn't finished by then, it returns the message:
```
Agent reached maximum steps without completing the task.
```
Increase with `--max-steps 20` for complex codebases.

**Tool handlers never raise** — every tool returns a string result (including
errors). Claude decides how to proceed based on the result. This prevents a single
tool failure from crashing the session.

**Shell sandboxing** — `run_shell` executes in the target directory with the
current user's permissions. There is no additional sandbox. Do not point the
agent at untrusted code.

---

## Session state

The agent carries state across tool calls in an `AgentSession` object:

| Field | Set by | Used by |
|-------|--------|---------|
| `inputs` | `read_files` / `get_changed_files` | `run_analysis` |
| `analyst_result` | `run_analysis` | `run_analysis` (passed to checker) |
| `checker_result` | `run_analysis` | `run_analysis` (passed to critic) |
| `critic_result` | `run_analysis` | `apply_fixes`, `open_pr` |
| `fixer_result` | `apply_fixes` | `open_pr` |
| `pr_url` | `open_pr` | Final summary |
| `last_shell_output` | `run_shell` | Available to Claude for decisions |
| `token` | Session init | All pipeline + PR tool calls |

---

## Tips

**Be specific about what you want fixed:**
```
# Vague — may try to fix everything
"fix the issues"

# Better — only fixes what you've decided to address
"fix HIGH and CRITICAL issues, leave MEDIUM for now"
```

**Tell it when to stop:**
```
"review my PR — don't apply any fixes, just report"
"scan for secrets and open a PR with fixes if you find any"
```

**For large codebases, use diff mode:**
The agent automatically calls `get_changed_files` when the task mentions "PR",
"changes", "diff", or "what I changed". Be explicit for other cases:
```
"review the files changed since origin/main"
```

**Verify fixes didn't break anything:**
Include verification in the task:
```
"fix high-risk issues in src/ and run pytest after each fix"
```
The agent will call `run_shell("python -m pytest")` and report the result.

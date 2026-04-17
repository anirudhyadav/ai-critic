# Runbook — aicritic CLI

## Overview

The CLI runs the three-model critic chain locally against a file or directory.
No server, no GitHub App — just a terminal and a GitHub token.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Check with `python --version` |
| pip | any | Comes with Python |
| GitHub account | — | Must have Copilot Enterprise access |
| GitHub token | — | See Step 2 below |

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/anirudhyadav/ai-critic.git
cd ai-critic
```

---

## Step 2 — Create a GitHub token

1. Go to **github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Set expiry (90 days recommended for a demo token)
4. Under **Permissions** → no special scopes needed — models access is covered by the Copilot Enterprise licence
5. Click **Generate token** and copy the value

> The token only needs to exist under an account with an active Copilot Enterprise seat.
> It does not need any repository or organisation permissions.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

Installs: `openai`, `python-dotenv`, `rich`, `fastapi`, `uvicorn`, `httpx`, `cryptography`

---

## Step 4 — Configure environment

```bash
cp .env.example .env
```

Open `.env` and set your token:

```
GITHUB_TOKEN=ghp_your_token_here
```

---

## Step 5 — Verify the setup

```bash
python aicritic.py --help
```

Expected output:
```
usage: aicritic [-h] {check} ...

Route code through three AI models: Sonnet → Gemini → Opus.
...
```

---

## Running the tool

### Basic security review (default)

```bash
python aicritic.py check ./demo
```

### Run a specific tool

```bash
# Scan for hardcoded secrets
python aicritic.py check ./src --tool secrets_scan

# Check code coverage (requires coverage.xml)
python aicritic.py check ./src --tool code_coverage --coverage coverage.xml

# Review a pull request
python aicritic.py check ./src --tool pr_review

# Check DB migrations
python aicritic.py check ./migrations --tool migration_safety

# Audit dependencies
python aicritic.py check ./requirements.txt --tool dependency_audit
```

### Skip Gemini for faster results

```bash
# Sonnet → Opus only (~20s instead of ~90s)
python aicritic.py check ./src --skip-checker
```

Use this for tight dev-loop iterations or when Gemini is rate-limited.
The critic is told the cross-check was skipped and applies extra scrutiny.

### Parallel mode — Sonnet and Gemini at the same time

```bash
# Both analysts run in parallel; Opus arbitrates between independent findings
python aicritic.py check ./src --parallel
```

Trades the analyst→checker review chain for wall-clock speed.
Total time ≈ max(Sonnet, Gemini) + Opus instead of all three sequential.

### Large codebases — automatic batching

When the source set is too large for a single LLM call, `aicritic` splits it
into batches automatically — you'll see `[batch 1/3]…` in the output. The
analyst and checker run per batch; findings are aggregated before the
critic runs once. Works transparently with `--parallel`.

No flag needed — batching kicks in above ~40 kB of source code.

### PR-style review — only changed files

```bash
# Analyse only the files changed between main and HEAD
python aicritic.py check . --diff main

# Or against a specific commit
python aicritic.py check . --diff HEAD~5
```

Loader filters the file list to `git diff --name-only <ref>...HEAD` — combined
with `--skip-checker`, you get a ~15-second PR review on every push.

### Baseline / delta mode — show only new findings

```bash
# First run: save the current state as the baseline
python aicritic.py check ./src --save-baseline .aicritic_baseline.json

# Later runs: suppress anything already in the baseline
python aicritic.py check ./src --baseline .aicritic_baseline.json
```

Findings are fingerprinted by `(file, line_range, description prefix)`. Ideal
for legacy codebases — fail the CI build only when *new* HIGH issues appear,
not when the 200 pre-existing ones do. Combine with `--min-risk high` and a
non-zero exit code in CI to gate merges on regressions only.

### Auto-fix PR — close the loop from "found it" to "fixed it"

```bash
python aicritic.py check ./src --fix --pr
```

When you confirm the fixes, aicritic:
1. Creates a fresh branch `aicritic/fix-<tool>-<timestamp>`
2. Commits the changed files
3. Pushes to `origin`
4. Opens a PR against the default branch via the GitHub REST API

Requires `GITHUB_TOKEN` with `repo` write scope. The PR body lists every
modified file and echoes the critic's summary.

### CI integration — emit SARIF for GitHub code-scanning

```bash
python aicritic.py check ./src --sarif aicritic.sarif
```

In a GitHub Actions workflow:
```yaml
- run: python aicritic.py check ./src --sarif aicritic.sarif --skip-checker
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: aicritic.sarif
```

Findings render as PR annotations and appear in the repo's Security tab.
Dismissed alerts are tracked across runs by GitHub — free feedback loop.

### Filter noise — only surface HIGH findings

```bash
python aicritic.py check ./src --min-risk high
```

### Apply fixes automatically

```bash
# Preview what would change (safe — no files written)
python aicritic.py check ./src --tool secrets_scan --fix --dry-run

# Apply with confirmation prompt
python aicritic.py check ./src --tool secrets_scan --fix

# Apply HIGH fixes only
python aicritic.py check ./src --fix --min-risk high
```

The fixer is two-phase:

1. **Deterministic literal patches** — applied directly with `str.replace()` when
   the critic provided `find`/`replace` with `confidence: high` and `find`
   appears exactly once in the target file. No LLM involved.
2. **LLM rewrite fallback** — runs only for the leftovers (ambiguous,
   multi-location, or architectural changes).

You'll see `N literal patch(es) (deterministic)` in the console when phase 1
applied any patches. Skipped items appear as `→ reason` lines so you always
know what the fixer declined to touch.

When `--fix` is confirmed, originals are backed up to `.aicritic_backup/<timestamp>/` before any file is written.

### Generate a coverage report first

```bash
pip install coverage pytest
coverage run -m pytest
coverage xml          # produces coverage.xml

python aicritic.py check ./src --tool code_coverage --coverage coverage.xml
```

### Use a custom role profile

```bash
# Create your own roles directory
mkdir my-strict-profile
cp roles/*.md my-strict-profile/
# edit my-strict-profile/analyst.md → change strictness: high, model: claude-opus-4-5

python aicritic.py check ./src --roles ./my-strict-profile
```

---

## All CLI flags

```
python aicritic.py check <target> [flags]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--tool NAME` | security_review | Built-in tool profile |
| `--coverage FILE` | — | coverage.xml from `coverage xml` |
| `--min-risk LEVEL` | low | Show findings at or above: low / medium / high |
| `--skip-checker` | off | Skip Gemini cross-check — Sonnet → Opus only (~20s vs ~90s) |
| `--parallel` | off | Run Sonnet + Gemini in parallel as independent analyses (~50s vs ~90s) |
| `--fix` | off | Run fixer stage after critic |
| `--dry-run` | off | With `--fix`: show diff only, no writes |
| `--roles DIR` | roles/ | Custom roles directory (overrides `--tool`) |
| `--output FILE` | aicritic_report.md | Where to save the markdown report |
| `--sarif FILE` | — | Also write SARIF 2.1.0 JSON for GitHub code-scanning upload |
| `--diff REF` | — | Only analyse files changed between REF and HEAD (PR-style review) |
| `--baseline FILE` | — | Suppress findings already present in this baseline JSON |
| `--save-baseline FILE` | — | Save the current run's findings as a baseline for future `--baseline` calls |
| `--pr` | off | With `--fix`: create a branch, push, and open a PR via the GitHub REST API |

---

## Built-in tools

| Bucket | Tool | What it checks |
|--------|------|---------------|
| Ship Safety | `migration_safety` | Data loss, lock contention, missing rollbacks |
| Ship Safety | `secrets_scan` | Hardcoded credentials, API keys, tokens |
| Code Confidence | `code_coverage` | Untested paths, missing branch coverage |
| Code Confidence | `error_handling` | Swallowed exceptions, silent failures |
| Review Depth | `pr_review` | Regressions, logic errors in changed code |
| Review Depth | `test_quality` | Meaningless assertions, missing edge cases |
| Codebase Health | `dependency_audit` | CVEs, outdated packages, licence conflicts |
| Codebase Health | `performance` | N+1 queries, blocking I/O, inefficient loops |

---

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Console | Terminal | Rich-formatted, colour-coded per risk level |
| Report | `aicritic_report.md` | Markdown version of the full report |
| Backups | `.aicritic_backup/<timestamp>/` | Originals saved when `--fix` is confirmed |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `GITHUB_TOKEN is not set` | Missing `.env` or not exported | Run `cp .env.example .env` and add token |
| `401 Unauthorized` from API | Token expired or invalid | Regenerate token at github.com → Settings |
| `No Python source files found` | Wrong target path | Check the path exists and contains `.py` files |
| `Could not parse coverage XML` | Malformed `coverage.xml` | Regenerate with `coverage xml` after a fresh `coverage run` |
| `Could not parse JSON from model response` | Model returned prose instead of JSON | Re-run — usually a one-off; if persistent, check system prompt in `config.py` |
| `⚠ Checker stage unavailable` banner | Gemini API timeout or rate limit | Run continues with analyst-only findings; use `--skip-checker` to suppress the retry attempt next run |
| Slow (90s+) sequential run | Three sequential LLM calls | Add `--parallel` (~50s) or `--skip-checker` (~20s) |
| Hangs on a very large repo | Single prompt exceeds context window | Should self-resolve — auto-batching kicks in above ~40 kB; look for `[batch i/N]` progress lines |

---

## Demo script (for leadership)

```bash
# 1. Show the deliberately flawed demo project
cat demo/auth.py

# 2. Run security review
python aicritic.py check ./demo

# 3. Run with auto-fix preview
python aicritic.py check ./demo --fix --dry-run

# 4. Show the saved report
cat aicritic_report.md
```

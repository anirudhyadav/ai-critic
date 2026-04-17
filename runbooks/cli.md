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
| `--fix` | off | Run fixer stage after critic |
| `--dry-run` | off | With `--fix`: show diff only, no writes |
| `--roles DIR` | roles/ | Custom roles directory (overrides `--tool`) |
| `--output FILE` | aicritic_report.md | Where to save the markdown report |

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
| `Could not parse JSON from model response` | Model returned prose instead of JSON | Re-run — usually a one-off; if persistent, check system prompt in `config.py` |
| Slow response | Three sequential LLM calls | Expected — 30–90 seconds total is normal |

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

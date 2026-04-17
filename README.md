# aicritic

A multi-LLM critic chain for code analysis. Instead of asking one model, three models collaborate in sequence — each playing a distinct role — to produce a more reliable, higher-confidence result.

```
Your code
    │
    ▼
[Claude Sonnet]   primary analyst     → reads the code, identifies issues
    │
    ▼
[Gemini]          cross-checker       → verifies Sonnet's findings, flags gaps
    │
    ▼
[Claude Opus]     critic / arbiter    → assigns risk levels, prioritises fixes
    │
    ▼
[Fixer]           (optional)          → applies recommendations back to source
    │
    ▼
Console report  +  aicritic_report.md
```

All three models are accessed through the **GitHub Models API** — a single OpenAI-compatible endpoint covered by a GitHub Copilot Enterprise licence. No separate API keys required.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your GitHub token
cp .env.example .env
# edit .env and add your GITHUB_TOKEN

# Run against a directory
python aicritic.py check ./myproject

# Run a specific tool
python aicritic.py check ./myproject --tool secrets_scan

# Review and auto-fix findings
python aicritic.py check ./myproject --tool secrets_scan --fix
```

---

## Built-in Tools

Tools are organised into four buckets. Select one with `--tool <name>`.

### Ship Safety
| Tool | What it checks |
|------|---------------|
| `migration_safety` | Data loss, lock contention, missing rollbacks in DB migrations |
| `secrets_scan` | Hardcoded credentials, API keys, tokens, weak entropy sources |

### Code Confidence
| Tool | What it checks |
|------|---------------|
| `code_coverage` | Untested paths, missing branch coverage, risky uncovered logic |
| `error_handling` | Swallowed exceptions, missing timeouts, silent failures |

### Review Depth
| Tool | What it checks |
|------|---------------|
| `pr_review` | Regressions, logic errors, missing tests in changed code |
| `test_quality` | Meaningless assertions, missing edge cases, flaky patterns |

### Codebase Health
| Tool | What it checks |
|------|---------------|
| `dependency_audit` | Outdated packages, CVEs, licence conflicts, bloat |
| `performance` | N+1 queries, blocking I/O, inefficient algorithms |

When no `--tool` is specified, the default security review profile is used.

---

## CLI Reference

```bash
python aicritic.py check <target> [options]
```

| Flag | Description |
|------|-------------|
| `--tool NAME` | Built-in tool profile (see table above) |
| `--coverage FILE` | `coverage.xml` from `coverage run -m pytest && coverage xml` |
| `--min-risk LEVEL` | Only surface findings at `low`, `medium`, or `high` and above |
| `--skip-checker` | Skip the Gemini stage — Sonnet → Opus only (faster; less reliable) |
| `--parallel` | Run Sonnet + Gemini in parallel (independent analyses) |
| `--fix` | Run the fixer stage — apply recommendations to source files |
| `--dry-run` | With `--fix`: show the diff but do not write any files |
| `--roles DIR` | Use a custom roles directory instead of a built-in tool |
| `--output FILE` | Report output path (default: `aicritic_report.md`) |
| `--sarif FILE` | Also write SARIF 2.1.0 JSON for GitHub code-scanning upload |

---

## Controlling Model Behaviour

Each role — analyst, checker, critic, fixer — is configured by a markdown file. Edit these files to change what the models focus on, how strict they are, which LLM runs each stage, and what risk level gates the report.

```
roles/            ← default security review profile
tools/
├── secrets_scan/
│   ├── analyst.md
│   ├── checker.md
│   ├── critic.md
│   └── fixer.md
└── ...           ← one directory per tool
```

Each file has a frontmatter block and a freeform instruction body:

```markdown
---
model: claude-opus-4-5      # which LLM runs this stage
focus: security             # human label shown in output
strictness: high            # low | medium | high
min_risk: medium            # gate: only surface findings at or above this level
---

## What to Check
- SQL injection...

## Ignore
- Code style...
```

### Knobs at a glance

| Frontmatter key | Effect |
|-----------------|--------|
| `model` | Swap the LLM for this stage without changing anything else |
| `strictness` | How aggressively to flag issues — shapes the instruction body |
| `min_risk` | Findings below this level are filtered from the report |

### Swapping models per stage

To run the entire chain on Sonnet (fast, cheap):
```markdown
# analyst.md / checker.md / critic.md
model: claude-3-5-sonnet
```

To promote Opus to analyst for a critical security review:
```markdown
# analyst.md
model: claude-opus-4-5
```

### Custom profiles

Point `--roles` at any directory containing `analyst.md`, `checker.md`, `critic.md`:

```bash
python aicritic.py check ./src --roles ./profiles/strict-security
```

---

## The Fixer Stage

When `--fix` is passed, a fourth stage reads the critic's recommendations and applies them to source files.

```bash
# Dry run — see the diff, touch nothing
python aicritic.py check ./demo --tool secrets_scan --fix --dry-run

# Apply only HIGH and above
python aicritic.py check ./demo --fix --min-risk high

# Full fix with confirmation prompt
python aicritic.py check ./demo --tool security_review --fix
```

**Safety guarantees:**
- A colorised diff is shown before any file is touched
- `Apply these changes? [y/N]` — nothing happens until you confirm
- Original files are backed up to `.aicritic_backup/<timestamp>/` before writing

**Tool-specific fixer behaviour:**

| Tool | Fixer approach |
|------|---------------|
| `secrets_scan` | Replaces values with `os.environ.get("VAR_NAME")` — never deletes |
| `migration_safety` | Uses Opus, adds `CONCURRENTLY` where needed, always adds rollback |
| All others | Sonnet applies only what Opus recommended; skips ambiguous changes |

---

## Project Structure

```
aicritic/
├── aicritic.py          CLI entry point
├── config.py            Model names, endpoints, system prompts, load_role()
├── pipeline/
│   ├── __init__.py      Shared JSON parser
│   ├── analyst.py       Step 1 — Claude Sonnet
│   ├── checker.py       Step 2 — Gemini
│   ├── critic.py        Step 3 — Claude Opus
│   └── fixer.py         Step 4 — applies fixes (optional)
├── inputs/
│   └── loader.py        .py file walker + coverage.xml parser
├── report/
│   └── formatter.py     Rich console output + markdown report + diff printer
├── roles/               Default security review profile
│   ├── analyst.md
│   ├── checker.md
│   ├── critic.md
│   └── fixer.md
├── tools/               Built-in tool profiles
│   ├── migration_safety/
│   ├── secrets_scan/
│   ├── code_coverage/
│   ├── error_handling/
│   ├── pr_review/
│   ├── test_quality/
│   ├── dependency_audit/
│   └── performance/
├── demo/                Deliberately flawed project for demos
│   ├── auth.py
│   ├── api.py
│   └── utils.py
├── requirements.txt
└── .env.example
```

---

## Environment Setup

```bash
pip install openai python-dotenv rich
```

`.env` file:
```
GITHUB_TOKEN=ghp_your_token_here
```

The token must belong to an account with GitHub Copilot Enterprise access. The GitHub Models API endpoint (`https://models.inference.ai.azure.com`) handles all three model vendors through the same interface.

---

## Demo

A sample project with deliberate security flaws lives in `demo/`:

```bash
# Basic security review
python aicritic.py check ./demo

# Security review + auto-fix, preview only
python aicritic.py check ./demo --fix --dry-run

# Scan for secrets only, show HIGH findings
python aicritic.py check ./demo --tool secrets_scan --min-risk high
```

---

## Running as a GitHub Copilot Extension

The same pipeline runs as a Copilot Extension (Agent type). Users type
`@aicritic check my code` directly in VS Code or GitHub.com Copilot Chat.

### How it works differently from the CLI

| | CLI | Copilot Extension |
|-|-----|-------------------|
| Code input | File paths on disk | Code pasted in chat as a fenced block |
| Tool selection | `--tool` flag | Auto-detected from natural language |
| Output | Console + markdown file | Streamed into Copilot Chat as it runs |
| Auth | `GITHUB_TOKEN` env var | GitHub App ECDSA signature on every request |

Each model stage streams its results into the chat as it completes — the user
sees Sonnet's findings while Gemini is still running.

### Setup

**1. Start the server**
```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

**2. Expose it publicly (local dev)**
```bash
ngrok http 8000
# Note the https URL — e.g. https://abc123.ngrok.io
```

**3. Register a GitHub App**
- Go to `github.com/settings/apps` → New GitHub App
- Set **Callback URL** and **Webhook URL** to your ngrok URL
- Under **Copilot** → set type to **Agent**, callback URL to `https://abc123.ngrok.io`
- Install the app on your account or organisation

**4. Enable dev mode for local testing**
```bash
# .env
AICRITIC_DEV_MODE=true    # skips ECDSA signature verification
GITHUB_TOKEN=ghp_...
```

**5. Use it in VS Code**
```
@aicritic check this code for security issues

```python
def login(user, pwd):
    query = f"SELECT * FROM users WHERE user='{user}'"
    ...
```
```

### Tool auto-detection

The extension detects which tool to run from the user's message:

| Keywords in message | Tool selected |
|---------------------|---------------|
| secret, credential, hardcoded | `secrets_scan` |
| coverage, untested | `code_coverage` |
| migration, alter table | `migration_safety` |
| performance, slow, n+1 | `performance` |
| error handling, exception | `error_handling` |
| dependency, requirements | `dependency_audit` |
| pull request, pr review | `pr_review` |
| test quality, flaky | `test_quality` |
| _(anything else)_ | `security_review` |

### Project structure — what's new for the extension

```
copilot/
├── auth.py       GitHub ECDSA signature verification
├── parser.py     Extract code blocks + detect tool from chat messages
└── streamer.py   Format pipeline results as SSE chunks
server.py         FastAPI entry point (uvicorn server:app)
```

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — CLI | ✓ Done | Local tool, `python aicritic.py check ./src` |
| 2 — Copilot Extension | ✓ Done | `@aicritic` in VS Code and GitHub.com, FastAPI + SSE |
| 3 — Internal hosting | Planned | Deploy FastAPI behind corporate proxy, firm-wide rollout |

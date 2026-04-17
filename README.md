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
    │                                   (gracefully skipped on failure)
    ▼
[Claude Opus]     critic / arbiter    → assigns risk levels, prioritises fixes
    │                                   (sees only ±5 lines around each finding)
    ▼
[Fixer]           (optional)          → deterministic patches + LLM fallback
    │                                   → backs up originals before writing
    ▼
Console  +  aicritic_report.md  +  aicritic.sarif (optional)
```

All three models are accessed through the **GitHub Models API** — a single OpenAI-compatible endpoint covered by a GitHub Copilot Enterprise licence. No separate API keys required.

**Three execution modes** for the analyst/checker stages:
- **Sequential** (default): analyst → checker reviews analyst → critic — most rigorous, ~90s
- **Parallel** (`--parallel`): analyst + checker run independently at the same time — ~50s
- **Fast** (`--skip-checker`): analyst only, critic arbitrates alone — ~20s

Large codebases are split into batches automatically, so the tool works on real repositories, not just demo snippets.

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
python aicritic.py check ./demo --tool secrets_scan --fix
```

### Two-phase strategy

The fixer splits the work between a **deterministic** path and an **LLM rewrite** path so the most dangerous failure mode (an LLM rewriting working code) is avoided for mechanical changes.

| Phase | How it works | When it runs |
|-------|-------------|--------------|
| **1. Deterministic literal patch** | `str.replace(find, replace, 1)` — no LLM | Critic marked the fix `confidence: high` **and** `find` appears exactly once in the file |
| **2. LLM rewrite** | Model rewrites file content given recommendations | Only for the leftovers: ambiguous, multi-location, or architectural changes |

If a literal `find` string is missing or appears more than once, the patch is **skipped**, not guessed. Skipped items appear in the console as `→ reason` lines.

### Safety guarantees

- A colorised unified diff is shown before any file is touched
- `Apply these changes? [y/N]` — nothing happens until you confirm
- Original files are backed up to `.aicritic_backup/<timestamp>/` before writing
- `--dry-run` previews the diff without prompting or writing

### Tool-specific fixer behaviour

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
├── server.py            FastAPI entry point for the Copilot Extension
├── pipeline/
│   ├── __init__.py      Shared JSON parser
│   ├── analyst.py       Step 1 — Claude Sonnet
│   ├── checker.py       Step 2 — Gemini (graceful degradation on failure)
│   ├── critic.py        Step 3 — Claude Opus (context-window only)
│   ├── fixer.py         Step 4 — deterministic patches + LLM fallback
│   └── batching.py      Auto-batching + finding-context extractor
├── inputs/
│   └── loader.py        .py file walker + coverage.xml parser
├── report/
│   ├── formatter.py     Rich console + markdown report + diff printer
│   └── sarif.py         SARIF 2.1.0 writer for GitHub code-scanning
├── copilot/
│   ├── auth.py          GitHub ECDSA signature verification
│   ├── parser.py        Extract code blocks + detect tool from chat
│   └── streamer.py      Format pipeline results as SSE chunks
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
├── runbooks/            Operator runbooks (CLI + Copilot Extension)
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

## CI Integration (GitHub Actions + SARIF)

Emit SARIF 2.1.0 JSON with `--sarif` and upload via GitHub's standard action. Findings render as PR annotations and appear in the repository's Security tab; GitHub natively tracks dismissed alerts across runs.

```yaml
# .github/workflows/aicritic.yml
name: aicritic

on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write     # required for SARIF upload
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python aicritic.py check ./src --skip-checker --sarif aicritic.sarif
        env:
          GITHUB_TOKEN: ${{ secrets.AICRITIC_GITHUB_TOKEN }}
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: aicritic.sarif
```

Risk mapping:

| aicritic risk | SARIF level | PR annotation |
|---------------|-------------|---------------|
| critical, high | `error` | red dot, blocks merge (if required) |
| medium | `warning` | yellow dot |
| low | `note` | blue dot |

### Delta mode — only fail on new issues

For legacy codebases, you don't want CI to fail on 200 pre-existing findings.
Use a committed baseline file:

```yaml
- run: python aicritic.py check ./src
       --diff ${{ github.event.pull_request.base.ref }}
       --baseline .aicritic_baseline.json
       --min-risk high
       --skip-checker
```

Generate the baseline once (`--save-baseline .aicritic_baseline.json`) and
commit it. From then on CI only surfaces findings that weren't in the
baseline — the delta.

### Auto-fix PR loop

```bash
python aicritic.py check ./src --fix --pr
```

Creates a branch, pushes the fixer's changes, and opens a PR via the GitHub
REST API. Pair with `--min-risk high` and a scheduled workflow to get an
overnight "fix-the-easy-stuff" bot.

---

## Benchmarks

Measure the pipeline's precision and recall against known-flawed fixtures:

```bash
python benchmarks/run.py
python benchmarks/run.py --case sql_injection
python benchmarks/run.py --output benchmarks/latest.json
```

See `benchmarks/README.md` for the case format and matching rules.

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

---

## Features & Benefits

### Features

**Pipeline**
- Three-model critic chain: Claude Sonnet → Gemini → Claude Opus
- Optional fourth stage: fixer applies critic recommendations back to source
- Sequential, parallel, or fast (skip-checker) execution modes
- Graceful degradation — Gemini failure no longer crashes the run
- Auto-batching for codebases that exceed a single LLM's context window
- Context-window critic — Opus sees only ±5 lines around each flagged range

**Analysis coverage (8 built-in tools across 4 buckets)**
- Ship Safety: `migration_safety`, `secrets_scan`
- Code Confidence: `code_coverage`, `error_handling`
- Review Depth: `pr_review`, `test_quality`
- Codebase Health: `dependency_audit`, `performance`

**Fixer**
- Deterministic literal patches for high-confidence mechanical changes (no LLM rewrite)
- LLM rewrite fallback for ambiguous or architectural changes
- Colorised unified diff preview + `Apply? [y/N]` confirmation
- `.aicritic_backup/<timestamp>/` mirror before any write
- `--dry-run` preview-only mode

**Control surface**
- Markdown role files — swap model, strictness, or min_risk without touching Python
- `--tool <name>` for built-in profiles, `--roles <dir>` for fully custom
- `--min-risk` threshold filtering across all stages

**Outputs**
- Rich console report with colour-coded risk levels
- Markdown report file (`aicritic_report.md`)
- SARIF 2.1.0 JSON (`--sarif`) for GitHub code-scanning upload
- Coverage XML parser (`--coverage`) for code_coverage tool

**Surfaces**
- CLI (`python aicritic.py check`) — local terminal, CI workflows
- GitHub Copilot Extension (`@aicritic`) — VS Code + GitHub.com chat
- Server streams results into chat as each stage completes (SSE)

**Security**
- GitHub ECDSA-P256 signature verification on every Copilot request
- Dev mode flag to bypass verification during local development
- No secrets in-repo — `GITHUB_TOKEN` loaded from `.env`

### Benefits

**For engineers**
- Catches issues a single model misses — adversarial cross-check by design
- Fast dev-loop mode (`--skip-checker`) for iteration; rigorous mode for PRs
- Deterministic fixes for mechanical issues — no more second-guessing LLM rewrites
- Works on real repositories — auto-batching prevents context-window failures
- Unified tool for security, coverage, migrations, performance, and more

**For engineering leadership**
- Runs on existing GitHub Copilot Enterprise licence — zero new budget line
- Consistent risk taxonomy (low / medium / high / critical) across every team
- Full audit trail — markdown report + backups + SARIF history in GitHub
- Findings appear natively in PR review — engineers don't need to learn a new tool
- Demo-ready: clone, set token, run against `./demo/` — see results in seconds

**For security and compliance**
- SARIF upload means dismissed alerts are tracked natively by GitHub
- Deterministic fixes are reviewable line-by-line before any write
- Original source is backed up before any modification
- No code leaves the corporate GitHub boundary — models are called via the
  same endpoint that Copilot itself uses

**For the organisation**
- ~40-50% fewer LLM tokens per run (context-window critic + batching)
- ~50% faster wall time with `--parallel`; ~80% faster with `--skip-checker`
- Scales from single-file demos to multi-thousand-file repositories
- Dual-surface delivery: same pipeline powers CI integration and interactive
  chat, so adoption doesn't require picking one or the other

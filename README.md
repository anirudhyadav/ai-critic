# aicritic

**Three AI models review your code in sequence. Each one checks the previous one's work.**

Claude Sonnet finds the issues. Gemini cross-checks them (when the pipeline runs that stage). Claude Opus arbitrates, assigns final risk levels, and writes a prioritised fix plan. An optional fixer applies patches automatically.

```
Your code
    │
    ▼
[1] Claude Sonnet ─── primary analyst ───► findings JSON
    │
    ▼
[2] Gemini ──────────── cross-checker ───► agreements / disagreements (optional; see below)
    │
    ▼
[3] Claude Opus ──────── critic/arbiter ─► verdict + recommendations
    │
    ├─► report  (Markdown / HTML / JSON / SARIF)
    ├─► --fix   → fixer → patched source files
    ├─► --pr    → GitHub PR with inline review comments
    ├─► --explain → WHY + exact fix for your specific code
    └─► --generate-tests → optional test skeletons for high-risk gaps
```

All models run through the **GitHub Models API** — no separate Anthropic or Google API keys. Usage is billed to your **GitHub Copilot** / org entitlement (see GitHub’s current Models documentation for eligibility).

---

## Table of contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Quick start](#quick-start)
4. [How the pipeline works](#how-the-pipeline-works)
5. [Interfaces](#interfaces-check-ci-agent-copilot)
6. [Tool profiles](#tool-profiles)
7. [CLI reference (`check`)](#cli-reference-check)
8. [Outputs](#outputs)
9. [Diff, baseline, and suppressions](#diff-baseline-and-suppressions)
10. [Auto-fix, PRs, and tests](#auto-fix-prs-and-tests)
11. [CI policy gate](#ci-policy-gate)
12. [Agent mode](#agent-mode)
13. [VS Code Copilot extension](#vs-code-copilot-extension)
14. [Configuration files](#configuration-files)
15. [Cache, notifications, hooks, audit](#cache-notifications-hooks-audit)
16. [Custom roles and project layout](#custom-roles-and-project-layout)
17. [Documentation](#documentation)

---

## Requirements

- **Python 3.11+**
- A **GitHub token** with access to **GitHub Models** (fine-grained PAT; Copilot Enterprise access as required by your org — see `.env.example` and GitHub docs)

---

## Installation

```bash
git clone https://github.com/anirudhyadav/ai-critic
cd ai-critic
pip install -r requirements.txt
cp .env.example .env   # set GITHUB_TOKEN=ghp_...
```

---

## Quick start

```bash
# Analyse a directory (default profile: security-style roles under roles/)
python aicritic.py check src/

# Only changed files vs a branch, with teaching explanations
python aicritic.py check src/ --diff main --explain

# Faster: high+ findings only, skip Gemini cross-check
python aicritic.py check src/ --diff main --min-risk high --skip-checker

# Fix automatically; optionally open a PR
python aicritic.py check src/ --fix --pr --min-risk high

# CI gate — exits 1 if policy-defined blocking findings exist
python aicritic.py ci .

# Natural-language agent
python aicritic.py agent "review my changes for security issues and summarise" src/
```

Shorthand: you can run `python aicritic.py "your task" path/` and the CLI injects the `agent` subcommand automatically (see `aicritic.py`).

---

## How the pipeline works

| Stage   | Default model (see `config.py`) | Role |
|--------|----------------------------------|------|
| Analyst | Claude Sonnet                  | Reads loaded sources; emits structured findings |
| Checker | Gemini                         | Cross-checks analyst output; may add findings |
| Critic  | Claude Opus                    | Reconciles stages, assigns risk, fix plan |

**Checker behaviour**

- **`--skip-checker`** — Sonnet → Opus only (fastest; no Gemini).
- **`--parallel`** — Sonnet and Gemini run in parallel (independent analyses reconciled by Opus). Mutually exclusive with skipping the checker in practice; skip wins if both are set.
- **Adaptive skip (default)** — If the analyst finds **no HIGH or CRITICAL** issues, Gemini is skipped unless you pass **`--full`** to always run it. This saves roughly a minute on clean runs.

**Large repos**

- Inputs larger than ~40 kB are **split into batches**, merged before the critic.

**Critic context**

- Opus receives **compact code around each finding** (±5 lines), not necessarily every full file — see `pipeline/critic.py`.

**Fixer**

- Literal high-confidence find/replace patches when possible; otherwise an LLM rewrite of full files — see [FEATURES.md](FEATURES.md) §7.

---

## Interfaces: `check`, `ci`, `agent`, Copilot

| Interface | Best for | Command / usage |
|-----------|----------|-----------------|
| **`check`** | Local or scripted analysis | `python aicritic.py check <path> [flags]` |
| **`ci`** | Blocking merges in GitHub Actions | `python aicritic.py ci <path>` |
| **`agent`** | Natural-language tasks (tools + pipeline) | `python aicritic.py agent "<task>" <path>` |
| **Copilot Chat** | IDE-integrated review | `@aicritic` (and `@agent` for agentic mode) |

---

## Tool profiles

Select with **`--tool <name>`** (defaults to **security_review**-style behaviour via `roles/` when no tool is set). Built-in profiles live under `tools/<name>/` with `analyst.md`, `checker.md`, `critic.md`, and `fixer.md`.

| Profile | Focus |
|---------|--------|
| `security_review` | General security (default when using `roles/`) |
| `secrets_scan` | Hardcoded keys, tokens, passwords |
| `error_handling` | Swallowed errors, bare `except`, missing timeouts |
| `pr_review` | Regressions, logic, tests for new code |
| `performance` | N+1, blocking I/O, hot paths |
| `migration_safety` | DB migrations, locks, rollbacks |
| `test_quality` | Weak assertions, happy-path-only tests |
| `code_coverage` | Coverage gaps (use with `--coverage` / coverage XML as documented) |
| `dependency_audit` | CVEs, outdated deps, licences |
| `dockerfile_review` | Container hygiene and security |
| `iac_review` | Terraform/K8s-style misconfigs |
| `design_review` | Design/architecture review; enables complexity helpers and explain-style output |

Override completely with **`--roles <dir>`** pointing at your own four role files.

---

## CLI reference (`check`)

Common flags (see `python aicritic.py check -h` for the full list):

| Area | Flags |
|------|--------|
| **Scope** | `--diff REF`, `--lang LANG` (repeatable), `--coverage FILE` (e.g. for `code_coverage`) |
| **Pipeline** | `--skip-checker`, `--parallel`, `--full` (always run Gemini when not skipping) |
| **Filtering** | `--min-risk low\|medium\|high` |
| **Reports** | `--output FILE`, `--html FILE`, `--json FILE`, `--sarif FILE` |
| **Explanations** | `--explain` |
| **Fix / ship** | `--fix`, `--dry-run`, `--pr`, `--min-risk` with fix |
| **Tests** | `--generate-tests FILE`, `--auto-commit-tests` |
| **Baseline** | `--baseline FILE`, `--save-baseline FILE` |
| **Notify** | `--notify-slack URL`, `--notify-teams URL` |

**Project defaults** — Values in **`.aicritic.yaml`** are applied when discovered walking up from the target path; CLI flags override them (`project_config.py`).

---

## Outputs

| Format | Flag | Notes |
|--------|------|--------|
| Markdown | `--output` (default filename in config) | Human-readable report |
| HTML | `--html` | Self-contained report with styling |
| JSON | `--json` | Structured machine output |
| SARIF | `--sarif` | GitHub code scanning–compatible (see [FEATURES.md](FEATURES.md)) |

---

## Diff, baseline, and suppressions

- **`--diff REF`** — Only files changed between `REF` and `HEAD` (via git).
- **`--baseline` / `--save-baseline`** — Track known findings and surface **new** issues only (fingerprints in `report/baseline.py` logic — see [FEATURES.md](FEATURES.md) §5).
- **Inline suppression** — Comments such as `# aicritic: accepted-risk <reason>` on or above flagged lines. Suppressed items are listed separately for audit; they do not satisfy “fix the code” but keep visibility for leads ([FEATURES.md](FEATURES.md) §6).

---

## Auto-fix, PRs, and tests

- **`--fix`** applies critic-driven changes; **`--dry-run`** shows diffs without writing.
- **`--fix --pr`** creates a branch, pushes, and opens a GitHub PR with review comments.
- **`--generate-tests`** writes suggested tests for high-risk gaps; **`--auto-commit-tests`** must be set explicitly to allow committing generated tests.

Backups for fixed files go under **`.aicritic_backup/<timestamp>/`** (`aicritic.py`).

---

## CI policy gate

```bash
python aicritic.py ci <path>
```

- Reads **`.aicritic-policy.yaml`** (unless `--policy FILE`). Typical keys: `block_on`, `tool`, `min_risk`, `diff_only`, `skip_checker`, **`min_coverage`** (optional coverage floor — failure can exit **2**).
- In GitHub Actions, **`GITHUB_BASE_REF`** is used to infer diff scope when `diff_only` is true.
- Prints **`::error` / `::warning`** annotations and a **step summary** when `GITHUB_STEP_SUMMARY` is set.
- Exit codes: **0** pass, **1** blocking findings, **2** coverage gate failure when configured.

Workflow example: `.github/workflows/aicritic.yml`. Details: [runbooks/ci-cd.md](runbooks/ci-cd.md).

---

## Agent mode

Claude uses tools (`agent/tools.py`) to read files, run analysis stages, apply fixes, open PRs, run shell checks, save baselines, etc. Bounded by **`--max-steps`** (default 12).

```bash
python aicritic.py agent "scan for secrets and list HIGH findings" . --tool secrets_scan
```

---

## VS Code Copilot extension

Run the API server:

```bash
uvicorn server:app --reload --port 8000
```

Register your GitHub App / extension endpoint per [runbooks/copilot-extension.md](runbooks/copilot-extension.md). Requests can be verified with signatures; **`AICRITIC_DEV_MODE=true`** disables verification for local dev only.

---

## Configuration files

| File | Purpose |
|------|---------|
| `.env` | `GITHUB_TOKEN`, optional `AICRITIC_*` (see `.env.example`) |
| `.aicritic.yaml` | Repo defaults: tool, languages, baseline paths, notify webhooks, etc. |
| `.aicritic-policy.yaml` | CI gate rules |
| `.aicriticignore` | Glob excludes for inputs (like `.gitignore`) |

---

## Cache, notifications, hooks, audit

- **Cache** — Stage results cached under **`.aicritic_cache/`** (TTL via `AICRITIC_CACHE_TTL`, directory via `AICRITIC_CACHE_DIR`). Disable in CI with `TTL=0`. Clear with **`python aicritic.py cache-clear`**.
- **Slack / Teams** — `--notify-slack`, `--notify-teams`, or YAML keys (`report/notify.py`).
- **Pre-commit** — See `.pre-commit-hooks.yaml` and [FEATURES.md](FEATURES.md) §15.
- **Audit log** — `AICRITIC_AUDIT_LOG` for JSONL request logs (`copilot/audit.py`).

---

## Custom roles and project layout

- **Custom roles** — Markdown with optional YAML frontmatter (`mode`, `strictness`, `min_risk`, `model`, …) plus body text appended to prompts — [FEATURES.md](FEATURES.md) §16.
- **Repo map** (high level): `pipeline/` (stages), `inputs/` (loading, diff, suppressions), `report/` (formats, SARIF, PR), `agent/` (loop + tools), `copilot/` (HTTP + streaming), `tools/` (prompt packs per profile), `roles/` (default prompts), `benchmarks/` (sample cases).

---

## Documentation

| Document | Contents |
|----------|----------|
| [FEATURES.md](FEATURES.md) | Single feature reference: quick map, **Mermaid workflow diagrams**, full detail |
| [index.html](index.html) | Same workflow diagrams in a browser (offline-capable after CDN load) |
| [runbooks/quickstart.md](runbooks/quickstart.md) | First run |
| [runbooks/cli.md](runbooks/cli.md) | CLI details |
| [runbooks/ci-cd.md](runbooks/ci-cd.md) | GitHub Actions + policy |
| [runbooks/copilot-extension.md](runbooks/copilot-extension.md) | Copilot extension setup |
| [runbooks/org-deployment.md](runbooks/org-deployment.md) | Org-wide rollout |
| [runbooks/agent.md](runbooks/agent.md) | Agent mode |
| [benchmarks/README.md](benchmarks/README.md) | Benchmark harness |

# aicritic — Full Feature Reference

A comprehensive listing of every capability in aicritic, from the core pipeline
through outputs, surfaces, CI integration, and extensibility.

---

## 0. Agent Mode *(new)*

The highest-level surface: give aicritic a task in plain English; Claude Opus
drives the pipeline autonomously using tool-use until the task is done.

```bash
# Review changed files and fix anything high-risk
python aicritic.py agent "review my PR and fix high-risk issues" . --min-risk high

# Full security scan with auto-PR
python aicritic.py agent "scan for secrets and open a PR with fixes" ./src --tool secrets_scan

# Verify fixes with tests before opening PR
python aicritic.py agent "check error handling, fix it, run pytest, then open a PR" ./src
```

In Copilot Chat, append `@agent` to hand control to the agent loop:

```
@aicritic @agent review my changes and fix the critical issues
```

### How it works

```
User task (natural language)
    │
    ▼
Claude Opus — decides what to do next
    │
    ├─ get_changed_files(ref)   → loads only changed files
    ├─ read_files(lang?)        → loads full target
    ├─ run_analysis(tool)       → Sonnet → Gemini → Opus pipeline
    ├─ apply_fixes(min_risk)    → deterministic patches + LLM rewrite
    ├─ run_shell(command)       → linter / tests / syntax check
    ├─ open_pr(title?)          → branch + push + GitHub PR
    ├─ read_file / write_file   → targeted single-file edits
    └─ save_baseline(path)      → persist current findings
    │
    ▼
Final summary — what was found, fixed, and where the PR is
```

### Available agent tools

| Tool | What it does |
|------|-------------|
| `get_changed_files(ref)` | Load files changed since `ref` (git diff) |
| `read_files(languages?)` | Load all source files in the target |
| `run_analysis(tool?, skip_checker?)` | Run the full 3-model pipeline |
| `apply_fixes(min_risk?)` | Apply critic recommendations to disk |
| `open_pr(title?)` | Push branch + open GitHub PR |
| `read_file(path)` | Read a single file |
| `write_file(path, content)` | Write a single file |
| `run_shell(command, timeout?)` | Run linter / tests / syntax check |
| `save_baseline(path?)` | Save findings fingerprints for future delta runs |

### Safety limits

- `--max-steps N` (default 12) — hard ceiling on tool-call iterations
- Fixes are backed up to `.aicritic_backup/<timestamp>/` before any write
- `open_pr` is only called when the task explicitly requests a PR
- `run_shell` is sandboxed to the target directory

---

## 1. Core Pipeline

### Three-model critic chain

| Stage | Model | Role |
|-------|-------|------|
| **Analyst** | Claude Sonnet | Primary code review — finds issues, assigns risk levels |
| **Checker** | Gemini | Cross-verification — confirms, challenges, and catches misses |
| **Critic** | Claude Opus | Arbiter — reconciles both, assigns final risk, orders recommendations |
| **Fixer** *(optional)* | Claude Sonnet | Applies critic recommendations back to source files |

No single model has the final word. Disagreements are explicitly resolved by Opus.

### Three execution modes

| Mode | Command | Time | When to use |
|------|---------|------|-------------|
| Sequential (default) | `check ./src` | ~90s | Full accuracy, demos, non-urgent review |
| Parallel | `check ./src --parallel` | ~50s | Speed matters, both models independent |
| Fast | `check ./src --skip-checker` | ~20s | CI fast-path, Gemini rate-limited |

### Graceful checker degradation

If the Gemini cross-check stage fails for any reason (rate limit, timeout, API
outage), the pipeline **never crashes**. Instead:

- Chat/console shows `⚠ Checker stage unavailable — <reason>`
- Claude Opus is told the cross-check was skipped and applies extra scrutiny
- The user always receives an answer — flagged, but never empty

### Context-window critic (token optimisation)

Opus does **not** receive the full source code. It receives:

- A compact ±5-line window around each flagged line range (overlapping ranges
  merged per file)
- The full analyst JSON
- The full checker JSON (or a skipped notice)

This cuts critic input tokens by ~40% without affecting arbitration quality.

### Auto-batching for large codebases

When the source set exceeds ~40 kB, aicritic automatically splits it into
batches. The analyst and checker run per batch; findings are merged before
Opus arbitrates once. Progress lines show `[batch 1/3]…`. No flag required.

---

## 2. Analysis Tools

Ten built-in tool profiles, each with specialised system prompts for the
analyst stage:

| Bucket | Tool | What it checks |
|--------|------|----------------|
| **Ship Safety** | `migration_safety` | Data loss, lock contention, missing rollbacks in DB migrations |
| **Ship Safety** | `secrets_scan` | Hardcoded credentials, API keys, tokens, connection strings |
| **Code Confidence** | `code_coverage` | Untested paths, missing branch coverage (needs `coverage.xml`) |
| **Code Confidence** | `error_handling` | Swallowed exceptions, bare `except`, missing timeouts, silent failures |
| **Review Depth** | `pr_review` | Regressions, logic errors, missing tests for new code |
| **Review Depth** | `test_quality` | Meaningless assertions, happy-path-only tests, brittle fixtures |
| **Codebase Health** | `dependency_audit` | CVEs, outdated packages, licence conflicts, transitive bloat |
| **Codebase Health** | `performance` | N+1 queries, blocking I/O, inefficient loops, missing caching |
| **Infrastructure** | `dockerfile_review` | Root user, unpinned tags, baked secrets, bloat, missing health checks |
| **Infrastructure** | `iac_review` | Overpermissive IAM, public buckets, missing encryption, open security groups |

The Copilot Extension auto-detects the tool from keywords in the user's
message — no flag required in chat.

---

## 3. Fixer Stage

### Two-phase strategy

Activated with `--fix`. Uses a fast deterministic phase before calling an LLM:

| Phase | Method | When it applies |
|-------|--------|-----------------|
| **Phase 1 — Literal patch** | `str.replace(find, replace, 1)` | Critic provided `find`/`replace` with `confidence: high` and `find` appears exactly once in the file |
| **Phase 2 — LLM rewrite** | Claude Sonnet rewrites the file | Everything the literal phase could not apply (ambiguous, multi-location, architectural) |

Console output shows `N literal patch(es) (deterministic)` when Phase 1 fires.
Skipped items print `→ reason` so you always know what the fixer declined.

### Dry run

```bash
python aicritic.py check ./src --fix --dry-run
```

Shows a unified diff per file — no files written.

### Backup

When `--fix` is confirmed, originals are backed up to
`.aicritic_backup/<timestamp>/` before any file is touched.

### Auto-PR

```bash
python aicritic.py check ./src --fix --pr
```

After applying fixes locally, aicritic:
1. Creates branch `aicritic/fix-<tool>-<timestamp>`
2. Commits the modified files
3. Pushes to `origin`
4. Opens a PR against the default branch via the GitHub REST API

Requires `GITHUB_TOKEN` with `repo` write scope. Falls back with a clear
error message if any step fails — local fixes are still applied regardless.

---

## 4. Diff Mode

```bash
python aicritic.py check . --diff main
python aicritic.py check . --diff HEAD~5
python aicritic.py check . --diff origin/main
```

Restricts the file set to only those changed between `<REF>` and HEAD.
Combined with `--skip-checker`, delivers a ~15-second PR-scoped review.

Internally parses unified-diff hunk headers to record which line ranges
changed — the pipeline only receives and analyses those.

---

## 5. Baseline / Delta Mode

```bash
# Save the current state once
python aicritic.py check ./src --save-baseline .aicritic_baseline.json

# Future runs: only surface new findings
python aicritic.py check ./src --baseline .aicritic_baseline.json
```

Findings are fingerprinted by `(file, line_range, description-prefix)`.
Anything in the baseline is silently suppressed; only new findings reach the
report and the CI exit code.

**Use case:** legacy codebases with existing debt. CI gates on regressions
only, not the pre-existing 200 warnings.

---

## 6. Risk Filtering

```bash
python aicritic.py check ./src --min-risk high
```

Filter applies at output time (not during pipeline execution) so you can
re-run with a lower threshold without a fresh API call. Can also be set
persistently in a custom role markdown file.

Risk levels: `low` → `medium` → `high` → `critical`

---

## 7. Outputs

| Output | Flag | Format |
|--------|------|--------|
| Console | *(always)* | Rich colour-coded, risk-level highlighted |
| Markdown report | `--output FILE` | Analyst + checker + critic sections |
| JSON report | `--json FILE` | Full run payload — machine-readable, pipeable |
| HTML report | `--html FILE` | Self-contained single-file, inline CSS, risk badges |
| SARIF | `--sarif FILE` | SARIF 2.1.0 JSON for GitHub code-scanning |
| Baseline | `--save-baseline FILE` | JSON fingerprint list for delta runs |
| Auto-PR | `--pr` | GitHub PR with branch, diff, and critic summary |
| Backup | *(with `--fix`)* | Original files under `.aicritic_backup/<timestamp>/` |
| Slack notification | `--notify-slack URL` | Block-kit message with verdict, top findings |
| Teams notification | `--notify-teams URL` | Connector card with facts, top findings |

### SARIF / GitHub code-scanning

```bash
python aicritic.py check ./src --sarif aicritic.sarif
```

Risk → SARIF level mapping:

| aicritic risk | SARIF level | PR annotation |
|---------------|-------------|---------------|
| critical, high | `error` | Red dot — can block merge |
| medium | `warning` | Yellow dot |
| low | `note` | Blue dot |

Dismissed alerts are tracked across runs by GitHub natively — no custom
database needed.

---

## 8. CI Integration

### Fast PR review (no noise, no legacy debt)

```yaml
- run: python aicritic.py check .
       --diff ${{ github.event.pull_request.base.ref }}
       --baseline .aicritic_baseline.json
       --min-risk high
       --skip-checker
       --sarif aicritic.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: aicritic.sarif
```

### Overnight auto-fix bot (scheduled workflow)

```yaml
- run: python aicritic.py check ./src --fix --pr --min-risk high
  env:
    GITHUB_TOKEN: ${{ secrets.AICRITIC_GITHUB_TOKEN }}
```

Finds high-risk issues, fixes what it can deterministically, and opens a PR
for human review every night.

---

## 9. Copilot Extension Surface

Users type `@aicritic check this code` in VS Code or GitHub.com Copilot Chat.
The full Sonnet → Gemini → Opus chain runs server-side; results stream back
stage by stage.

### Tool auto-detection from keywords

| Keywords in the message | Tool selected |
|-------------------------|---------------|
| secret, credential, hardcoded, api key | `secrets_scan` |
| coverage, untested, branch coverage | `code_coverage` |
| migration, alter table, rollback | `migration_safety` |
| performance, slow, n+1, blocking | `performance` |
| error handling, exception, timeout | `error_handling` |
| dependency, requirements, cve, licence | `dependency_audit` |
| pull request, pr review, regression | `pr_review` |
| test quality, flaky, assertion | `test_quality` |
| *(anything else)* | `security_review` |

### Streaming behaviour

Results stream into chat as each stage completes — Sonnet's findings appear
while Gemini is still running. No waiting for all three to finish.

---

## 10. Multi-Language Support

aicritic analyses any combination of supported languages — not just Python.

| Language | Extensions |
|----------|------------|
| Python | `.py` |
| JavaScript | `.js`, `.mjs`, `.cjs` |
| TypeScript | `.ts`, `.tsx` |
| Go | `.go` |
| Java | `.java` |
| Ruby | `.rb` |
| Rust | `.rs` |
| C# | `.cs` |
| PHP | `.php` |
| Kotlin | `.kt` |
| Swift | `.swift` |
| Shell | `.sh`, `.bash` |
| Dockerfile | `Dockerfile`, `.dockerfile` |
| Terraform / HCL | `.tf`, `.tfvars` |
| YAML | `.yml`, `.yaml` |
| SQL | `.sql` |

### Language filter

```bash
# Only TypeScript and Python files
python aicritic.py check ./src --lang typescript --lang python

# Only Dockerfiles
python aicritic.py check . --tool dockerfile_review --lang dockerfile
```

### `.aicriticignore`

Place a `.aicriticignore` file at the target directory root to exclude files
using gitignore-style glob patterns:

```
# .aicriticignore
*_test.go
migrations/
vendor/
**/*.generated.py
```

---

## 11. Project Config File

```yaml
# .aicritic.yaml — checked into the repo root
tool: secrets_scan
min_risk: high
skip_checker: false
parallel: true
languages:
  - python
  - typescript
notify_slack: https://hooks.slack.com/services/YOUR/WEBHOOK/URL
baseline: .aicritic_baseline.json
sarif: aicritic.sarif
```

aicritic searches upward from the target directory for `.aicritic.yaml`.
CLI flags always override the config file — teams set sensible defaults,
individuals override per run. No YAML library dependency — uses a built-in
minimal parser.

---

## 12. Extensibility

### Custom role profiles

Every model in the chain is controlled by a markdown file with YAML frontmatter:

```markdown
---
model: claude-opus-4-7
strictness: high
min_risk: medium
focus: security
---
Your extra instructions here…
```

Override the default roles with `--roles ./my-profile` or `--tool <name>` to
use a built-in tool's profile.

### Custom tool profiles

A "tool" is just a directory under `tools/` containing three role files
(`analyst.md`, `checker.md`, `critic.md`). Create any number of custom tools
without touching Python code.

---

## 13. Benchmark Harness

```bash
python benchmarks/run.py                        # all cases
python benchmarks/run.py --case sql_injection   # one case
python benchmarks/run.py --output latest.json   # persist results
```

Measures **precision** and **recall** against three known-flawed fixture repos:

| Case | Tool | What it tests |
|------|------|---------------|
| `sql_injection` | `security_review` | String-format SQL injection in two query patterns |
| `hardcoded_secret` | `secrets_scan` | Database password + API keys committed in source |
| `missing_timeout` | `error_handling` | `requests.get/post` calls with no timeout argument |

Ground truth is defined in `benchmarks/ground_truth.json` — add new cases
without any Python by editing that file and dropping a fixture directory.

---

## 14. Security — Copilot Extension

| Feature | Detail |
|---------|--------|
| **ECDSA-P256 signature verification** | Every request from GitHub is verified before processing |
| **Dev mode bypass** | `AICRITIC_DEV_MODE=true` skips signature check for local development |
| **No code storage** | Source snippets from Copilot chat are never persisted |
| **Token scope** | Only needs a fine-grained PAT with Copilot Enterprise access — no repo permissions |

---

## 15. CLI Flags — Quick Reference

```
python aicritic.py check <target> [flags]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--tool NAME` | security_review | Built-in tool profile |
| `--lang LANG` | all | Language filter (repeatable) |
| `--coverage FILE` | — | `coverage.xml` from `coverage xml` |
| `--min-risk LEVEL` | low | `low` / `medium` / `high` — filter threshold |
| `--skip-checker` | off | Sonnet → Opus only (~20s) |
| `--parallel` | off | Sonnet + Gemini in parallel (~50s) |
| `--fix` | off | Run fixer stage after critic |
| `--dry-run` | off | With `--fix`: show diff only, no writes |
| `--pr` | off | With `--fix`: push branch and open GitHub PR |
| `--diff REF` | — | Restrict to files changed since REF |
| `--baseline FILE` | — | Suppress findings already in this baseline |
| `--save-baseline FILE` | — | Write current findings as a new baseline |
| `--sarif FILE` | — | Write SARIF 2.1.0 for GitHub code-scanning |
| `--json FILE` | — | Write full run as JSON |
| `--html FILE` | — | Write self-contained HTML report |
| `--notify-slack URL` | — | Post summary to Slack Incoming Webhook |
| `--notify-teams URL` | — | Post summary to Teams webhook |
| `--roles DIR` | `roles/` | Custom roles directory |
| `--output FILE` | `aicritic_report.md` | Markdown report path |

---

## 16. Prerequisites & Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | Fine-grained PAT with Copilot Enterprise access |
| `AICRITIC_DEV_MODE` | Dev only | `true` to skip ECDSA signature check |

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | |
| pip packages | — | `pip install -r requirements.txt` |
| GitHub account | — | Must have Copilot Enterprise access |
| ngrok | any | Copilot Extension only — exposes localhost to GitHub |

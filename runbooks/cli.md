# Runbook — aicritic CLI

## Commands

```
aicritic check <target>       Analyse source files
aicritic ci    <target>       CI gate — exits 1 on blocking findings
aicritic agent "<task>" <target>  Autonomous agent mode
aicritic cache-clear          Delete cached pipeline results
```

---

## `aicritic check`

Full analysis with console output and report file.

### Input

```bash
python aicritic.py check <target> [options]
```

`<target>` — a `.py` file or any directory. Subdirectories are walked recursively.
Non-source files and common noise directories (`__pycache__`, `node_modules`,
`.venv`, `.git`) are skipped automatically.

### Tool selection

```bash
--tool NAME        Built-in profile (see list below)
--roles DIR        Directory of custom .md role files (overrides --tool)
```

Available profiles: `security_review` *(default)*, `secrets_scan`,
`error_handling`, `pr_review`, `performance`, `migration_safety`, `test_quality`,
`dependency_audit`, `dockerfile_review`, `iac_review`.

### Language filter

```bash
--lang LANG        Restrict to a language (repeatable)
```

Supported: `python`, `javascript`, `typescript`, `go`, `java`, `ruby`, `rust`,
`csharp`, `php`, `kotlin`, `swift`, `shell`, `dockerfile`, `terraform`, `yaml`, `sql`.

```bash
python aicritic.py check . --lang python --lang typescript
```

### Pipeline control

```bash
--skip-checker     Skip Gemini cross-check (~20s vs ~90s)
--parallel         Run Sonnet + Gemini simultaneously (independent, not sequential)
```

### Risk filtering

```bash
--min-risk LEVEL   Only surface findings at LEVEL and above (low/medium/high)
```

`--min-risk high` is recommended for pre-commit hooks and noisy codebases.

### Diff mode

```bash
--diff REF         Only analyse files changed since REF
```

```bash
python aicritic.py check src/ --diff main
python aicritic.py check src/ --diff HEAD~1
python aicritic.py check src/ --diff origin/main
```

Uses `git diff --name-only <ref>...HEAD` internally.

### Coverage integration

```bash
--coverage FILE    Path to coverage.xml from `coverage xml`
```

Passes line-coverage data to the analyst. The `code_coverage` tool profile
uses this to flag high-risk uncovered paths.

### Baseline

```bash
--baseline FILE      Suppress findings present in this baseline JSON
--save-baseline FILE Save current findings as a new baseline
```

```bash
# First run — save baseline
python aicritic.py check src/ --save-baseline .aicritic_baseline.json

# Later runs — show only new findings
python aicritic.py check src/ --baseline .aicritic_baseline.json
```

### Inline suppression

Add a comment in your source to formally dismiss a finding:

```python
# aicritic: accepted-risk validated upstream in the controller
cursor.execute(raw_sql)

cursor.execute(raw_sql)  # aicritic: accepted-risk ORM handles escaping
```

Suppressed findings are excluded from output but listed in a separate table
in the report so leads can audit what has been accepted.

Works in: Python (`#`), JS/Go/Rust (`//`), CSS/SQL block (`/* */`), SQL line (`--`), INI (`;`).

### Output formats

```bash
--output FILE      Markdown report path (default: aicritic_report.md)
--html   FILE      Also write self-contained HTML report
--json   FILE      Also write JSON report
--sarif  FILE      Also write SARIF 2.1.0 for GitHub code scanning
```

### Explain mode

```bash
--explain          After critic stage, explain WHY + show exact fix for each finding
```

Adds a teaching card per finding: concrete attack scenario, your vulnerable code
verbatim, a corrected version of your specific code, and a one-line rule.

### Notifications

```bash
--notify-slack URL    Post summary to Slack webhook
--notify-teams URL   Post summary to Teams webhook
```

### Fix mode

```bash
--fix              Apply critic recommendations to source files
--dry-run          Show what --fix would change without writing files
--pr               With --fix: create branch, push, open GitHub PR with inline comments
--min-risk LEVEL   Only fix findings at LEVEL and above
```

**Two-phase fixer:**
1. Deterministic literal patches (no LLM) for `confidence: high` find/replace pairs.
2. Claude Sonnet rewrites for ambiguous or multi-location changes.

### All flags at a glance

| Flag | Default | Description |
|------|---------|-------------|
| `target` | *(required)* | File or directory to analyse |
| `--tool` | `security_review` | Built-in tool profile |
| `--roles` | — | Custom roles directory |
| `--lang` | all | Language filter (repeatable) |
| `--diff` | — | Analyse changed files since this git ref |
| `--coverage` | — | Path to coverage.xml |
| `--skip-checker` | false | Skip Gemini |
| `--parallel` | false | Run Sonnet + Gemini in parallel |
| `--min-risk` | low | Minimum risk to surface |
| `--baseline` | — | Suppress known findings |
| `--save-baseline` | — | Save findings as new baseline |
| `--output` | `aicritic_report.md` | Markdown report path |
| `--html` | — | HTML report path |
| `--json` | — | JSON report path |
| `--sarif` | — | SARIF report path |
| `--notify-slack` | — | Slack webhook URL |
| `--notify-teams` | — | Teams webhook URL |
| `--fix` | false | Apply fixes |
| `--dry-run` | false | Show fix diff without writing |
| `--pr` | false | Open GitHub PR with fixes |
| `--explain` | false | Add teaching cards to findings |

---

## `aicritic ci`

CI gate designed for GitHub Actions. Same pipeline as `check` but with CI-specific
output and a meaningful exit code.

```bash
python aicritic.py ci <target> [--policy FILE] [--no-diff]
```

**What it does:**
1. Loads `.aicritic-policy.yaml` from the target directory (auto-discovered).
2. Detects the PR base branch from `GITHUB_BASE_REF` (set automatically in Actions).
3. Runs the pipeline on changed files (or all files with `--no-diff`).
4. Applies inline suppression comments.
5. Emits `::error` / `::warning` annotations for every finding.
6. Writes a Markdown step summary to `$GITHUB_STEP_SUMMARY`.
7. Exits 1 if blocking findings exist, 0 otherwise.

**Flags:**

| Flag | Description |
|------|-------------|
| `target` | Directory to analyse |
| `--policy FILE` | Explicit path to policy file (default: auto-discover) |
| `--no-diff` | Analyse all files, not just changed ones |

**Policy defaults** (if no `.aicritic-policy.yaml` is found):
```
block_on:     [critical, high]
diff_only:    true
min_risk:     low
skip_checker: false
tool:         security_review
```

**Local testing:**
```bash
GITHUB_BASE_REF=main python aicritic.py ci src/
```

---

## `aicritic agent`

Natural-language task runner. See [agent.md](agent.md) for full documentation.

```bash
python aicritic.py agent "review my PR and fix high-risk issues" src/
python aicritic.py agent "scan for hardcoded secrets" . --tool secrets_scan
```

---

## `aicritic cache-clear`

Delete all cached pipeline results.

```bash
python aicritic.py cache-clear
```

Removes all `.json` files from `.aicritic_cache/`. Prints the number removed.
Useful before a clean CI run or after changing role files.

---

## Project config (`.aicritic.yaml`)

Set per-repo defaults. CLI flags always take precedence.

```yaml
tool: secrets_scan
min_risk: medium
skip_checker: false
parallel: false
languages:
  - python
  - typescript
baseline: .aicritic_baseline.json
sarif: aicritic.sarif
output: reports/aicritic_report.md
notify_slack: https://hooks.slack.com/services/...
diff: main
```

aicritic walks up from the target directory to find the file.

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | Required. Fine-grained PAT with Copilot Enterprise access. |
| `AICRITIC_DEV_MODE` | `true` skips signature verification (local dev only). |
| `AICRITIC_CACHE_TTL` | Cache TTL in seconds (default 86400). `0` disables. |
| `AICRITIC_CACHE_DIR` | Override cache directory (default `.aicritic_cache/`). |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `GITHUB_TOKEN is not set` | Missing `.env` | `cp .env.example .env` and add token |
| `401 Unauthorized` | Token expired | Regenerate at github.com → Settings |
| `Could not parse JSON from model` | Model returned prose | Re-run; one-off; check `config.py` prompts if persistent |
| `No files to analyse` | Target is empty or all ignored | Check `.aicriticignore`; verify file extensions |
| Slow first run | No cache yet | Normal; subsequent runs are fast. Use `--skip-checker` for speed |
| Cache not helping | Files or role changed | Cache key includes content; any change invalidates it |

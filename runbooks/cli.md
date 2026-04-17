# CLI Reference

```bash
python aicritic.py check <target>            # analyse files
python aicritic.py ci    <target>            # CI gate — exits 1 on blocking findings
python aicritic.py agent "<task>" <target>   # autonomous agent mode
python aicritic.py cache-clear               # delete cached results
```

---

## I want to scan a file or directory

```bash
python aicritic.py check src/
python aicritic.py check src/db.py
```

`<target>` can be a single file or a directory. Directories are walked recursively.
Files in `__pycache__`, `node_modules`, `.venv`, `.git` are skipped automatically.

---

## I only want to scan what changed

```bash
python aicritic.py check src/ --diff main
python aicritic.py check src/ --diff HEAD~1
python aicritic.py check src/ --diff origin/main
```

Only files changed between the ref and HEAD are loaded. Much faster and less noisy than
a full scan. Use this before every push.

---

## I want to focus on a specific type of problem

```bash
python aicritic.py check src/ --tool security_review   # default
python aicritic.py check src/ --tool secrets_scan
python aicritic.py check src/ --tool error_handling
python aicritic.py check src/ --tool design_review
python aicritic.py check src/ --tool performance
python aicritic.py check src/ --tool test_quality
python aicritic.py check src/ --tool pr_review
python aicritic.py check src/ --tool migration_safety
python aicritic.py check src/ --tool dependency_audit
python aicritic.py check src/ --tool dockerfile_review
python aicritic.py check src/ --tool iac_review
```

`design_review` automatically enables `--explain` and runs the pattern advisor
(God class, Feature Envy, Long Method, Magic Numbers, Deep Nesting, etc.).

---

## I want to understand WHY each finding is dangerous

```bash
python aicritic.py check src/ --explain
```

After the verdict, each finding gets a teaching card:
- The concrete attack scenario or failure mode
- Your exact vulnerable lines (not a generic example)
- A corrected version of your specific code
- A one-sentence rule to carry forward

Adds ~15 seconds. Worth it when onboarding a junior developer or reviewing an unfamiliar codebase.

---

## I want to fix issues automatically

```bash
# See what would change without touching any files
python aicritic.py check src/ --fix --dry-run

# Apply the fixes
python aicritic.py check src/ --fix

# Apply fixes for HIGH and above only
python aicritic.py check src/ --fix --min-risk high

# Apply and open a GitHub PR
python aicritic.py check src/ --fix --pr
```

The fixer works in two phases:
1. **Deterministic patches** — mechanical find/replace for high-confidence fixes (no LLM)
2. **LLM rewrite** — for ambiguous or multi-location changes

You're shown a diff and asked to confirm before any files are written.

---

## I want to ignore noise from existing issues

Save a baseline on the current findings, then future runs only show new ones:

```bash
# First run — save everything as known
python aicritic.py check src/ --save-baseline .aicritic_baseline.json

# Later runs — only new findings
python aicritic.py check src/ --baseline .aicritic_baseline.json
```

---

## I want to suppress a specific finding permanently

Add a comment in the source file on the line before (or the same line as) the flagged code:

```python
# aicritic: accepted-risk @alice 2025-04-17 — parameterized in ORM layer
cursor.execute(raw_sql)
```

Or inline:
```python
cursor.execute(raw_sql)  # aicritic: accepted-risk internal endpoint, no user data
```

The finding is removed from output and shown separately in the report as suppressed.
Works in Python (`#`), JS/Go/Rust (`//`), SQL (`--`), CSS (`/* */`).

---

## I want to run faster

```bash
# Skip the Gemini cross-check (~20s instead of ~90s)
python aicritic.py check src/ --skip-checker

# Run Sonnet and Gemini in parallel (independent, not sequential)
python aicritic.py check src/ --parallel

# Only surface HIGH and CRITICAL (skip low/medium noise)
python aicritic.py check src/ --min-risk high
```

---

## I want to scan specific languages only

```bash
python aicritic.py check . --lang python --lang typescript
```

Supported: `python`, `javascript`, `typescript`, `go`, `java`, `ruby`, `rust`,
`csharp`, `php`, `kotlin`, `swift`, `shell`, `dockerfile`, `terraform`, `yaml`, `sql`.

---

## I want to save the report in different formats

```bash
python aicritic.py check src/ --output report.md       # Markdown (default)
python aicritic.py check src/ --html report.html       # self-contained HTML
python aicritic.py check src/ --json results.json      # machine-readable JSON
python aicritic.py check src/ --sarif scan.sarif       # GitHub code scanning
```

SARIF upload wires findings into the **Security → Code scanning** tab in GitHub,
separate from PR checks.

---

## I want to send a notification when issues are found

```bash
python aicritic.py check src/ --notify-slack https://hooks.slack.com/services/...
python aicritic.py check src/ --notify-teams https://your-teams-webhook-url
```

---

## I want to set defaults so I don't repeat flags every time

Create `.aicritic.yaml` at your repo root:

```yaml
tool: security_review
min_risk: medium
skip_checker: false
diff: main
baseline: .aicritic_baseline.json
output: reports/aicritic_report.md
notify_slack: https://hooks.slack.com/services/...
```

CLI flags always override the file. aicritic walks up from the target directory to find it.

---

## I want to run the CI gate locally before pushing

```bash
GITHUB_BASE_REF=main python aicritic.py ci src/
```

Same pipeline as `check` but uses `.aicritic-policy.yaml` rules and exits 1 on blocking findings.
See [ci-cd.md](ci-cd.md) for the full CI setup.

---

## All flags at a glance

| Flag | Default | What it does |
|------|---------|-------------|
| `--tool NAME` | `security_review` | Analysis profile |
| `--diff REF` | — | Analyse only files changed since REF |
| `--explain` | off | Add WHY + exact fix for each finding |
| `--fix` | off | Apply fixes to source files |
| `--dry-run` | off | Show fix diff without writing files |
| `--pr` | off | With `--fix`: open a GitHub PR |
| `--min-risk LEVEL` | `low` | Only surface `low`/`medium`/`high` and above |
| `--skip-checker` | off | Skip Gemini cross-check (~20s vs ~90s) |
| `--parallel` | off | Run Sonnet + Gemini simultaneously |
| `--lang LANG` | all | Language filter (repeatable) |
| `--baseline FILE` | — | Suppress findings in this baseline |
| `--save-baseline FILE` | — | Save current findings as baseline |
| `--output FILE` | `aicritic_report.md` | Markdown report path |
| `--html FILE` | — | HTML report path |
| `--json FILE` | — | JSON report path |
| `--sarif FILE` | — | SARIF report path |
| `--coverage FILE` | — | coverage.xml for `code_coverage` tool |
| `--notify-slack URL` | — | Post summary to Slack |
| `--notify-teams URL` | — | Post summary to Teams |
| `--roles DIR` | — | Custom roles directory (overrides `--tool`) |

---

## Troubleshooting

**`GITHUB_TOKEN is not set`**
Run `cp .env.example .env` and add your token. Or `export GITHUB_TOKEN=ghp_...` in your shell.

**`401 Unauthorized`**
Your token expired or doesn't have Copilot Enterprise access. Regenerate at github.com → Settings.

**`No files to analyse`**
Check your target path. If using `--diff`, make sure the ref exists (`git log --oneline` to confirm).
Check `.aicriticignore` if you have one.

**`Could not parse JSON from model`**
One-off — the model returned a malformed response. Re-run. If it happens consistently,
check `config.py` for prompt changes.

**First run is slow**
Normal — no cache yet. Subsequent runs on unchanged code are fast.
Use `--skip-checker` to cut 70s off the first run.

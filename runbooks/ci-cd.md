# Runbook — CI/CD Integration

## Overview

`aicritic ci` runs the analysis pipeline and exits with a meaningful code:
- **Exit 0** — no blocking findings, PR can merge
- **Exit 1** — blocking findings exist, PR is blocked

The gate integrates with GitHub Actions to post inline annotations on the PR diff
and a step summary without any extra tooling.

---

## 5-minute setup

### 1. Copy the workflow

The workflow file is already in this repo at `.github/workflows/aicritic.yml`.
Copy it into the target repository:

```bash
mkdir -p .github/workflows
cp /path/to/aicritic/.github/workflows/aicritic.yml .github/workflows/
```

Or create it from scratch:

```yaml
# .github/workflows/aicritic.yml
name: aicritic

on:
  pull_request:
    branches: ["**"]
  push:
    branches: [main, master]

permissions:
  contents: read
  pull-requests: read

jobs:
  security-gate:
    name: security gate
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # required for --diff

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run aicritic CI gate
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          AICRITIC_CACHE_TTL: "0"   # always fresh in CI
        run: python aicritic.py ci .
```

### 2. Add GITHUB_TOKEN to secrets

Go to: **repo → Settings → Secrets and variables → Actions → New repository secret**

Name: `GITHUB_TOKEN`
Value: a fine-grained PAT with Copilot Enterprise access.

*Note: the default `${{ secrets.GITHUB_TOKEN }}` works for read-only operations but
may not have Copilot model access. Use a personal fine-grained PAT for model calls.*

### 3. Set as a required status check

Go to: **repo → Settings → Branches → Branch protection rules → Edit (or Add rule)**

- Enable **Require status checks to pass before merging**
- Search for and add: `aicritic / security gate`
- Enable **Require branches to be up to date before merging**

Once saved, every PR to that branch must pass the aicritic gate before merging.

---

## Policy configuration

Create `.aicritic-policy.yaml` at the repo root to customise blocking behaviour.

```yaml
# .aicritic-policy.yaml

# Risk levels that fail the CI gate and block the PR.
# Remove "high" to only block on CRITICAL findings.
block_on: [critical, high]

# Analysis profile to use.
tool: security_review

# Minimum risk level to include in the report (does not affect blocking).
min_risk: low

# Only analyse files changed in this PR.
# Set to false to scan the full codebase on every PR (slower).
diff_only: true

# Skip the Gemini cross-check for faster runs (~20s vs ~90s).
skip_checker: false
```

If the file is absent, defaults are used: `block_on: [critical, high]`,
`diff_only: true`, all other defaults.

**Recommended policy by team size:**

| Team | Policy |
|------|--------|
| Small (< 5 devs) | `block_on: [critical, high]`, `skip_checker: false` |
| Medium (5–20) | `block_on: [critical, high]`, `skip_checker: true` (faster) |
| Large (20+) | `block_on: [critical]`, `skip_checker: true` (lowest friction) |

---

## What developers see

### In the GitHub Actions tab

A step named **security gate** shows either:
- ✅ green — PASSED
- ❌ red — BLOCKED with the specific findings

### Inline PR annotations

For every finding, the workflow emits a `::error` or `::warning` command:

```
::error file=src/db.py,line=23,title=aicritic [HIGH]::Unsanitized user input...
::warning file=src/auth.py,line=45,title=aicritic [MEDIUM]::Password in log output
```

These appear as **inline annotations on the Files Changed tab** of the PR —
pinned to the exact line — without any additional tooling or configuration.

### Step summary

The workflow writes a Markdown summary to `$GITHUB_STEP_SUMMARY`:

```markdown
## aicritic Security Gate — ❌ BLOCKED

Files analysed: 8
Blocking levels: `critical, high`

### ❌ Blocking findings (1)

| Risk | File | Lines | Description |
|------|------|-------|-------------|
| **HIGH** | `src/db.py` | 23-25 | Unsanitized user input passed to SQL query |

### ℹ️ Below-threshold findings (2)

| Risk | File | Lines | Description |
|------|------|-------|-------------|
| MEDIUM | `src/auth.py` | 45 | Password logged in plaintext |
| LOW    | `src/utils.py` | 12 | Unused import |

### 🔕 Suppressed findings (1)

| Risk | File | Lines | Reason |
|------|------|-------|--------|
| HIGH | `src/legacy.py` | 88 | reviewed by @lead — migration tracked in JIRA-456 |
```

---

## Suppressing findings

When a lead or senior developer reviews a finding and determines it is acceptable,
they add a suppression comment in the source file:

```python
# aicritic: accepted-risk reviewed by @lead 2025-04-17 — internal endpoint, no user data
cursor.execute(raw_query, params)
```

Or on the same line:

```python
cursor.execute(raw_query, params)  # aicritic: accepted-risk ORM validates all inputs
```

**Effect in CI:**
- The finding is removed from the blocking count and does not block the PR.
- It appears in the step summary's 🔕 Suppressed table with the reason.
- It remains in the full report for audit purposes.

**Best practice:** include the reviewer's name and date in the reason. This creates
a searchable audit trail:

```python
# aicritic: accepted-risk @alice 2025-04-17 — false positive, parameterized in ORM layer
```

---

## Scanning the full codebase (not just diffs)

Set `diff_only: false` in the policy, or pass `--no-diff`:

```bash
python aicritic.py ci . --no-diff
```

Useful for:
- Scheduled nightly scans
- Running after a new tool profile is added
- Initial baseline creation

**Scheduled scan example:**
```yaml
on:
  schedule:
    - cron: "0 2 * * 1"   # every Monday at 2am

jobs:
  full-scan:
    steps:
      - run: python aicritic.py ci . --no-diff
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          AICRITIC_CACHE_TTL: "0"
```

---

## Multiple tool profiles in CI

Run different profiles on different paths:

```yaml
jobs:
  secrets:
    steps:
      - run: python aicritic.py ci . --policy .aicritic-policy-secrets.yaml

  security:
    steps:
      - run: python aicritic.py ci src/ --policy .aicritic-policy-security.yaml
```

```yaml
# .aicritic-policy-secrets.yaml
block_on: [high, critical]
tool: secrets_scan
diff_only: false   # always scan entire codebase for secrets
skip_checker: true
```

---

## SARIF upload (optional)

Upload findings to GitHub code scanning for persistent tracking:

```yaml
- name: Run aicritic
  run: python aicritic.py check . --sarif aicritic.sarif --min-risk low
  continue-on-error: true   # don't fail here — let the upload happen first

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: aicritic.sarif
```

This creates a permanent security alert in the **Security → Code scanning** tab,
separate from the PR gate.

---

## Local testing

Test the CI gate locally before pushing:

```bash
# Simulate GitHub Actions environment
GITHUB_BASE_REF=main python aicritic.py ci src/

# Test with a specific policy file
python aicritic.py ci src/ --policy .aicritic-policy.yaml

# Test without diff filtering
python aicritic.py ci src/ --no-diff
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Gate always passes | No `.aicritic-policy.yaml` found | Check file location — must be at repo root |
| `No files to analyse` | `diff_only: true` but no changed files | Ensure `fetch-depth: 0` in checkout step |
| `GITHUB_TOKEN is not set` | Secret not configured | Add to repo secrets (Settings → Secrets → Actions) |
| Gate passes but annotations missing | Permissions issue | Add `pull-requests: write` to workflow permissions |
| `401 Unauthorized` from model API | Token lacks Copilot access | Use a fine-grained PAT with Copilot Enterprise scope |
| Slow CI runs | Full codebase scan | Set `diff_only: true` or `skip_checker: true` in policy |

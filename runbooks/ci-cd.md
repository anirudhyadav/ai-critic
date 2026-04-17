# CI/CD Setup

aicritic runs as a GitHub Actions gate that blocks PRs with high-risk findings
and posts inline annotations directly on the diff — no extra tooling needed.

---

## I want to add a CI gate to my repo

**Step 1 — Copy the workflow**

```bash
mkdir -p .github/workflows
cp /path/to/aicritic/.github/workflows/aicritic.yml .github/workflows/
```

Or create it manually:

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
          fetch-depth: 0        # required for diff mode

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run aicritic
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          AICRITIC_CACHE_TTL: "0"
        run: python aicritic.py ci .
```

**Step 2 — Add GITHUB_TOKEN to secrets**

Settings → Secrets and variables → Actions → New repository secret.

Name: `GITHUB_TOKEN`
Value: a fine-grained PAT with Copilot Enterprise access.

> The default `${{ secrets.GITHUB_TOKEN }}` works for repo operations but may
> not have Copilot model access. Use a personal fine-grained PAT for model calls.

**Step 3 — Make it a required check**

Settings → Branches → Branch protection rules → Edit (or Add rule):
- Enable **Require status checks to pass before merging**
- Add: `aicritic / security gate`
- Enable **Require branches to be up to date before merging**

That's it. Every PR to that branch is now gated.

---

## I want to control what blocks a PR

Create `.aicritic-policy.yaml` at your repo root:

```yaml
# .aicritic-policy.yaml

# Risk levels that fail the gate and block the PR
block_on: [critical, high]

# Analysis profile
tool: security_review

# Only scan files changed in this PR (faster, less noise)
diff_only: true

# Skip Gemini cross-check for faster runs
skip_checker: false
```

If the file is absent, defaults are used: `block_on: [critical, high]`, `diff_only: true`.

**Recommended settings by team size:**

| Team | Recommended policy |
|------|--------------------|
| < 5 devs | `block_on: [critical, high]`, `skip_checker: false` |
| 5–20 devs | `block_on: [critical, high]`, `skip_checker: true` (faster) |
| 20+ devs | `block_on: [critical]`, `skip_checker: true` (lowest friction) |

---

## I want to see what developers see

**In the Actions tab:** a step called `security gate` shows ✅ PASSED or ❌ BLOCKED.

**On the Files Changed tab:** inline annotations pinned to exact lines:

```
⛔ aicritic [HIGH] — Unsanitized user input passed to SQL query   db.py line 23
⚠  aicritic [MEDIUM] — Password logged in plaintext              auth.py line 45
```

**In the step summary:** a Markdown table of all findings, split into blocking and below-threshold:

```
## aicritic Security Gate — ❌ BLOCKED

Files analysed: 8
Blocking levels: critical, high

### ❌ Blocking findings (1)
| Risk | File | Lines | Description |
| HIGH | src/db.py | 23-25 | Unsanitized user input passed to SQL query |

### ℹ️ Below-threshold findings (2)
| Risk | File | Lines | Description |
| MEDIUM | src/auth.py | 45 | Password logged in plaintext |
```

---

## I want to suppress a finding the team has reviewed and accepted

Add a comment in the source file:

```python
# aicritic: accepted-risk @alice 2025-04-17 — internal endpoint, no user data
cursor.execute(raw_sql)
```

Or inline:
```python
cursor.execute(raw_sql)  # aicritic: accepted-risk ORM validates all inputs
```

**What happens:**
- The finding no longer blocks the PR
- It appears in the **🔕 Suppressed** table in the step summary so leads can audit it
- It stays in the full JSON report for compliance

**Best practice:** include reviewer name and date. This creates a searchable audit trail as the codebase grows.

---

## I want to run a full scan (not just changed files)

```bash
# In .aicritic-policy.yaml
diff_only: false
```

Or pass `--no-diff` at the command line:

```bash
python aicritic.py ci . --no-diff
```

Useful for:
- Nightly scans of the full codebase
- Running after you add a new tool profile
- Creating an initial baseline

**Scheduled nightly scan:**
```yaml
on:
  schedule:
    - cron: "0 2 * * 1"   # every Monday at 2 AM

jobs:
  full-scan:
    steps:
      - run: python aicritic.py ci . --no-diff
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          AICRITIC_CACHE_TTL: "0"
```

---

## I want to run different scan profiles on different parts of the repo

```yaml
jobs:
  secrets:
    name: secrets scan
    steps:
      - run: python aicritic.py ci . --policy .aicritic-policy-secrets.yaml

  security:
    name: security gate
    steps:
      - run: python aicritic.py ci src/ --policy .aicritic-policy-security.yaml
```

```yaml
# .aicritic-policy-secrets.yaml
tool: secrets_scan
block_on: [high, critical]
diff_only: false      # always scan the full codebase for secrets
skip_checker: true
```

---

## I want findings in GitHub code scanning (persistent alerts)

```yaml
- name: Run aicritic
  run: python aicritic.py check . --sarif aicritic.sarif --min-risk low
  continue-on-error: true    # let the upload happen even if gate fails

- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: aicritic.sarif
```

Findings appear permanently in **Security → Code scanning**, separate from PR checks.

---

## I want to test the gate locally before pushing

```bash
# Simulate the GitHub Actions environment
GITHUB_BASE_REF=main python aicritic.py ci src/

# Test with your policy file
python aicritic.py ci src/ --policy .aicritic-policy.yaml

# Test without diff filtering
python aicritic.py ci src/ --no-diff
```

Exit 0 = would pass. Exit 1 = would block.

---

## Troubleshooting

**Gate always passes even with obvious issues**
Check that `.aicritic-policy.yaml` is at the repo root, not in a subdirectory.

**`No files to analyse`**
`diff_only: true` but the checkout has no diff. Make sure `fetch-depth: 0` is set in the
`actions/checkout` step — without it, GitHub Actions checks out a shallow clone with no history.

**Annotations not appearing on the PR diff**
Add `pull-requests: write` to the workflow permissions block.

**`GITHUB_TOKEN is not set`**
The secret isn't configured. Go to Settings → Secrets → Actions and add it.

**`401 Unauthorized` from model API**
The default `${{ secrets.GITHUB_TOKEN }}` doesn't have Copilot model access.
Use a fine-grained PAT (personal token, not the Actions bot token).

**Gate is slow**
Add `skip_checker: true` to your policy. This cuts ~70 seconds by skipping the Gemini stage.
Also check `diff_only: true` is set — full scans on large codebases take much longer.

# Quickstart — aicritic in 5 minutes

## 1. Install

```bash
git clone https://github.com/anirudhyadav/ai-critic
cd ai-critic
pip install -r requirements.txt
```

## 2. Set your token

```bash
cp .env.example .env
```

Open `.env` and set:
```
GITHUB_TOKEN=ghp_your_token_here
```

You need a **fine-grained personal access token** with Copilot Enterprise access.
Generate one at: github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens.

## 3. Run your first analysis

```bash
python aicritic.py check src/
```

You'll see output like:
```
  [1/3] Claude Sonnet  (primary analyst)
  ● HIGH    src/db.py:23  Unsanitized user input passed to SQL query
  ● MEDIUM  src/auth.py:45  Password logged in plaintext

  [2/3] Gemini  (cross-checker)
  ✓ Confirmed: SQL injection at db.py:23
  ✗ Disagrees: auth.py:45 is low risk (logging is internal only)

  [3/3] Claude Opus  (critic verdict)
  Verdict: HIGH — 1 confirmed critical issue

  Recommendations:
  1. [HIGH] Use parameterized queries in db.py line 23
  2. [MEDIUM] Remove password from log statement in auth.py line 45
```

A Markdown report is saved to `aicritic_report.md`.

## 4. Understand what's wrong (junior developer)

```bash
python aicritic.py check src/ --explain
```

Adds a teaching card to every finding — what the attack looks like, your
vulnerable code, the exact fix, and a rule to remember.

## 5. Fix issues automatically

```bash
# Preview the changes without writing them
python aicritic.py check src/ --fix --dry-run

# Apply the fixes
python aicritic.py check src/ --fix

# Apply and open a GitHub PR
python aicritic.py check src/ --fix --pr
```

## 6. Run faster on your changed files

Before pushing, run only against what you changed:
```bash
python aicritic.py check src/ --diff main
python aicritic.py check src/ --diff HEAD~1
```

## 7. Add a CI gate (5 minutes)

Copy the workflow into your repo:
```bash
mkdir -p .github/workflows
cp /path/to/aicritic/.github/workflows/aicritic.yml .github/workflows/
```

Add `GITHUB_TOKEN` to your repo secrets (Settings → Secrets → Actions).

Create the policy file:
```yaml
# .aicritic-policy.yaml
block_on: [critical, high]
diff_only: true
```

Set the workflow as a required status check in your branch protection rules.
Done — every PR is now gated.

## Common options

```bash
--tool secrets_scan      # scan for hardcoded credentials
--tool error_handling    # check exception handling
--min-risk high          # only show HIGH and CRITICAL
--skip-checker           # skip Gemini (20s instead of 90s)
--explain                # add WHY + fix for each finding
--diff main              # only changed files since main
--fix                    # apply fixes automatically
--html report.html       # also save an HTML report
--sarif scan.sarif       # SARIF for GitHub code scanning
```

## Next steps

- [CLI reference](cli.md) — all flags explained
- [CI/CD setup](ci-cd.md) — full GitHub Actions guide
- [Copilot Extension](copilot-extension.md) — use `@aicritic` in VS Code
- [Agent mode](agent.md) — natural language tasks

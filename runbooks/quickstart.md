# Get started with aicritic

You'll have your first analysis running in under 5 minutes.

---

## Step 1 — Install

```bash
git clone https://github.com/anirudhyadav/ai-critic
cd ai-critic
pip install -e .
cp .env.example .env
```

Open `.env` and paste your GitHub token:

```
GITHUB_TOKEN=ghp_your_token_here
```

**Where to get a token:** github.com → Settings → Developer settings →
Personal access tokens → Fine-grained tokens. You need Copilot Enterprise access.

**Optional: set up the `@aicritic` alias**

```bash
# Add to your ~/.zshrc or ~/.bashrc
source /path/to/ai-critic/aicritic-init.sh
```

After that, `@aicritic "task" target` works exactly like `aicritic "task" target`.

---

## Step 2 — Run your first analysis

Point it at a file or directory:

```bash
python aicritic.py check src/
```

You'll see three stages run, then a verdict:

```
  [1/3] Claude Sonnet
  ● HIGH    src/db.py:23    Unsanitized user input passed to SQL query
  ● MEDIUM  src/auth.py:45  Password logged in plaintext

  [2/3] Gemini
  ✓ Confirmed: SQL injection at db.py:23
  ✗ Disagrees: auth.py:45 is low risk (logging is internal only)

  [3/3] Claude Opus
  Verdict: HIGH — 1 confirmed issue

  Recommendations:
  1. [HIGH]   Use parameterized queries in db.py line 23
  2. [MEDIUM] Remove password from log statement in auth.py line 45

Report saved: aicritic_report.md
```

---

## I want to understand WHY something is a problem

```bash
python aicritic.py check src/ --explain
```

After the verdict, you get a teaching card for each finding:

```
  ⚠ Why this is dangerous
    An attacker sends ' OR 1=1 -- as the username.
    Your query returns all rows and bypasses authentication entirely.

  ✘ Vulnerable code
    query = f"SELECT * FROM users WHERE name = '{username}'"

  ✔ How to fix it
    cursor.execute("SELECT * FROM users WHERE name = ?", (username,))

  💡 Remember: Never interpolate user input into SQL — use parameterized queries.
```

---

## I want to fix issues automatically

Preview what would change without touching any files:

```bash
python aicritic.py check src/ --fix --dry-run
```

Apply the fixes:

```bash
python aicritic.py check src/ --fix
```

Apply and open a GitHub PR in one step:

```bash
python aicritic.py check src/ --fix --pr
```

---

## I only want to check what I changed

Before pushing, scan only the files you touched:

```bash
python aicritic.py check src/ --diff main
python aicritic.py check src/ --diff HEAD~1
```

This is 5–10x faster than a full scan and filters out noise from existing code.

---

## I want to scan for a specific type of problem

```bash
python aicritic.py check src/ --tool secrets_scan      # hardcoded credentials
python aicritic.py check src/ --tool error_handling    # swallowed exceptions
python aicritic.py check src/ --tool design_review     # God classes, anti-patterns
python aicritic.py check src/ --tool performance       # N+1 queries, blocking I/O
python aicritic.py check src/ --tool test_quality      # weak assertions, missing coverage
```

---

## I want a CI gate that blocks bad PRs

Five minutes to set up:

```bash
# 1. Copy the workflow
mkdir -p .github/workflows
cp /path/to/aicritic/.github/workflows/aicritic.yml .github/workflows/

# 2. Add GITHUB_TOKEN to repo secrets
#    Settings → Secrets and variables → Actions → New repository secret

# 3. Create the policy file
cat > .aicritic-policy.yaml << 'EOF'
block_on: [critical, high]
diff_only: true
EOF
```

Go to: **Settings → Branches → Branch protection rules → Require status checks** →
add `aicritic / security gate`. Every PR is now gated.

Full CI setup: [ci-cd.md](ci-cd.md)

---

## I want aicritic in VS Code Copilot Chat

Type `@aicritic` in VS Code Copilot Chat to get analysis without leaving your editor.
Setup takes about 10 minutes: [copilot-extension.md](copilot-extension.md)

---

## Quick reference

| I want to… | Command |
|------------|---------|
| Scan everything | `python aicritic.py check src/` |
| Only changed files | `python aicritic.py check src/ --diff main` |
| Understand WHY | add `--explain` |
| Fix automatically | add `--fix` |
| Fix + open PR | add `--fix --pr` |
| Scan for secrets | add `--tool secrets_scan` |
| Review design | add `--tool design_review` |
| Skip Gemini (faster) | add `--skip-checker` |
| Only HIGH+ findings | add `--min-risk high` |
| Save HTML report | add `--html report.html` |

---

**Next steps**

- [CLI reference](cli.md) — every flag explained with examples
- [CI/CD setup](ci-cd.md) — GitHub Actions gate, policy file, suppression
- [Copilot Extension](copilot-extension.md) — `@aicritic` in VS Code
- [Agent mode](agent.md) — natural language tasks, autonomous fixes

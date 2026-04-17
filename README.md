# aicritic

**Three AI models review your code in sequence. Each one checks the previous one's work.**

Claude Sonnet finds the issues. Gemini cross-checks them. Claude Opus arbitrates,
assigns final risk levels, and writes a prioritised fix plan. An optional fixer
applies the patches automatically.

```
Your code
    │
    ▼
[1] Claude Sonnet ─── primary analyst ───► findings JSON
    │
    ▼
[2] Gemini ──────────── cross-checker ───► agreements / disagreements
    │
    ▼
[3] Claude Opus ──────── critic/arbiter ─► verdict + recommendations
    │
    ├─► report  (Markdown / HTML / JSON / SARIF)
    ├─► --fix   → fixer → patched source files
    ├─► --pr    → GitHub PR with inline review comments
    └─► --explain → WHY + exact fix written for your specific code
```

All models run through the **GitHub Models API** — no separate Anthropic or Google
API keys needed. Costs are covered by your existing GitHub Copilot licence.

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # set GITHUB_TOKEN=ghp_...

# Analyse a directory
python aicritic.py check src/

# Only changed files, with explanations (great before opening a PR)
python aicritic.py check src/ --diff main --explain

# Fix issues automatically and open a PR
python aicritic.py check src/ --fix --pr --min-risk high

# CI gate — exits 1 if HIGH or CRITICAL findings exist
python aicritic.py ci .
```

---

## Four ways to use it

| Interface | Best for | Command |
|-----------|----------|---------|
| **`aicritic check`** | Local review before pushing | `python aicritic.py check <path>` |
| **`aicritic ci`** | Blocking PRs on policy violations | `python aicritic.py ci <path>` |
| **`aicritic agent`** | Natural-language tasks across a codebase | `python aicritic.py agent "<task>" <path>` |
| **`@aicritic`** | Inline review inside VS Code Copilot Chat | Type `@aicritic` in VS Code |

---

## For your team

### Junior developer — learn while you fix

```bash
python aicritic.py check src/ --explain
```

`--explain` adds a teaching card to every finding:

```
1. SQL Injection  [HIGH]  src/db.py:23

  ⚠ Why this is dangerous
    An attacker can send ' OR 1=1 -- as the username. Your query becomes
    SELECT * FROM users WHERE name = '' OR 1=1 --' which returns ALL rows
    and bypasses login entirely.

  ✘ Vulnerable code
    query = f"SELECT * FROM users WHERE name = '{username}'"

  ✔ How to fix it
    cursor.execute("SELECT * FROM users WHERE name = ?", (username,))

  💡 Remember: Never interpolate user input into SQL — use parameterized queries.
```

The same explanations appear automatically in `@aicritic` Copilot Chat — no extra
command needed.

### Senior developer — fast signal, low noise

```bash
# Changed files only, high+ risk, no Gemini cross-check (20s instead of 90s)
python aicritic.py check src/ --diff main --min-risk high --skip-checker

# Suppress a finding you've reviewed and accepted
result = db.execute(raw_sql)  # aicritic: accepted-risk ORM layer validates all inputs
```

The `# aicritic: accepted-risk <reason>` comment (placed on the same line or the
line before the flagged code) removes the finding from output without touching the
shared baseline file. The suppressed finding still appears in a dedicated table in
the report so leads can audit what has been accepted and why.

### Lead developer — enforce without babysitting

```yaml
# .aicritic-policy.yaml (place at repo root)
block_on: [critical, high]
tool: security_review
diff_only: true
```

```bash
# The workflow is already at .github/workflows/aicritic.yml
# Set it as a required status check:
# GitHub → Settings → Branches → Branch protection rules → Require status checks
```

Every PR now shows a **required status check**. The GitHub Actions step summary
includes three tables: blocking findings, below-threshold findings, and a 🔕
suppressed findings table with each accepted-risk reason.

---

## Tool profiles

| Profile | What it catches |
|---------|-----------------|
| `security_review` | SQL injection, XSS, command injection, auth flaws *(default)* |
| `secrets_scan` | Hardcoded API keys, tokens, passwords, private keys |
| `error_handling` | Swallowed exceptions, missing timeouts, bare `except` |
| `pr_review` | Regressions, logic errors, missing tests for new code |
| `performance` | N+1 queries, blocking I/O, inefficient data structures |
| `migration_safety` | DB lock contention, data loss, failed rollbacks |
| `test_quality` | Always-passing assertions, happy-path-only tests |
| `dependency_audit` | Outdated packages, CVEs, licence conflicts |
| `dockerfile_review` | Container security, root user, exposed secrets |
| `iac_review` | Terraform/K8s misconfigs, open permissions, missing encryption |

---

## Output formats

```bash
python aicritic.py check src/ \
  --output   report.md    \   # Markdown (always written)
  --html     report.html  \   # Self-contained HTML with risk badges
  --json     report.json  \   # Machine-readable JSON
  --sarif    scan.sarif       # SARIF 2.1.0 for GitHub code scanning upload
```

---

## Installation

**Requirements:** Python 3.11+, a GitHub token with Copilot Enterprise access.

```bash
git clone https://github.com/anirudhyadav/ai-critic
cd ai-critic
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set GITHUB_TOKEN=ghp_...
python aicritic.py check src/
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [FEATURES.md](FEATURES.md) | Every feature with examples |
| [runbooks/quickstart.md](runbooks/quickstart.md) | First run in 5 minutes |
| [runbooks/cli.md](runbooks/cli.md) | Full CLI reference |
| [runbooks/ci-cd.md](runbooks/ci-cd.md) | GitHub Actions + policy setup |
| [runbooks/copilot-extension.md](runbooks/copilot-extension.md) | VS Code Copilot Extension |
| [runbooks/org-deployment.md](runbooks/org-deployment.md) | Org-wide deployment |
| [runbooks/agent.md](runbooks/agent.md) | Autonomous agent mode |

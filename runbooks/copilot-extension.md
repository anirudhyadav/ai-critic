# Copilot Extension — @aicritic in VS Code

Use aicritic directly from VS Code Copilot Chat without leaving your editor.
Type `@aicritic` followed by what you want — paste code, ask a question, or
give it a task.

---

## I want to set it up for local development

**Step 1 — Start the server**

```bash
pip install -r requirements.txt
cp .env.example .env
# Add your GITHUB_TOKEN to .env

uvicorn server:app --reload --port 8000
```

**Step 2 — Expose it publicly**

GitHub needs to reach your server. Use ngrok for local dev:

```bash
ngrok http 8000
# Copy the https URL, e.g. https://abc123.ngrok.io
```

**Step 3 — Register a GitHub App**

1. github.com → Settings → Developer settings → GitHub Apps → **New GitHub App**
2. Fill in:
   - **Name:** `aicritic`
   - **Homepage URL:** `https://abc123.ngrok.io`
   - **Webhook URL:** `https://abc123.ngrok.io`
   - **Copilot Agent** → enable → **Callback URL:** `https://abc123.ngrok.io`
3. Permissions: **Copilot Chat → Read**
4. Click **Create GitHub App**

**Step 4 — Install the App**

App settings → **Install App** → Install on your account or org.

**Step 5 — Use it in VS Code**

Open VS Code → Copilot Chat panel. Type `@aicritic` — it appears in the agent list.

---

## I want to review code I'm looking at

Paste the code block in Copilot Chat:

```
@aicritic check this:

```python
def get_user(username):
    query = f"SELECT * FROM users WHERE name = '{username}'"
    return db.execute(query)
```
```

aicritic runs the full three-model pipeline and streams results back as markdown,
including WHY the finding is dangerous and the exact fix for your specific code.

---

## I want to scan for a specific type of problem

```
@aicritic check this code for security issues
@aicritic scan for hardcoded credentials
@aicritic review my error handling
@aicritic check this migration for safety issues
@aicritic review this PR
@aicritic check my tests
@aicritic audit these dependencies
@aicritic check this Dockerfile
@aicritic review this Terraform
```

aicritic detects the intent and routes to the right analysis profile automatically.

---

## I want to ask it to do something autonomously

Prefix with `@agent` to enable agentic mode — aicritic calls tools in a loop
until the task is done:

```
@aicritic @agent review my PR and fix high-risk issues
@aicritic @agent scan the changed files and summarise what you find
@aicritic @agent check what I changed since main
@aicritic @agent give me a full security report
@aicritic @agent review my code for design issues
```

In agent mode you see each tool call as it happens:

```
→ get_changed_files(ref='main')
   3 file(s) loaded: db.py, auth.py, config.py

→ run_analysis(tool='security_review')
   3 findings: 1 HIGH, 1 MEDIUM, 1 LOW

Found 3 issues. Before I fix them:
  - [HIGH] db.py:23 — SQL injection

→ apply_fixes(min_risk='high')
   Applied: 1 literal patch in db.py
```

---

## What a response looks like

Every response streams in three stages plus an explanation:

```markdown
### [1/3] Claude Sonnet — Primary Analysis
- **HIGH** `db.py:23` — Unsanitized user input passed to SQL query

### [2/3] Gemini — Cross-Check
✓ Confirmed: SQL injection at db.py:23

### [3/3] Claude Opus — Verdict
**HIGH — 1 confirmed issue**

### Why this matters — and how to fix it

**1. SQL Injection** [HIGH] — db.py:23

⚠️ Why this is dangerous
An attacker sends ' OR 1=1 -- and your query returns all rows,
bypassing authentication entirely.

✘ Vulnerable code
query = f"SELECT * FROM users WHERE name = '{username}'"

✔ How to fix it
cursor.execute("SELECT * FROM users WHERE name = ?", (username,))
```

---

## I want to deploy this for my whole team

See [org-deployment.md](org-deployment.md) — every developer in your org gets
`@aicritic` in VS Code, billed to your existing Copilot Enterprise licence,
with no individual API keys.

---

## Troubleshooting

**`@aicritic` doesn't appear in VS Code**
The App isn't installed or hasn't propagated yet. Re-install the App, wait ~1 minute,
then reload VS Code (Cmd/Ctrl+Shift+P → "Developer: Reload Window").

**`401 Invalid request signature`**
ECDSA verification is failing. For local dev, add `AICRITIC_DEV_MODE=true` to your `.env`
to skip signature verification. Never use this in production.

**`403 Access restricted to org members`**
Your `AICRITIC_ORG` setting is active and the requesting user isn't in that org.
Either add them to the org or clear `AICRITIC_ORG` to allow any valid Copilot user.

**Empty response — no analysis appears**
aicritic couldn't find a code block in your message. Wrap your code in triple backticks.

**`GITHUB_TOKEN is not set`**
Run `cp .env.example .env` and add your token.

**ngrok URL changed**
Free tier ngrok generates a new URL on restart. Update all three URLs in the GitHub App settings:
Homepage URL, Callback URL, Webhook URL. Then save.

**Slow first response**
Normal — no cache yet for this code. Re-run on the same code is instant.

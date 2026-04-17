# Runbook — aicritic Copilot Extension

## Overview

The Copilot Extension exposes aicritic as a GitHub Copilot Agent (`@aicritic`)
inside VS Code Copilot Chat. Developers type natural language — the server runs
the full three-model pipeline and streams results back as markdown, including the
explainer (WHY + exact fix) for every finding.

Requests use the developer's own Copilot bearer token for model calls, so costs
are billed to the org's existing Copilot Enterprise licence.

---

## How it works

```
Developer types in VS Code Copilot Chat
    │
    ▼ HTTPS + ECDSA signature
aicritic server (FastAPI)
    │
    ├─ Verify GitHub ECDSA signature
    ├─ Extract user token from Authorization header
    ├─ Verify org membership (if AICRITIC_ORG is set)
    │
    ▼
Three-model pipeline (Sonnet → Gemini → Opus)
    │
    ▼
Explainer (WHY + exact fix for each finding)
    │
    ▼ Server-Sent Events
VS Code Copilot Chat (streaming markdown)
```

---

## Setup

### 1. Start the server

```bash
pip install -r requirements.txt
cp .env.example .env
# Set GITHUB_TOKEN in .env

uvicorn server:app --reload --port 8000
```

### 2. Expose publicly

GitHub needs to reach your server. Use ngrok for local development:

```bash
ngrok http 8000
# Copy the https URL, e.g. https://abc123.ngrok.io
```

For production, deploy behind a reverse proxy with a TLS certificate.

### 3. Register a GitHub App

1. Go to: **github.com → Settings → Developer settings → GitHub Apps → New GitHub App**
2. Fill in:
   - **GitHub App name:** `aicritic` (or your org's name)
   - **Homepage URL:** `https://abc123.ngrok.io`
   - **Webhook URL:** `https://abc123.ngrok.io`
   - **Copilot Agent:** enable → **Callback URL:** `https://abc123.ngrok.io`
3. Permissions: **Copilot Chat → Read**
4. Click **Create GitHub App**

### 4. Install the App

- Go to the App settings → **Install App**
- Install on your account or org

### 5. Use in VS Code

1. Open VS Code → Copilot Chat panel
2. Type `@aicritic` — the extension appears in the agent list
3. Start chatting:

```
@aicritic check this code for SQL injection
@aicritic review my error handling
@aicritic scan for hardcoded secrets
@aicritic @agent review my PR and fix high-risk issues
```

---

## What you can ask

### Standard analysis

```
@aicritic check this code
@aicritic review my error handling
@aicritic scan for secrets
@aicritic look at my migration for safety issues
```

Paste a code block in your message and aicritic will analyse it:

````
@aicritic check this:

```python
def get_user(username):
    query = f"SELECT * FROM users WHERE name = '{username}'"
    return db.execute(query)
```
````

### Specific tool profiles

```
@aicritic check this for security issues         → security_review
@aicritic scan for hardcoded credentials         → secrets_scan
@aicritic review my error handling               → error_handling
@aicritic check this migration                   → migration_safety
@aicritic review this PR                         → pr_review
@aicritic check my tests                         → test_quality
@aicritic audit my dependencies                  → dependency_audit
@aicritic check this Dockerfile                  → dockerfile_review
@aicritic review this Terraform                  → iac_review
```

### Agent mode

Prefix with `@agent` to enable the autonomous tool-use loop:

```
@aicritic @agent review my PR and fix high-risk issues
@aicritic @agent scan the changed files and summarise what you find
@aicritic @agent check what I changed since main
```

In agent mode, aicritic calls tools autonomously: reading files, running the
pipeline, applying fixes, and opening PRs — reporting progress step by step.

---

## What the response looks like

Every response streams in three stages, then automatically runs the explainer:

```markdown
### [1/3] Claude Sonnet — Primary Analysis
- **HIGH** `db.py:23` — Unsanitized user input passed to SQL query
- **MEDIUM** `auth.py:45` — Password logged in plaintext

### [2/3] Gemini — Cross-Check
✓ Confirmed: SQL injection at db.py:23
✗ Disagrees: auth.py:45 is low risk (logging is internal only)

### [3/3] Claude Opus — Verdict
**HIGH — 1 confirmed critical issue**
1. [HIGH] Use parameterized queries in db.py line 23

### Why these matter — and how to fix them

---

**1. SQL Injection** `[HIGH]` — `db.py:23`

⚠️ **Why this is dangerous**
An attacker can send ' OR 1=1 -- as the username. Your query returns
ALL rows and bypasses authentication entirely.

✘ **Vulnerable code**
```
query = f"SELECT * FROM users WHERE name = '{username}'"
```

✔ **How to fix it**
```
cursor.execute("SELECT * FROM users WHERE name = ?", (username,))
```

> 💡 **Remember:** Never interpolate user input into SQL — use parameterized queries.
```

---

## Org deployment

### Per-request token

Each Copilot Chat request carries the user's bearer token in the `Authorization`
header. aicritic extracts this token and uses it for all model calls — no shared
service account is needed for model API access.

The `GITHUB_TOKEN` in `.env` is only used as a CLI fallback and for PR operations
(branch creation, PR API calls).

### Org membership gating

Set `AICRITIC_ORG` to restrict access to members of a specific organisation:

```bash
# .env
AICRITIC_ORG=my-org-name
```

On each request:
1. aicritic calls `GET /user` with the user's token to get their GitHub login.
2. Calls `GET /orgs/{org}/members/{username}` — 204 = member, otherwise denied.
3. Returns HTTP 403 for non-members (logged to audit file).
4. Caches the result for 5 minutes to avoid repeated GitHub API calls.

Leave `AICRITIC_ORG` blank to allow any valid Copilot user.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | Fine-grained PAT; CLI fallback and PR operations |
| `AICRITIC_DEV_MODE` | Dev only | `true` skips ECDSA verification and org check |
| `AICRITIC_ORG` | Recommended | GitHub org slug — restricts to org members |
| `AICRITIC_AUDIT_LOG` | Optional | Path to JSONL audit log file |
| `AICRITIC_CACHE_TTL` | Optional | Cache TTL in seconds (default 86400) |

---

## Audit log

Every request — allowed and denied — is written as a JSON line:

```json
{"ts":"2025-04-17T12:34:56Z","user":"alice","tool":"security_review","files":3,"findings":5,"high_count":2,"agent_mode":false,"duration_ms":4200,"verdict":"HIGH — 2 issues found"}
```

Denied requests:
```json
{"ts":"2025-04-17T12:34:00Z","user":"unknown","denied":true,"reason":"not_org_member"}
```

Always written to the Python logger (`INFO` level). Set `AICRITIC_AUDIT_LOG` to
also write to a file. Compatible with Datadog, Splunk, CloudWatch, and `grep`.

---

## Production deployment

Replace ngrok with a permanent HTTPS endpoint:

1. Deploy `server.py` on any host (AWS, GCP, Railway, Render, etc.).
2. Put it behind a reverse proxy (nginx, Caddy) with a TLS certificate.
3. Set `AICRITIC_DEV_MODE=false` (or omit entirely).
4. Update all GitHub App URLs to the production domain.
5. Set `AICRITIC_ORG` to restrict access to your organisation.
6. Configure `AICRITIC_AUDIT_LOG` to write to a persistent log path.

```bash
# Production .env
GITHUB_TOKEN=ghp_service_account_token
AICRITIC_DEV_MODE=false
AICRITIC_ORG=my-org
AICRITIC_AUDIT_LOG=/var/log/aicritic/audit.jsonl
```

---

## Updating the ngrok URL (free tier)

When ngrok restarts it generates a new URL. To update:

1. `ngrok http 8000` — copy the new URL
2. Go to: **github.com → Settings → Developer settings → GitHub Apps → aicritic → Edit**
3. Update **Homepage URL**, **Callback URL**, and **Webhook URL**
4. Click **Save changes**

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `@aicritic` not visible in VS Code | App not installed or not propagated | Re-install App; wait ~1 min; reload VS Code |
| `401 Invalid request signature` | ECDSA verification failing | Set `AICRITIC_DEV_MODE=true` for local dev |
| `403 Access restricted to org members` | User not in `AICRITIC_ORG` | Add user to the org, or clear `AICRITIC_ORG` |
| `GITHUB_TOKEN is not set` | Missing `.env` | `cp .env.example .env` and add token |
| `401 Unauthorized` from model API | Token expired or lacks Copilot access | Regenerate token; check Copilot Enterprise scope |
| Server not reachable | ngrok URL changed | Re-run `ngrok http 8000`; update GitHub App URLs |
| Empty response in chat | No code block found in message | Wrap code in triple backticks |
| Org check passes for removed employee | Membership cache still valid | Cache expires in 5 min; restart server to force refresh |
| Slow first response | No cache yet for this code | Normal; re-runs on unchanged code are fast |

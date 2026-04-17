# Runbook — aicritic Copilot Extension

## Overview

The Copilot Extension exposes the same three-model critic chain as a GitHub Copilot Agent.
Users type `@aicritic check this code` directly in VS Code or GitHub.com Copilot Chat.
Code is pasted as a fenced block; results stream back into the chat as each model finishes.

```
User types @aicritic in Copilot Chat
    │
    ▼
GitHub sends signed POST to your server
    │
    ▼
FastAPI verifies ECDSA signature → parses code blocks → detects tool
    │
    ▼
[Claude Sonnet]  primary analyst    → streams findings into chat
    │
    ▼
[Gemini]         cross-checker      → streams verification into chat
    │
    ▼
[Claude Opus]    critic / arbiter   → streams final report into chat
```

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Check with `python --version` |
| GitHub account | — | Must have Copilot Enterprise access |
| GitHub token | — | Fine-grained PAT (same as CLI) |
| ngrok | any | Exposes localhost to GitHub during development |
| GitHub App | — | Created in Step 5 below |

---

## Step 1 — Clone and install

```bash
git clone https://github.com/anirudhyadav/ai-critic.git
cd ai-critic
pip install -r requirements.txt
```

---

## Step 2 — Create a GitHub token

1. Go to **github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Set expiry (90 days recommended)
4. Under **Permissions** — no special scopes needed; Copilot Enterprise covers model access
5. Click **Generate token** and copy the value

---

## Step 3 — Configure environment

```bash
cp .env.example .env
```

Open `.env` and set:

```
GITHUB_TOKEN=ghp_your_token_here
AICRITIC_DEV_MODE=true
```

> `AICRITIC_DEV_MODE=true` skips GitHub's ECDSA signature check.
> **Remove or set to `false` before any production deployment.**

---

## Step 4 — Start the server

```bash
uvicorn server:app --reload --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

Verify the health check:
```bash
curl http://localhost:8000/
# {"status":"ok","service":"aicritic"}
```

---

## Step 5 — Expose the server publicly with ngrok

GitHub must be able to reach your server to send requests.

```bash
ngrok http 8000
```

Note the HTTPS forwarding URL — you will need it in Step 6:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8000
```

> The ngrok URL changes every time you restart ngrok (free tier).
> Update the GitHub App URLs in Step 6 whenever this happens.

---

## Step 6 — Register a GitHub App

1. Go to **github.com → Settings → Developer settings → GitHub Apps**
2. Click **New GitHub App**
3. Fill in the fields:

| Field | Value |
|-------|-------|
| **GitHub App name** | `aicritic` (or any unique name) |
| **Homepage URL** | your ngrok URL, e.g. `https://abc123.ngrok.io` |
| **Callback URL** | your ngrok URL |
| **Webhook URL** | your ngrok URL |
| **Webhook secret** | leave blank for dev mode |

4. Under **Permissions** → no repository permissions needed
5. Under **Copilot** (scroll down):
   - Set **App type** to `Agent`
   - Set **Inference description** to e.g. `Review code with a three-model AI critic chain`
   - Set the **Callback URL** to `https://abc123.ngrok.io`
6. Click **Create GitHub App**
7. On the App's page, click **Install App** → install on your personal account or organisation

---

## Step 7 — Use it in VS Code

1. Open VS Code with the GitHub Copilot extension installed
2. Open Copilot Chat (`Ctrl+Shift+I` / `Cmd+Shift+I`)
3. Type `@aicritic` — it should appear as an available agent
4. Paste code in a fenced block and ask a question:

```
@aicritic check this for security issues

```python
def login(user, pwd):
    query = f"SELECT * FROM users WHERE user='{user}'"
    db.execute(query)
```
```

Results stream in as each model finishes — Sonnet first, then Gemini, then Opus.

---

## Using it on GitHub.com

The same `@aicritic` agent is available in GitHub.com Copilot Chat once the App is installed.
Navigate to any repository → click the Copilot icon → type `@aicritic`.

---

## Tool auto-detection

The extension detects which analysis tool to run from keywords in your message.
No `--tool` flag needed — just describe what you want.

| Keywords in your message | Tool selected |
|--------------------------|---------------|
| secret, credential, hardcoded, api key | `secrets_scan` |
| coverage, untested, branch coverage | `code_coverage` |
| migration, alter table, rollback | `migration_safety` |
| performance, slow, n+1, blocking | `performance` |
| error handling, exception, timeout | `error_handling` |
| dependency, requirements, cve, licence | `dependency_audit` |
| pull request, pr review, regression | `pr_review` |
| test quality, flaky, assertion | `test_quality` |
| _(anything else)_ | `security_review` |

---

## Streaming behaviour

Each stage streams into the chat as it completes:

```
aicritic — security_review

---

Running Claude Sonnet…
**Finding 1** — SQL injection in login() [HIGH]
...

Running Gemini…
**Verified:** SQL injection confirmed — also found missing authentication
...

Running Claude Opus…
**Final findings — 3 issues**
| Risk | Finding | File |
...

---
Analysis complete.
```

The user sees Sonnet's findings while Gemini is still running — no waiting for all three to finish.

### Graceful degradation

If the Gemini cross-check stage fails for any reason (rate limit, timeout,
malformed response, API outage), the pipeline **does not crash**. Instead
the chat shows:

```
> ⚠ Checker stage unavailable — <reason>.
> Continuing with analyst-only findings.
```

Opus is explicitly told the cross-check was skipped and applies extra
scrutiny to Sonnet's findings. The user always gets an answer — just a
flagged one.

### Token efficiency

Opus (the critic stage) does not receive the full pasted code — it gets a
compact ±5-line window around each flagged line range, plus the analyst
and checker JSON. This keeps the final stage fast and well under any
context-window limit, even for long pasted snippets.

---

## All environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | Fine-grained PAT used as CLI fallback; per-request user token is used for model calls in org deployments |
| `AICRITIC_DEV_MODE` | Dev only | Set `true` to skip ECDSA signature verification and org membership check |
| `AICRITIC_ORG` | Org deployments | GitHub org slug — restricts access to org members only. Leave blank to allow any valid Copilot user |
| `AICRITIC_AUDIT_LOG` | Optional | Absolute or relative path to a JSONL file for structured audit logs. Omit to log to stdout only |

---

## Org deployment

### How it works

When deployed as a Copilot Extension inside an organisation, every request arrives
with a per-request bearer token in the `Authorization` header. This token belongs
to the individual employee and is automatically injected by Copilot Chat — no
separate login is required.

aicritic uses that token for all model calls, so:

- Model usage is billed against the **org's Copilot Enterprise licence**, not a
  shared service account.
- `GITHUB_TOKEN` is only used as a fallback (e.g. CLI usage).

### Org membership gate

Set `AICRITIC_ORG=my-org` to restrict access to members of that organisation.

On each request, aicritic:

1. Calls `GET /user` with the per-request token to get the GitHub username.
2. Calls `GET /orgs/{org}/members/{username}` — HTTP 204 = member, otherwise denied.
3. Caches the result for **5 minutes** (TTL configurable via `_MEMBERSHIP_TTL` in
   `copilot/auth.py`) to avoid a GitHub API call on every message.
4. Returns HTTP 403 with a logged `denied` audit event for non-members.

If `AICRITIC_ORG` is not set, all authenticated Copilot users are allowed.

### Audit log

Every request (allowed or denied) is logged as a JSON line:

```json
{"ts":"2025-04-17T12:34:56Z","user":"alice","tool":"security_review","files":3,"findings":5,"high_count":2,"agent_mode":false,"duration_ms":4200,"verdict":"HIGH — 2 issues found"}
```

Denied requests:

```json
{"ts":"2025-04-17T12:34:00Z","user":"unknown","denied":true,"reason":"invalid_signature"}
```

Logs always go to the Python logger at `INFO` level. Set `AICRITIC_AUDIT_LOG=./logs/audit.jsonl`
to also write to a file (one JSON line per request, append mode).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `@aicritic` not visible in VS Code | App not installed or not yet propagated | Re-install App; wait ~1 min; reload VS Code |
| `401 Invalid request signature` | ECDSA verification failing | Set `AICRITIC_DEV_MODE=true` in `.env` |
| `GITHUB_TOKEN is not set` | Missing `.env` | Run `cp .env.example .env` and add token |
| `401 Unauthorized` from model API | Token expired | Regenerate at github.com → Settings |
| Server not reachable | ngrok URL changed | Re-run `ngrok http 8000`, update GitHub App URLs |
| Empty response in chat | No code block found | Wrap your code in triple backticks |
| `Could not parse JSON from model response` | Model returned prose | Re-run — usually one-off; persistent issues → check `config.py` system prompts |
| Slow / no streaming in VS Code | Proxy buffering SSE | Check corporate proxy; SSE requires chunked transfer encoding |
| `403 Access restricted to org members` | User not in `AICRITIC_ORG` | Add user to the org, or clear `AICRITIC_ORG` to allow all users |
| Org check passes for removed employees | Membership cache still valid | Cache expires in 5 min; restart server to force immediate eviction |
| Audit file not growing | Wrong path or permission | Check `AICRITIC_AUDIT_LOG`; ensure the `logs/` directory exists and is writable |

---

## Updating the ngrok URL

When ngrok restarts (free tier), update the GitHub App:

1. Get the new URL from `ngrok http 8000` output
2. Go to **github.com → Settings → Developer settings → GitHub Apps → aicritic → Edit**
3. Update **Homepage URL**, **Callback URL**, and **Webhook URL**
4. Click **Save changes**

---

## Moving to production

For a permanent deployment, replace ngrok with a real HTTPS endpoint:

1. Deploy `server.py` behind a reverse proxy (nginx / Caddy) with a TLS certificate
2. Set `AICRITIC_DEV_MODE=false` (or remove the variable entirely)
3. Update all GitHub App URLs to the production domain
4. Rotate `GITHUB_TOKEN` to a long-lived service account token

---

## Demo script (for leadership)

```
# In VS Code Copilot Chat:

@aicritic check this for SQL injection and hardcoded secrets

```python
import sqlite3

DB_PASSWORD = "admin123"

def get_user(username):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE name = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()
```
```

Expected: Sonnet flags SQL injection and hardcoded credential → Gemini confirms and adds details → Opus assigns risk levels and prioritises fixes.

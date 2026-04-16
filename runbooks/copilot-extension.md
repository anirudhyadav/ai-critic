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

---

## All environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | Fine-grained PAT with Copilot Enterprise access |
| `AICRITIC_DEV_MODE` | Dev only | Set `true` to skip ECDSA signature verification |

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

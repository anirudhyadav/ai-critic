# Org Deployment

Deploy aicritic as a shared `@aicritic` agent for your whole organisation.
Every developer gets it in VS Code Copilot Chat. Model calls are billed to
your existing Copilot Enterprise licence — no individual API keys, no per-seat setup.

---

## How it works

```
Developer types @aicritic in VS Code
        │
        │ HTTPS + ECDSA signature
        ▼
  aicritic server
        ├─ Verify GitHub's signature
        ├─ Extract the user's Copilot bearer token
        ├─ Check org membership
        ├─ Log to audit file
        │
        ▼ model calls using the USER's own token
  GitHub Models API
        │
        └─► billed to org's Copilot Enterprise licence
```

Each developer's API usage is billed under their own seat.
The `GITHUB_TOKEN` in `.env` is only used for PR operations (push, PR API calls).

---

## Before you start

You need:
- GitHub **Copilot Enterprise** licence for the org (not Individual)
- A persistent HTTPS endpoint (public domain with TLS)
- A GitHub service account (machine user) with Copilot access
- Org admin access to register a GitHub App

---

## Step 1 — Deploy the server

Pick your deployment option:

**Docker:**
```bash
docker build -t aicritic .
docker run -p 8000:8000 --env-file .env aicritic
```

**Railway / Render / Fly.io:**
```bash
git clone https://github.com/anirudhyadav/ai-critic
# Push to your platform and set environment variables in the dashboard
```

**VM / bare metal:**
```bash
pip install -r requirements.txt
gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

The server must be reachable at a stable public HTTPS URL before the next step.

---

## Step 2 — Configure environment

On the server (or in your hosting platform's env var settings):

```bash
# Required
GITHUB_TOKEN=ghp_service_account_token

# Disable dev mode in production
AICRITIC_DEV_MODE=false

# Restrict access to members of this org
AICRITIC_ORG=your-org-slug

# Audit log
AICRITIC_AUDIT_LOG=/var/log/aicritic/audit.jsonl

# Cache (optional)
AICRITIC_CACHE_TTL=86400
AICRITIC_CACHE_DIR=/var/cache/aicritic
```

`GITHUB_TOKEN` should be a **fine-grained PAT from a service account** (not a personal account), with:
- Contents: read
- Pull requests: write

---

## Step 3 — Register the GitHub App

1. Log in as the service account (or org admin)
2. github.com → Settings → Developer settings → GitHub Apps → **New GitHub App**
3. Fill in:

| Field | Value |
|-------|-------|
| Name | `aicritic` (or `your-org-aicritic`) |
| Homepage URL | `https://your-domain.example.com` |
| Webhook URL | `https://your-domain.example.com` |
| Copilot Agent | Enable |
| Callback URL | `https://your-domain.example.com` |

4. Permissions: **Copilot Chat → Read**
5. Click **Create GitHub App** and note the App ID

---

## Step 4 — Install on the org

App settings → **Install App** → your org → **Install**.

Choose all repositories or specific repos. After install, org members see `@aicritic`
in VS Code within ~1 minute (may need a VS Code reload).

---

## Step 5 — Verify it's working

Health check from your server:
```bash
curl https://your-domain.example.com/
# Expected: {"status": "ok", "service": "aicritic"}
```

Test from VS Code:
1. Open VS Code → Copilot Chat
2. Type: `@aicritic check this code`
3. Paste a snippet and press Enter
4. Verify a streaming response appears

Watch the audit log:
```bash
tail -f /var/log/aicritic/audit.jsonl
```

---

## I want to restrict access to org members only

Set `AICRITIC_ORG=your-org-slug` in your environment. On every request, aicritic:

1. Calls `GET /user` with the user's token → gets their GitHub login
2. Calls `GET /orgs/{org}/members/{login}` → 204 = member, anything else = denied
3. Returns HTTP 403 for non-members and logs a `denied` audit event

Membership results are cached for 5 minutes per token. To force immediate re-verification
(e.g. after removing a contractor), restart the server.

Leave `AICRITIC_ORG` blank to allow any valid Copilot user — not recommended for org deployments.

---

## I want to review who's using aicritic and what they found

Every request writes one JSON line to the audit log:

```json
{
  "ts": "2025-04-17T12:34:56Z",
  "user": "alice",
  "tool": "security_review",
  "files": 3,
  "findings": 5,
  "high_count": 2,
  "agent_mode": false,
  "duration_ms": 4200,
  "verdict": "HIGH — 2 issues found"
}
```

Denied requests:
```json
{
  "ts": "2025-04-17T12:34:00Z",
  "user": "unknown",
  "denied": true,
  "reason": "not_org_member"
}
```

**Useful queries:**
```bash
# Most active users
cat audit.jsonl | jq -r '.user' | sort | uniq -c | sort -rn | head 10

# Sessions that found HIGH or CRITICAL issues
cat audit.jsonl | jq 'select(.high_count > 0) | {user, ts, verdict}'

# Average response time
cat audit.jsonl | jq -r '.duration_ms' | awk '{s+=$1; c++} END {print s/c " ms avg"}'
```

The log is compatible with Datadog, Splunk, CloudWatch, and `grep`.

---

## I want to scale to multiple server instances

The server is stateless — run multiple instances behind a load balancer.
The pipeline result cache is per-instance (disk-based). For cache sharing across
instances, point `AICRITIC_CACHE_DIR` to a network file system.

---

## Security checklist before going live

- [ ] `AICRITIC_DEV_MODE=false` (never skip signature verification in production)
- [ ] `AICRITIC_ORG` set to restrict access to your org
- [ ] `GITHUB_TOKEN` is a service account PAT, not a personal account token
- [ ] Server is behind HTTPS (no plain HTTP)
- [ ] Audit log is on persistent storage and not web-accessible
- [ ] Server process runs as a non-root user
- [ ] Token rotation scheduled (recommended: every 90 days)

---

## Troubleshooting

**`@aicritic` not visible to org members**
The App isn't installed on the org. Go to App settings → Install App → your org.

**`403 Access restricted to org members`**
The user isn't in `AICRITIC_ORG`. Add them to the GitHub org, or temporarily
clear `AICRITIC_ORG` to confirm it's a membership issue.

**`401 Invalid request signature`**
ECDSA verification is failing — usually a proxy stripping headers. Check that the
`x-github-public-key-identifier` and `x-github-public-key-signature` headers
reach the server unchanged.

**Model calls returning 401**
The user's token doesn't have Copilot Enterprise access. They need an active seat
in the org's Copilot Enterprise licence.

**Membership check passing for a removed employee**
The 5-minute membership cache hasn't expired. Restart the server to force
immediate re-verification.

**`AICRITIC_ORG` set correctly but check always fails**
Use the org's slug (the URL-safe name), not the display name.
Confirm with: `curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/orgs/your-slug`

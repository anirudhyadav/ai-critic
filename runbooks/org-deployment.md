# Runbook — Org Deployment

## Overview

This runbook covers deploying aicritic as a shared Copilot Extension for an
entire organisation. The goal: every developer in the org can type `@aicritic`
in VS Code Copilot Chat, backed by the org's existing Copilot Enterprise licence —
no individual API keys, no per-developer setup.

---

## Architecture

```
Developer → VS Code Copilot Chat
                │
                │ HTTPS request + user's Copilot bearer token
                ▼
        aicritic server (FastAPI)
                │
                ├─ Verify ECDSA signature  (GitHub signs every request)
                ├─ Extract user token from Authorization header
                ├─ Check org membership    (AICRITIC_ORG)
                ├─ Log to audit file       (AICRITIC_AUDIT_LOG)
                │
                ▼ model API calls using the USER's token
        GitHub Models API (Azure endpoint)
                │
                └─► billed to org's Copilot Enterprise licence
```

**Key properties:**
- Each developer's model calls use their own Copilot token — not a shared key.
- The `GITHUB_TOKEN` in `.env` is only used for PR operations (branch/push/PR API).
- Access is gated by org membership — non-members get HTTP 403.
- Every request is logged for compliance and usage analytics.

---

## Prerequisites

| Item | Details |
|------|---------|
| GitHub Copilot Enterprise | Org must have Copilot Enterprise (not Individual) |
| Python 3.11+ | On the deployment host |
| Persistent HTTPS endpoint | Public domain with TLS certificate |
| Service account | GitHub account for the GitHub App; needs Copilot access |
| Org admin access | To register the GitHub App and install on the org |

---

## Step 1: Deploy the server

### Option A: Simple server (Railway / Render / Fly.io)

```bash
# Clone and push to your deployment platform
git clone https://github.com/anirudhyadav/ai-critic
cd ai-critic
# Follow your platform's deploy instructions
# Set environment variables in the platform dashboard
```

### Option B: Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t aicritic .
docker run -p 8000:8000 --env-file .env aicritic
```

### Option C: VM / bare metal

```bash
pip install -r requirements.txt
# Use a process manager to keep it running
gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Or with systemd
# Create /etc/systemd/system/aicritic.service
```

The server must be accessible at a stable public HTTPS URL.

---

## Step 2: Configure environment

Create a `.env` file on the server (or set variables in your hosting platform):

```bash
# Required
GITHUB_TOKEN=ghp_service_account_token_here

# Security — disable dev mode in production
AICRITIC_DEV_MODE=false

# Org gating — restrict to members of this org
AICRITIC_ORG=your-org-name

# Audit log
AICRITIC_AUDIT_LOG=/var/log/aicritic/audit.jsonl

# Cache (optional — on-disk, per-server)
AICRITIC_CACHE_TTL=86400
AICRITIC_CACHE_DIR=/var/cache/aicritic
```

The `GITHUB_TOKEN` should be a fine-grained PAT from a **service account**
(a GitHub machine user), not a personal account, with:
- Copilot Enterprise access
- Contents: read (for PR branch creation)
- Pull requests: write (for opening PRs)

---

## Step 3: Register the GitHub App

1. Log in as the service account (or org admin).
2. Go to: **github.com → Settings → Developer settings → GitHub Apps → New GitHub App**
3. Fill in:
   | Field | Value |
   |-------|-------|
   | GitHub App name | `aicritic` (or `your-org-aicritic`) |
   | Homepage URL | `https://your-domain.example.com` |
   | Webhook URL | `https://your-domain.example.com` |
   | Copilot Agent | Enable |
   | Callback URL | `https://your-domain.example.com` |
4. Permissions:
   - **Copilot Chat:** Read
5. Click **Create GitHub App**
6. Note the App ID.

---

## Step 4: Install the App on the org

1. In the App settings: **Install App → Your org → Install**
2. Choose: **All repositories** or select specific repos.
3. Click **Install**.

After installation, org members will see `@aicritic` in VS Code Copilot Chat
within ~1 minute (may require VS Code reload).

---

## Step 5: Verify the deployment

Health check:
```bash
curl https://your-domain.example.com/
# Expected: {"status": "ok", "service": "aicritic"}
```

Test from VS Code:
1. Open VS Code → Copilot Chat
2. Type: `@aicritic check this code`
3. Paste a code snippet and press Enter
4. Verify a streaming analysis response appears

Check the audit log:
```bash
tail -f /var/log/aicritic/audit.jsonl
```

---

## Org membership gating

With `AICRITIC_ORG=your-org-name`, aicritic checks every request:

1. Calls `GET https://api.github.com/user` with the user's token → gets their login.
2. Calls `GET https://api.github.com/orgs/{org}/members/{login}` → 204 = member.
3. Returns HTTP 403 for non-members; logs a `denied` audit event.

**Cache:** membership results are cached for 5 minutes per token prefix. Restart
the server to force immediate re-verification (e.g., after removing a member).

**Leave `AICRITIC_ORG` blank** to allow any valid Copilot user (not recommended
for org deployments).

---

## Audit log reference

Every request produces one JSON line:

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

| Field | Description |
|-------|-------------|
| `ts` | ISO 8601 UTC timestamp |
| `user` | GitHub login (empty if unknown) |
| `tool` | Analysis profile used |
| `files` | Number of files analysed |
| `findings` | Total findings in final report |
| `high_count` | Findings at HIGH or CRITICAL risk |
| `agent_mode` | `true` if request used `@agent` trigger |
| `duration_ms` | Wall-clock time for the full pipeline |
| `verdict` | Final verdict string from Claude Opus |
| `denied` | Present and `true` for blocked requests |
| `reason` | Denial reason: `invalid_signature`, `not_org_member` |

**Usage analytics from audit log:**
```bash
# Most active users
cat audit.jsonl | jq -r '.user' | sort | uniq -c | sort -rn | head 10

# High/critical finding rate over time
cat audit.jsonl | jq 'select(.high_count > 0) | .ts' | head 20

# Average response time
cat audit.jsonl | jq -r '.duration_ms' | awk '{s+=$1; c++} END {print s/c " ms avg"}'
```

---

## Scaling

The FastAPI server is stateless — scale horizontally by running multiple instances
behind a load balancer. The pipeline result cache is per-instance (disk-based), so
cache hits only occur on the same instance that last processed the request. For
shared caching across instances, point `AICRITIC_CACHE_DIR` to a network file system.

---

## Security checklist

- [ ] `AICRITIC_DEV_MODE=false` in production (never skip signature verification)
- [ ] `AICRITIC_ORG` set to restrict access
- [ ] `GITHUB_TOKEN` is a service account PAT, not a personal token
- [ ] Server is behind TLS (HTTPS only, no plain HTTP)
- [ ] Audit log path is on persistent storage
- [ ] Audit log directory is not web-accessible
- [ ] Server process runs as a non-root user
- [ ] Token is rotated on a schedule (recommended: 90 days)

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `@aicritic` not visible to org members | App not installed on org | Install App on org (step 4) |
| `403 Access restricted to org members` | User not in org | Add user to the GitHub org |
| `401 Invalid request signature` | ECDSA check failing | Verify server is reachable; check for proxy stripping headers |
| Model calls failing with 401 | User's token lacks Copilot access | User needs an active Copilot Enterprise seat |
| Membership check always fails | Wrong `AICRITIC_ORG` value | Use the org's slug (not display name); check with `gh api /orgs/{slug}` |
| Old removed employees still have access | Membership cache not expired | Restart server to clear cache (expires automatically in 5 min) |
| Audit log not growing | Wrong path or permissions | Check `AICRITIC_AUDIT_LOG`; ensure directory exists and is writable |

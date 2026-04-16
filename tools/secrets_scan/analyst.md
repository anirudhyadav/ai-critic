---
mode: secrets_scan
focus: secrets and credentials
strictness: high
min_risk: low
model: claude-3-5-sonnet
---

## What to Check
- Hardcoded passwords, API keys, tokens, and private keys
- Database connection strings with embedded credentials
- OAuth secrets and client IDs committed to source
- SSH or TLS private key material
- Secrets in comments or debug statements
- Environment variable values hardcoded as fallbacks (e.g. `os.getenv("KEY", "real-secret")`)
- Weak entropy sources used for token or session generation

## Ignore
- Placeholder values clearly marked as examples (e.g. `"your-key-here"`, `"<REPLACE_ME>"`)
- Public keys — only flag private key material

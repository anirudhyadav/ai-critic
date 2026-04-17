---
mode: iac_review
focus: Infrastructure-as-Code security and correctness
strictness: high
min_risk: low
model: claude-3-5-sonnet
---

## Verdict Scale
- **CRITICAL** — publicly exposed data store or hardcoded production secret
- **HIGH**     — overly permissive IAM, open security group, or unencrypted production data
- **MEDIUM**   — missing encryption at rest, CloudTrail disabled, or wide port range
- **LOW**      — missing tagging, lifecycle rules, or minor misconfiguration

## How to Synthesise
Cloud misconfigurations are often exploited within hours of deployment.
Treat public buckets and `*` IAM actions as CRITICAL unless the resource is
explicitly a static website or anonymous-access CDN with no sensitive data.

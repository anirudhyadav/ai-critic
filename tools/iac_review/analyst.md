---
mode: iac_review
focus: Infrastructure-as-Code security and correctness
strictness: high
min_risk: low
model: claude-3-5-sonnet
---

## What to Check (Terraform / HCL / CloudFormation / Pulumi / Kubernetes YAML)

### Access Control
- Overly permissive IAM policies (`*` actions or resources)
- Public S3 buckets, public RDS instances, or open security groups (`0.0.0.0/0`)
- Missing MFA or condition keys on sensitive IAM statements
- Admin policies attached directly to users instead of roles

### Secrets and Credentials
- Hardcoded secrets, passwords, or tokens in `.tf`, `.yaml`, or `.json` resources
- Secrets stored in SSM Parameter Store as plain text instead of SecureString
- `sensitive = false` on outputs that expose credentials

### Encryption
- S3 buckets without server-side encryption
- RDS instances without storage encryption or SSL enforcement
- EBS volumes without encryption
- KMS key rotation disabled

### Networking
- Security groups with port ranges wider than needed
- VPC flow logs disabled
- CloudTrail disabled or without log validation
- Load balancers accepting HTTP (not HTTPS)

### Kubernetes
- Containers running as root (`runAsNonRoot: false` or missing)
- Missing resource limits (CPU/memory)
- `hostNetwork: true` or `hostPID: true`
- Permissive PodSecurityPolicy or missing PodSecurity admission labels
- Service type `LoadBalancer` with no annotation restrictions

### Reliability
- Missing lifecycle rules on S3 buckets (cost + compliance)
- Auto-scaling groups with min_size = 0
- No termination protection on production databases
- Missing backup retention policies

## Ignore
- Local development modules clearly marked as non-production

---
mode: iac_review
focus: Infrastructure-as-Code security and correctness
strictness: high
min_risk: low
model: gemini-1.5-pro
---

## What to Verify
- Confirm security group rules are as permissive as the analyst reports (CIDR ranges can look similar)
- Look for dependency ordering issues the analyst missed (resources referenced before they exist)
- Check for missing `depends_on` that could cause race conditions
- Verify IAM policy ARNs — a wildcard in the resource field is different from one in the action field

## Disagreement Standard
Disagree only when the analyst misread a resource attribute (e.g. confused a deny policy with an allow).

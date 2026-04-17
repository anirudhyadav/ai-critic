---
model: claude-3-5-sonnet
---

## Constraints
- Narrow IAM `*` actions to the specific actions listed in the finding's recommendation
- Add `server_side_encryption_configuration` blocks to S3 resources where missing
- Replace `0.0.0.0/0` CIDR ranges with the specific IP range from the recommendation
- Add `deletion_protection = true` to production database resources
- Do not rename or restructure Terraform modules — only add/fix resource attributes
- For secrets: add `sensitive = true` to outputs, but do not move values to vaults
  (note in skipped_recommendations that vault migration is required)
- Preserve all comments, variable references, and formatting exactly

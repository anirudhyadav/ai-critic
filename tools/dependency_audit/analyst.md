---
mode: dependency_audit
focus: dependency audit
strictness: medium
min_risk: low
model: gemini-1.5-pro
---

## What to Check
- Packages with known CVEs or security advisories in the pinned version
- Outdated major versions with breaking changes or dropped security support
- Unpinned versions (`package>=1.0`) that could pull in a breaking or vulnerable release
- Unused dependencies that add attack surface with no benefit
- Licence conflicts: GPL in a proprietary codebase, missing attribution requirements
- Packages with very few downloads or maintainers (supply chain risk)
- Duplicate packages that provide the same functionality

## Ignore
- Minor patch version differences when no CVE exists
- Dev/test-only dependencies in clearly marked dev dependency sections

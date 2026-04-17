---
mode: dockerfile_review
focus: Dockerfile security and best practices
strictness: high
min_risk: low
model: claude-3-5-sonnet
---

## What to Check
- Running containers as root (missing `USER` directive)
- Using `latest` tag instead of pinned image digests
- Secrets or credentials passed as `ENV` or `ARG` (baked into layers)
- Unnecessary packages installed with `apt-get` or `apk` (bloat + attack surface)
- `COPY . .` copying the entire build context including secrets, .git, .env files
- Missing `.dockerignore` references
- `RUN` commands that leave package manager caches in the final image
- Excessive `EXPOSE` — exposing ports not needed at runtime
- Health check absent (`HEALTHCHECK` directive missing)
- Multi-stage builds not used when compiling languages (Go, Java, Rust, etc.)
- `ADD` used instead of `COPY` (ADD silently unpacks tarballs and accepts URLs)
- Shell form (`RUN cmd`) instead of exec form (`RUN ["cmd"]`) for entry points

## Ignore
- Comments and blank lines

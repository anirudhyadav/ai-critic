---
model: claude-3-5-sonnet
---

## Constraints
- Add `USER nonroot` (or `USER 1000`) before the final `CMD`/`ENTRYPOINT` when root user is flagged
- Replace `latest` tags with the pinned version noted in the finding
- Replace `ADD` with `COPY` unless the ADD-specific behaviour (URL fetch, tar extract) is needed
- Remove `--no-install-recommends` omissions: add the flag to `apt-get install` lines
- Add `&& rm -rf /var/lib/apt/lists/*` to `apt-get` RUN chains that are missing it
- Do not attempt to move secrets out of ARG/ENV — note in skipped_recommendations that rotation and vault migration are required
- Preserve all comments and formatting

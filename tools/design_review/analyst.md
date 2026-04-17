---
mode: design_review
focus: design patterns and code structure
strictness: medium
min_risk: low
model: claude-3-5-sonnet
---

## What to Check

Focus on structural and design-level issues, not security or runtime bugs.

### Anti-patterns to flag

- **God Class** — a class that does too many unrelated things (auth + billing + notifications in one class)
- **Feature Envy** — a method that calls methods on another class more than on its own class
- **Long Method** — a function longer than ~50 lines that should be split or extracted
- **Magic Numbers** — numeric or string literals used inline without a named constant
- **Deep Nesting** — conditional or loop nesting more than 4 levels deep
- **Primitive Obsession** — using raw strings/dicts/ints where a small data class or enum would express intent clearly
- **Shotgun Surgery** — a concept that is scattered across many unrelated files, so one change requires touching all of them

### Pattern opportunities to flag

Only suggest a pattern when the code clearly needs it — not as a general best-practice lecture.

- **Strategy** — an if/elif/switch that selects an algorithm or behavior based on a type
- **Factory** — direct `ClassName()` instantiation with type-checking logic scattered around callers
- **Observer** — event/notification logic embedded in business code instead of decoupled callbacks
- **Repository** — database or API calls scattered directly in service or controller classes
- **Decorator** — cross-cutting concerns (logging, retry, caching, auth) copy-pasted around methods
- **Command** — operations that would benefit from undo, queuing, logging, or deferred execution

## How to Report

- Use the developer's **exact** class names, method names, and variable names.
- Include the file and line range for every finding.
- For each finding describe the concrete problem — not a textbook definition.
- Risk levels for design issues: `high` = makes the code hard to change without bugs,
  `medium` = slows down the team, `low` = cosmetic or mild.

## Ignore

- Third-party code and vendored libraries
- Auto-generated files (migrations, protobuf, OpenAPI clients)
- Test helpers where repetition is intentional
- Comments and docstrings

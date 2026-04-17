"""Inline suppression comment parser.

A suppression comment on or immediately before a flagged line dismisses
that finding from the final report. The models still see — and detect —
the code; suppression is purely a reporting concern.

Supported forms:
  # aicritic: accepted-risk <reason>          Python / shell / Ruby / YAML
  // aicritic: accepted-risk <reason>         JS / TS / Go / Java / C / Rust
  /* aicritic: accepted-risk <reason> */      CSS / block comments
  -- aicritic: accepted-risk <reason>         SQL
  ; aicritic: accepted-risk <reason>          INI / config files

Two placement modes:
  same-line   cursor.execute(raw_query)  # aicritic: accepted-risk ORM handles escaping
  prev-line   # aicritic: accepted-risk validated upstream in the controller
              cursor.execute(raw_query)
"""
import re

_RE = re.compile(
    r'(?:#|//|/\*|--|;)\s*aicritic\s*:\s*accepted-risk\s*(.*?)(?:\s*\*/)?$',
    re.IGNORECASE,
)


def parse_suppressions(content: str) -> dict[int, str]:
    """Return {1-based line number: reason} for every suppression comment in content."""
    result: dict[int, str] = {}
    for i, line in enumerate(content.splitlines(), 1):
        m = _RE.search(line)
        if m:
            result[i] = m.group(1).strip()
    return result


def _parse_range(line_range: str) -> tuple[int, int]:
    """Parse '10-15' or '10' → (10, 15)."""
    try:
        parts = str(line_range).split("-")
        start = int(parts[0].strip())
        end = int(parts[-1].strip()) if len(parts) > 1 and parts[-1].strip() else start
        return start, end
    except (ValueError, IndexError):
        return 0, 0


def apply_suppressions(
    findings: list,
    inputs: dict,
) -> tuple[list, list]:
    """Split findings into (kept, suppressed).

    A finding is suppressed when its file has an accepted-risk comment on any
    line within the finding's range, or on the line immediately before the range.

    Returns:
        kept       — findings to show / act on
        suppressed — findings dismissed by an accepted-risk comment;
                     each has an extra key '_suppressed_reason'
    """
    # Build {path: {line_no: reason}} for every file with at least one suppression
    suppression_map: dict[str, dict[int, str]] = {}
    for f in inputs.get("files", []):
        smap = parse_suppressions(f.get("content", ""))
        if smap:
            suppression_map[f["path"]] = smap

    if not suppression_map:
        return findings, []

    def _lookup(fpath: str) -> dict[int, str] | None:
        if fpath in suppression_map:
            return suppression_map[fpath]
        # Partial path match (model may return basename or relative path)
        for k, v in suppression_map.items():
            if k.endswith(fpath) or fpath.endswith(k):
                return v
        return None

    kept: list = []
    suppressed: list = []
    for finding in findings:
        smap = _lookup(finding.get("file", ""))
        if not smap:
            kept.append(finding)
            continue

        start, end = _parse_range(finding.get("line_range", "0"))
        reason: str | None = None
        # Check prev-line suppression (start-1) through end of range
        for ln in range(max(1, start - 1), end + 1):
            if ln in smap:
                reason = smap[ln]
                break

        if reason is not None:
            suppressed.append({**finding, "_suppressed_reason": reason})
        else:
            kept.append(finding)

    return kept, suppressed

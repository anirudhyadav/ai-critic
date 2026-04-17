"""
Helpers for building compact source context for the critic stage
and for batching large codebases across multiple pipeline runs.
"""
from typing import Iterable


# Approx. chars per batch before we split. At ~4 chars/token this is ~10k tokens
# of source per batch, leaving room for system prompts, findings, and responses
# within a 32k-context model window.
_DEFAULT_BATCH_CHARS = 40_000

# Lines of context to include around each flagged line range
_CONTEXT_RADIUS = 5


def _parse_line_range(line_range) -> tuple:
    """Return (start, end) ints from '12-15', '12', or int. Defaults (1, 1)."""
    if isinstance(line_range, int):
        return (line_range, line_range)
    if not line_range:
        return (1, 1)
    s = str(line_range).strip()
    if "-" in s:
        a, _, b = s.partition("-")
        try:
            return (int(a), int(b))
        except ValueError:
            return (1, 1)
    try:
        n = int(s)
        return (n, n)
    except ValueError:
        return (1, 1)


def _merge_ranges(ranges: list) -> list:
    """Merge overlapping (start, end) ranges. Input need not be sorted."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges)
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:   # touching or overlapping → merge
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def build_finding_context(inputs: dict, findings: Iterable) -> str:
    """
    Return a compact markdown block containing only the source lines
    within ±_CONTEXT_RADIUS of each flagged line range.

    This replaces the full-source-code payload for the critic — cuts critic
    input tokens by ~40% while preserving enough context for arbitration.
    """
    lines_by_path = {
        f["path"]: f["content"].splitlines()
        for f in inputs.get("files", [])
    }

    # Group finding ranges by file
    ranges_by_path: dict = {}
    for f in findings:
        path = f.get("file")
        if not path or path not in lines_by_path:
            continue
        start, end = _parse_line_range(f.get("line_range"))
        ctx_start = max(1, start - _CONTEXT_RADIUS)
        ctx_end   = end + _CONTEXT_RADIUS
        ranges_by_path.setdefault(path, []).append((ctx_start, ctx_end))

    if not ranges_by_path:
        return (
            "_(No findings had resolvable line references — "
            "critic will work from the findings JSON only.)_"
        )

    sections = []
    for path in sorted(ranges_by_path):
        source_lines = lines_by_path[path]
        merged = _merge_ranges(ranges_by_path[path])

        chunks = []
        for start, end in merged:
            end = min(end, len(source_lines))
            if start > len(source_lines):
                continue
            numbered = "\n".join(
                f"{start + i:>4}: {source_lines[start - 1 + i]}"
                for i in range(end - start + 1)
            )
            chunks.append(f"```\n{numbered}\n```")

        if chunks:
            sections.append(f"## {path}\n\n" + "\n\n".join(chunks))

    return "\n\n".join(sections)


def split_into_batches(inputs: dict, max_chars: int = _DEFAULT_BATCH_CHARS) -> list:
    """
    Split inputs into batches where each batch's total source content is
    under max_chars. Files that individually exceed max_chars get their
    own single-file batch (they'll still run, just closer to the limit).

    Each batch is a fully-formed inputs dict — pass it to run_analyst etc.
    unchanged.
    """
    files = inputs.get("files", [])
    coverage = inputs.get("coverage")
    mode = inputs.get("mode", "security")

    if not files:
        return [inputs]

    batches: list = []
    current: list = []
    current_size = 0

    for f in files:
        size = len(f.get("content", ""))
        if current and current_size + size > max_chars:
            batches.append(current)
            current = []
            current_size = 0
        current.append(f)
        current_size += size

    if current:
        batches.append(current)

    return [
        {"files": b, "coverage": coverage, "mode": mode}
        for b in batches
    ]


def merge_stage_results(results: list) -> dict:
    """
    Merge a list of analyst/checker results from separate batches into one.

    Preserves _role_config from the first non-empty result, concatenates
    findings/agreements/disagreements, and joins summaries with ' | '.
    """
    if not results:
        return {"findings": [], "agreements": [], "disagreements": [], "summary": ""}
    if len(results) == 1:
        return results[0]

    merged = {
        "model":         results[0].get("model", ""),
        "role":          results[0].get("role", ""),
        "findings":      [],
        "agreements":    [],
        "disagreements": [],
        "summary":       "",
    }

    summaries = []
    for r in results:
        merged["findings"].extend(r.get("findings", []))
        merged["agreements"].extend(r.get("agreements", []))
        merged["disagreements"].extend(r.get("disagreements", []))
        if r.get("summary"):
            summaries.append(r["summary"])
        # Carry forward internal keys from the first batch that has them
        for k, v in r.items():
            if k.startswith("_") and k not in merged:
                merged[k] = v

    merged["summary"] = " | ".join(summaries)
    return merged

"""Baseline persistence — save findings to a JSON file, then filter future
runs so only *new* findings surface. Enables CI gating on deltas."""
import hashlib
import json
import os
from typing import Optional


def _fingerprint(finding: dict) -> str:
    """Stable hash for (file, line_range, first N chars of description).

    Line numbers drift as code changes, so we truncate the description to a
    short prefix rather than hashing the whole thing — this keeps the
    fingerprint stable across minor edits to the surrounding context while
    still distinguishing genuinely different issues."""
    key = "|".join([
        (finding.get("file") or "").strip(),
        (str(finding.get("line_range") or "")).strip(),
        (finding.get("description") or "")[:80].strip().lower(),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def load_baseline(path: str) -> set:
    """Load a set of fingerprints from a baseline JSON file."""
    if not path or not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return set(data.get("fingerprints", []))


def save_baseline(path: str, critic_output: dict, target: str) -> str:
    """Write fingerprints of the current run's findings to `path`."""
    fps = sorted({_fingerprint(f) for f in critic_output.get("findings", [])})
    payload = {
        "version": 1,
        "target": target,
        "count": len(fps),
        "fingerprints": fps,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def filter_new(critic_output: dict, baseline_fps: set) -> dict:
    """Return a copy of critic_output with findings/recommendations limited to
    those whose fingerprint is NOT in the baseline."""
    if not baseline_fps:
        return critic_output

    new_findings = [
        f for f in critic_output.get("findings", [])
        if _fingerprint(f) not in baseline_fps
    ]
    # Recommendations reference findings by file; drop recs whose file no longer
    # has a surviving finding.
    surviving_files = {f.get("file") for f in new_findings}
    new_recs = [
        r for r in critic_output.get("recommendations", [])
        if r.get("file") in surviving_files or not r.get("file")
    ]

    out = dict(critic_output)
    out["findings"] = new_findings
    out["recommendations"] = new_recs
    out["_baseline_suppressed"] = (
        len(critic_output.get("findings", [])) - len(new_findings)
    )
    return out

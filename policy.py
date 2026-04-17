"""CI policy loader — reads .aicritic-policy.yaml and evaluates merge gates.

Example .aicritic-policy.yaml:
  block_on: [critical, high]   # risk levels that fail CI (exit code 1)
  tool: security_review        # analysis profile
  min_risk: low                # minimum risk level to surface in the report
  diff_only: true              # only analyse files changed in this PR
  skip_checker: false          # skip Gemini cross-check (faster, less thorough)
  paths: []                    # directories/files to scan (empty = CLI target)
"""
import os
import re

_FILENAMES = (".aicritic-policy.yaml", ".aicritic-policy.yml")

_DEFAULTS: dict = {
    "block_on":     ["critical", "high"],
    "tool":         None,
    "min_risk":     "low",
    "diff_only":    True,
    "skip_checker": False,
    "paths":        [],
}


def _parse(text: str) -> dict:
    """Minimal YAML parser: scalars, booleans, and flat/inline lists."""
    result: dict = {}
    list_key: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            list_key = None if not line.lstrip().startswith("#") else list_key
            continue
        stripped = line.lstrip()
        if stripped.startswith("- ") and list_key is not None:
            result.setdefault(list_key, []).append(stripped[2:].strip().strip("\"'"))
            continue
        list_key = None
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v == "":
            list_key = k
            result.setdefault(k, [])
        elif v == "[]":
            result[k] = []
        elif v.lower() == "true":
            result[k] = True
        elif v.lower() == "false":
            result[k] = False
        else:
            m = re.match(r'^\[(.+)\]$', v)
            if m:
                result[k] = [i.strip().strip("\"'") for i in m.group(1).split(",")]
            else:
                result[k] = v.strip("\"'")
    return result


def load(start: str) -> dict:
    """Find and load the nearest .aicritic-policy.yaml. Returns defaults if absent."""
    current = os.path.abspath(start if os.path.isdir(start) else os.path.dirname(start) or ".")
    for _ in range(8):
        for fname in _FILENAMES:
            path = os.path.join(current, fname)
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        raw = _parse(fh.read())
                    merged = dict(_DEFAULTS)
                    for k, v in raw.items():
                        if k in merged and v is not None:
                            merged[k] = v
                    return merged
                except OSError:
                    return dict(_DEFAULTS)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return dict(_DEFAULTS)


def check_policy(critic_result: dict, policy: dict) -> tuple[bool, list]:
    """Evaluate findings against the policy.

    Returns:
        blocked           — True if CI should exit 1
        blocking_findings — findings at a blocking risk level
    """
    import config as _cfg
    block_levels = {r.lower() for r in policy.get("block_on", _DEFAULTS["block_on"])}
    findings = critic_result.get("findings", [])
    blocking = [f for f in findings if f.get("risk", "low").lower() in block_levels]
    return bool(blocking), blocking

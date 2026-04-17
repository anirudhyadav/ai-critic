"""Load project-level defaults from .aicritic.yaml.

The config file is optional. When present it provides defaults for every CLI
flag so teams can set them once per repo. CLI flags always take precedence.

Example .aicritic.yaml:
    tool: secrets_scan
    min_risk: high
    skip_checker: false
    parallel: false
    languages:
      - python
      - typescript
    notify_slack: https://hooks.slack.com/services/...
    notify_teams: https://outlook.office.com/webhook/...
    baseline: .aicritic_baseline.json
    sarif: aicritic.sarif
    output: reports/aicritic_report.md
"""
import os

_FILENAME = ".aicritic.yaml"
_DEFAULTS = {
    "tool":           None,
    "min_risk":       None,
    "skip_checker":   False,
    "parallel":       False,
    "languages":      None,
    "notify_slack":   None,
    "notify_teams":   None,
    "baseline":       None,
    "save_baseline":  None,
    "sarif":          None,
    "output":         None,
    "diff":           None,
    "roles":          None,
}


def _find_config(start: str) -> str | None:
    """Walk up from `start` looking for .aicritic.yaml."""
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, _FILENAME)
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _parse_yaml_simple(text: str) -> dict:
    """Tiny YAML parser — handles flat key: value and simple lists only.
    We intentionally avoid a PyYAML dependency for this optional feature.
    Falls back gracefully if the structure is unsupported.
    """
    result = {}
    current_list_key = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        # List item under a key
        stripped = line.lstrip()
        if stripped.startswith("- ") and current_list_key:
            result.setdefault(current_list_key, []).append(stripped[2:].strip())
            continue
        if ":" in line:
            current_list_key = None
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if v == "" or v is None:
                # Key with no value on the same line — may be a list header
                current_list_key = k
                continue
            # Boolean coercion
            if v.lower() == "true":
                result[k] = True
            elif v.lower() == "false":
                result[k] = False
            elif v.lower() in ("null", "~", "none", ""):
                result[k] = None
            else:
                result[k] = v
    return result


def load(start: str = ".") -> dict:
    """Return a merged config dict with defaults.

    Keys map directly to CLI arg names (snake_case). CLI args should be
    applied on top of this dict — CLI always wins.
    """
    config = dict(_DEFAULTS)
    path = _find_config(start if os.path.isdir(start) else os.path.dirname(start) or ".")
    if not path:
        return config
    try:
        with open(path, encoding="utf-8") as fh:
            parsed = _parse_yaml_simple(fh.read())
        for k, v in parsed.items():
            if k in config:
                config[k] = v
    except OSError:
        pass
    return config


def apply_to_args(args, config: dict) -> None:
    """Overlay config values onto parsed argparse Namespace.
    Only fills in values the user did not explicitly set on the CLI.
    """
    for key, value in config.items():
        if value is None:
            continue
        # Only override if the arg is still at its argparse default
        current = getattr(args, key, None)
        if current is None or current is False:
            # For booleans, only override False → True (never True → False)
            if isinstance(value, bool) and not value:
                continue
            setattr(args, key, value)

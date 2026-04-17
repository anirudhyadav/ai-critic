"""Load team design conventions from .aicritic-patterns.yaml.

The file is optional. If absent, sensible defaults are returned so the
pattern advisor still runs with standard thresholds.

Example .aicritic-patterns.yaml:

    # Complexity thresholds
    max_method_lines: 50
    max_cyclomatic_complexity: 10
    max_class_lines: 300
    max_nesting_depth: 4

    # Pattern preferences
    approved_patterns:
      - Repository
      - Strategy
      - Factory

    avoid_patterns:
      - Singleton

    prefer_composition: true
    use_repository: true        # flag Feature Envy for any direct DB calls outside repo
"""
import os

_DEFAULTS = {
    "max_method_lines":          50,
    "max_cyclomatic_complexity": 10,
    "max_class_lines":           300,
    "max_nesting_depth":         4,
    "approved_patterns":         [],
    "avoid_patterns":            [],
    "prefer_composition":        None,
    "use_repository":            None,
}

_FILENAME = ".aicritic-patterns.yaml"


def _parse_yaml_simple(text: str) -> dict:
    """Zero-dependency YAML subset parser.

    Handles: scalar key: value, list items starting with '- ', and comments.
    Does not handle nested mappings or multi-line values.
    """
    result: dict = {}
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("- "):
            if current_list_key:
                result[current_list_key].append(line[2:].strip())
            continue

        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if not v:
                # Start of a list block
                result[k] = []
                current_list_key = k
            else:
                current_list_key = None
                # Inline list: key: [a, b, c]
                if v.startswith("[") and v.endswith("]"):
                    items = [i.strip().strip("\"'") for i in v[1:-1].split(",") if i.strip()]
                    result[k] = items
                else:
                    # Scalar — coerce bool/int
                    lv = v.lower()
                    if lv in ("true", "yes"):
                        result[k] = True
                    elif lv in ("false", "no"):
                        result[k] = False
                    else:
                        try:
                            result[k] = int(v)
                        except ValueError:
                            result[k] = v.strip("\"'")

    return result


def load(start: str = ".") -> dict:
    """Walk up from `start` looking for .aicritic-patterns.yaml.

    Returns a merged dict of defaults + file values. Never raises.
    """
    config = dict(_DEFAULTS)

    path = _find(start)
    if path is None:
        return config

    try:
        with open(path, encoding="utf-8") as fh:
            parsed = _parse_yaml_simple(fh.read())
    except OSError:
        return config

    # Merge parsed values over defaults
    for k, default in _DEFAULTS.items():
        if k in parsed:
            val = parsed[k]
            # Type-check list fields
            if isinstance(default, list) and not isinstance(val, list):
                continue
            config[k] = val

    return config


def _find(start: str) -> str | None:
    candidate = os.path.abspath(start)
    if os.path.isfile(candidate):
        candidate = os.path.dirname(candidate)

    # Walk up at most 6 directory levels
    for _ in range(6):
        path = os.path.join(candidate, _FILENAME)
        if os.path.isfile(path):
            return path
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent

    return None

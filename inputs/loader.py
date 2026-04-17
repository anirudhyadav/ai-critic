import os
import xml.etree.ElementTree as ET
from pathlib import Path

_SKIP_DIRS = {"__pycache__", ".venv", "venv", "env", "node_modules", ".git", "dist", "build"}


def _read_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return {"path": path, "content": f.read()}


def load_source_files(target: str) -> list:
    """Return [{path, content}] for all .py files at target (file or directory)."""
    p = Path(target)
    if p.is_file():
        return [_read_file(str(p))]

    files = []
    for root, dirs, names in os.walk(p):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            if name.endswith(".py"):
                files.append(_read_file(os.path.join(root, name)))
    return files


def parse_coverage_xml(xml_path: str) -> dict:
    """
    Parse a coverage.xml produced by `coverage xml`.
    Returns {filename: {line_rate: float, missing_lines: [int, ...]}}
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        raise ValueError(f"Could not parse coverage XML '{xml_path}': {e}") from e
    root = tree.getroot()
    result = {}
    for cls in root.iter("class"):
        filename = cls.get("filename", "unknown")
        line_rate = float(cls.get("line-rate", 0))
        missing = [
            int(line.get("number"))
            for line in cls.iter("line")
            if line.get("hits") == "0" and line.get("number", "").isdigit()
        ]
        result[filename] = {"line_rate": line_rate, "missing_lines": missing}
    return result


def from_text(files: dict, mode: str = "security") -> dict:
    """
    Build an inputs dict from a {filename: content} mapping.
    Used by the Copilot Extension where code arrives as text, not file paths.

    Args:
        files: {"snippet_1.py": "def login(...): ...", ...}
        mode:  "security" | "coverage" | any tool mode string
    """
    return {
        "files":    [{"path": path, "content": content} for path, content in files.items()],
        "coverage": None,
        "mode":     mode,
    }


def load_inputs(target: str, coverage_xml: str = None, diff_ref: str = None) -> dict:
    """
    Main entry point.

    Args:
        target: file or directory to analyse.
        coverage_xml: optional coverage.xml path.
        diff_ref: if set, restrict `files` to only those changed between
            `diff_ref` and HEAD. Useful for PR-style review.

    Returns:
        {
            "files":    [{path, content}, ...],
            "coverage": {filename: {line_rate, missing_lines}} | None,
            "mode":     "security" | "coverage",
            "diff":     {path: [(start, end), ...]} | None,
        }
    """
    files = load_source_files(target)
    if not files:
        raise ValueError(f"No Python source files found at: {target}")

    diff_map = None
    if diff_ref:
        from inputs.git_diff import changed_files, changed_line_ranges, GitDiffError
        try:
            changed = set(os.path.abspath(p) for p in changed_files(diff_ref, target))
        except GitDiffError as e:
            raise ValueError(str(e)) from e
        files = [f for f in files if os.path.abspath(f["path"]) in changed]
        if not files:
            raise ValueError(
                f"No .py files changed between '{diff_ref}' and HEAD under '{target}'"
            )
        diff_map = {}
        for f in files:
            try:
                diff_map[f["path"]] = changed_line_ranges(diff_ref, f["path"])
            except GitDiffError:
                diff_map[f["path"]] = []

    coverage = None
    mode = "security"
    if coverage_xml:
        coverage = parse_coverage_xml(coverage_xml)
        mode = "coverage"

    return {"files": files, "coverage": coverage, "mode": mode, "diff": diff_map}

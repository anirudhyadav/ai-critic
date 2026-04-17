import fnmatch
import os
import xml.etree.ElementTree as ET
from pathlib import Path

_SKIP_DIRS = {
    "__pycache__", ".venv", "venv", "env", "node_modules",
    ".git", "dist", "build", "target", ".next", ".nuxt",
    "coverage", ".coverage", "htmlcov",
}

# Extensions grouped by language — used for display and prompt context
LANGUAGE_EXTENSIONS = {
    "python":     {".py"},
    "javascript": {".js", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx"},
    "go":         {".go"},
    "java":       {".java"},
    "ruby":       {".rb"},
    "rust":       {".rs"},
    "csharp":     {".cs"},
    "php":        {".php"},
    "kotlin":     {".kt"},
    "swift":      {".swift"},
    "shell":      {".sh", ".bash"},
    "dockerfile": {"Dockerfile", ".dockerfile"},
    "terraform":  {".tf", ".tfvars"},
    "yaml":       {".yml", ".yaml"},
    "sql":        {".sql"},
}

# Flat set of all supported extensions (plus bare filenames like "Dockerfile")
_ALL_EXTENSIONS: set = set()
_ALL_BARE_NAMES: set = set()
for _lang, _exts in LANGUAGE_EXTENSIONS.items():
    for _e in _exts:
        if _e.startswith("."):
            _ALL_EXTENSIONS.add(_e)
        else:
            _ALL_BARE_NAMES.add(_e)

_MAX_FILE_BYTES = 500_000   # 500 KB — warn above this, skip above 2 MB
_SKIP_FILE_BYTES = 2_000_000

# Bytes that strongly indicate binary content
_BINARY_CHECK_LEN = 8192


def _is_binary(path: str) -> bool:
    """Quick binary-file check — reads first 8 KB and looks for null bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_CHECK_LEN)
        return b"\x00" in chunk
    except OSError:
        return False


def _read_file(path: str) -> dict | None:
    """Read a source file. Returns None if the file should be skipped."""
    size = os.path.getsize(path)
    if size > _SKIP_FILE_BYTES:
        print(f"  [skipped] {path} — file too large ({size // 1024} KB), increase limit if needed")
        return None
    if _is_binary(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as f:
            content = f.read()
    except UnicodeDecodeError:
        # Not valid UTF-8 — treat as binary
        return None
    if size > _MAX_FILE_BYTES:
        print(f"  [warning] {path} is large ({size // 1024} KB) — analysis may be less precise")
    return {"path": path, "content": content}


def _load_ignorefile(root: str) -> list:
    """Load .aicriticignore patterns (gitignore-style globs) from `root`."""
    ignore_path = os.path.join(root, ".aicriticignore")
    if not os.path.exists(ignore_path):
        return []
    with open(ignore_path, encoding="utf-8") as fh:
        return [
            line.strip()
            for line in fh
            if line.strip() and not line.startswith("#")
        ]


def _is_ignored(rel_path: str, patterns: list) -> bool:
    """Return True if rel_path matches any .aicriticignore glob pattern."""
    for pat in patterns:
        if fnmatch.fnmatch(rel_path, pat):
            return True
        if fnmatch.fnmatch(os.path.basename(rel_path), pat):
            return True
    return False


def _is_source_file(name: str) -> bool:
    """True if the filename is a supported source file."""
    _, ext = os.path.splitext(name)
    return ext.lower() in _ALL_EXTENSIONS or name in _ALL_BARE_NAMES


def detect_language(path: str) -> str:
    """Return the language label for a file path, or 'unknown'."""
    name = os.path.basename(path)
    _, ext = os.path.splitext(name)
    ext_lower = ext.lower()
    for lang, exts in LANGUAGE_EXTENSIONS.items():
        if ext_lower in exts or name in exts:
            return lang
    return "unknown"


def load_source_files(target: str, languages: list = None) -> list:
    """Return [{path, content, language}] for all supported source files.

    Args:
        target: file or directory.
        languages: optional whitelist e.g. ['python', 'typescript'].
    """
    allowed_exts: set = _ALL_EXTENSIONS
    allowed_names: set = _ALL_BARE_NAMES
    if languages:
        allowed_exts = set()
        allowed_names = set()
        for lang in languages:
            for ext in LANGUAGE_EXTENSIONS.get(lang, set()):
                if ext.startswith("."):
                    allowed_exts.add(ext)
                else:
                    allowed_names.add(ext)

    p = Path(target)

    if not p.exists():
        raise FileNotFoundError(
            f"Path not found: '{target}'\n"
            f"Check the path is correct and try again."
        )

    if p.is_file():
        f = _read_file(str(p))
        if f is None:
            raise ValueError(f"Cannot read '{target}' — file is binary or not valid UTF-8.")
        f["language"] = detect_language(str(p))
        return [f]

    if not p.is_dir():
        raise ValueError(f"'{target}' is neither a file nor a directory.")

    ignore_patterns = _load_ignorefile(str(p))

    files = []
    for root, dirs, names in os.walk(p):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(names):
            _, ext = os.path.splitext(name)
            if ext.lower() not in allowed_exts and name not in allowed_names:
                continue
            full_path = os.path.join(root, name)
            rel = os.path.relpath(full_path, p)
            if ignore_patterns and _is_ignored(rel, ignore_patterns):
                continue
            f = _read_file(full_path)
            if f is None:
                continue
            f["language"] = detect_language(full_path)
            files.append(f)
    return files


def parse_coverage_xml(xml_path: str) -> dict:
    """Parse a coverage.xml produced by `coverage xml`."""
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
    """Build an inputs dict from a {filename: content} mapping."""
    return {
        "files":    [
            {"path": path, "content": content, "language": detect_language(path)}
            for path, content in files.items()
        ],
        "coverage": None,
        "mode":     mode,
        "diff":     None,
    }


def load_inputs(
    target: str,
    coverage_xml: str = None,
    diff_ref: str = None,
    languages: list = None,
) -> dict:
    """Main entry point for loading source files.

    Raises FileNotFoundError or ValueError with a clear message on failure.
    """
    files = load_source_files(target, languages=languages)
    if not files:
        lang_hint = f" ({', '.join(languages)})" if languages else ""
        tip = ""
        if languages:
            supported = ", ".join(sorted(LANGUAGE_EXTENSIONS.keys()))
            tip = f"\n\nSupported languages: {supported}"
        raise ValueError(
            f"No source files found at: '{target}'{lang_hint}\n\n"
            f"aicritic looks for: {', '.join(sorted(_ALL_EXTENSIONS)[:12])} and more.\n"
            f"If your files are there, check that they aren't excluded by .aicriticignore."
            f"{tip}"
        )

    diff_map = None
    if diff_ref:
        from inputs.git_diff import changed_files, changed_line_ranges, GitDiffError
        try:
            changed = set(os.path.abspath(p) for p in changed_files(diff_ref, target))
        except GitDiffError as e:
            raise ValueError(
                f"Could not get git diff against '{diff_ref}': {e}\n\n"
                f"Make sure the ref exists: try `git log --oneline {diff_ref}`"
            ) from e
        files = [f for f in files if os.path.abspath(f["path"]) in changed]
        if not files:
            raise ValueError(
                f"No source files changed between '{diff_ref}' and HEAD under '{target}'.\n\n"
                f"This is normal if your current branch hasn't touched any source files yet.\n"
                f"Run without --diff to analyse everything: aicritic check {target}"
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

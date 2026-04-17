"""Resolve changed files (and optionally line ranges) from a git ref."""
import os
import subprocess
from typing import Optional


class GitDiffError(RuntimeError):
    pass


def _run(args: list, cwd: str) -> str:
    try:
        out = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        raise GitDiffError("git is not installed or not on PATH") from e
    except subprocess.CalledProcessError as e:
        raise GitDiffError(
            f"git {' '.join(args)} failed: {e.stderr.strip() or e.stdout.strip()}"
        ) from e
    return out.stdout


def _repo_root(start: str) -> str:
    root = _run(["rev-parse", "--show-toplevel"], cwd=start).strip()
    if not root:
        raise GitDiffError(f"'{start}' is not inside a git repository")
    return root


def changed_files(ref: str, target: str) -> list:
    """Return absolute paths of .py files changed between `ref` and HEAD,
    restricted to files under `target` (file or directory)."""
    start = target if os.path.isdir(target) else os.path.dirname(target) or "."
    repo = _repo_root(start)
    raw = _run(["diff", "--name-only", f"{ref}...HEAD"], cwd=repo).splitlines()

    target_abs = os.path.abspath(target)
    out = []
    for rel in raw:
        if not rel.endswith(".py"):
            continue
        abs_path = os.path.join(repo, rel)
        if os.path.abspath(abs_path).startswith(target_abs) and os.path.isfile(abs_path):
            out.append(abs_path)
    return out


def changed_line_ranges(ref: str, path: str) -> list:
    """Parse unified-diff hunk headers for `path` vs `ref` → [(start, end), ...]."""
    start = os.path.dirname(path) or "."
    repo = _repo_root(start)
    raw = _run(
        ["diff", "-U0", f"{ref}...HEAD", "--", os.path.relpath(path, repo)],
        cwd=repo,
    )
    ranges = []
    for line in raw.splitlines():
        if not line.startswith("@@"):
            continue
        # @@ -a,b +c,d @@   — we want c..c+d-1
        try:
            plus = line.split("+", 1)[1].split(" ", 1)[0]
            if "," in plus:
                c, d = plus.split(",", 1)
                c, d = int(c), int(d)
            else:
                c, d = int(plus), 1
            if d == 0:
                continue
            ranges.append((c, c + d - 1))
        except (ValueError, IndexError):
            continue
    return ranges

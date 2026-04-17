"""Open a GitHub PR from fixer output.

Flow:
  1. Detect repo owner/name from `git remote get-url origin`
  2. Create a fresh branch `aicritic/fix-<timestamp>` from current HEAD
  3. Stage the files the fixer rewrote, commit, push
  4. POST /repos/{owner}/{repo}/pulls via the REST API using GITHUB_TOKEN

Falls back with a clear error message if any step fails — the caller can
still rely on local fixes having been written."""
import json
import os
import re
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional


class PRError(RuntimeError):
    pass


def _run(args: list, cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd, check=True, capture_output=True, text=True
        )
        return r.stdout
    except FileNotFoundError as e:
        raise PRError("git is not installed") from e
    except subprocess.CalledProcessError as e:
        raise PRError(
            f"git {' '.join(args)} failed: {e.stderr.strip() or e.stdout.strip()}"
        ) from e


def _repo_root(start: str) -> str:
    return _run(["rev-parse", "--show-toplevel"], cwd=start).strip()


def _parse_owner_repo(remote_url: str) -> tuple:
    """Accept both https and ssh remote URLs."""
    # git@github.com:owner/repo(.git)?
    m = re.match(r"(?:git@[^:]+:|https?://[^/]+/)([^/]+)/([^/.]+)", remote_url.strip())
    if not m:
        raise PRError(f"Could not parse owner/repo from remote URL: {remote_url}")
    return m.group(1), m.group(2)


def _api_host(remote_url: str) -> str:
    """github.com → api.github.com; GHES host.example.com → host.example.com/api/v3."""
    m = re.match(r"(?:git@([^:]+):|https?://([^/]+)/)", remote_url.strip())
    if not m:
        return "api.github.com"
    host = m.group(1) or m.group(2)
    return "api.github.com" if host == "github.com" else f"{host}/api/v3"


def _base_branch(cwd: str) -> str:
    """Return the remote HEAD branch, or fall back to 'main'."""
    try:
        ref = _run(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd).strip()
        return ref.split("/")[-1] if ref else "main"
    except PRError:
        return "main"


def _parse_end_line(line_range: str) -> int | None:
    """Return the last line number from a range string like '10-15' or '10'."""
    try:
        parts = str(line_range).split("-")
        return int(parts[-1].strip()) if parts[-1].strip() else int(parts[0].strip())
    except (ValueError, IndexError):
        return None


def _post_review_comments(
    api_host: str,
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    critic_result: dict,
    repo_dir: str,
) -> None:
    """Post inline review comments on the PR for each finding. Never raises."""
    findings = critic_result.get("findings", []) if critic_result else []
    if not findings:
        return

    _RISK_BADGE = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "medium": "🟡 MEDIUM", "low": "🔵 LOW"}

    comments = []
    for f in findings:
        line = _parse_end_line(f.get("line_range", ""))
        if not line:
            continue
        raw_path = f.get("file", "")
        try:
            rel_path = os.path.relpath(raw_path, repo_dir) if os.path.isabs(raw_path) else raw_path
        except ValueError:
            rel_path = raw_path

        risk = f.get("risk", "low").lower()
        badge = _RISK_BADGE.get(risk, risk.upper())
        body = f"**{badge}** — {f.get('description', '(no description)')}"
        comments.append({"path": rel_path, "line": line, "side": "RIGHT", "body": body})

    if not comments:
        return

    high_count = sum(1 for f in findings if f.get("risk") in ("high", "critical"))
    verdict = critic_result.get("verdict", f"{len(findings)} finding(s)")
    review_body = (
        f"## aicritic — `{verdict}`\n\n"
        f"{len(findings)} finding(s) · {high_count} high/critical\n\n"
        f"> Inline comments below show individual findings."
    )

    url = f"https://{api_host}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
    payload = json.dumps({
        "body": review_body,
        "event": "COMMENT",
        "comments": comments,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "aicritic",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except (urllib.error.HTTPError, urllib.error.URLError):
        pass  # review comments are best-effort — never break the PR flow


def open_pr_from_fixes(
    fixer_result: dict,
    target: str,
    tool_label: str,
    token: str,
    summary: str = "",
    critic_result: dict | None = None,
) -> str:
    """Create branch, commit, push, open PR. Returns the PR URL."""
    if not token:
        raise PRError("GITHUB_TOKEN not set — cannot open PR")

    fixed = fixer_result.get("files", []) + [
        {"path": f["path"]} for f in fixer_result.get("applied_literal", [])
    ]
    paths = sorted({f["path"] for f in fixed})
    if not paths:
        raise PRError("No files were modified — nothing to open a PR for")

    start = target if os.path.isdir(target) else os.path.dirname(target) or "."
    repo_dir = _repo_root(start)

    remote = _run(["remote", "get-url", "origin"], repo_dir).strip()
    owner, repo = _parse_owner_repo(remote)
    api_host = _api_host(remote)
    base = _base_branch(repo_dir)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch = f"aicritic/fix-{tool_label}-{timestamp}"

    _run(["checkout", "-b", branch], repo_dir)
    for p in paths:
        rel = os.path.relpath(p, repo_dir)
        _run(["add", "--", rel], repo_dir)

    commit_msg = f"aicritic: auto-fix ({tool_label})\n\n{summary or fixer_result.get('summary', '')}"
    _run(["commit", "-m", commit_msg], repo_dir)
    _run(["push", "-u", "origin", branch], repo_dir)

    pr_title = f"aicritic auto-fix: {tool_label}"
    pr_body = (
        f"Automated fix generated by aicritic.\n\n"
        f"**Tool:** `{tool_label}`\n"
        f"**Files changed:** {len(paths)}\n\n"
        f"### Summary\n{summary or fixer_result.get('summary') or '(no summary)'}\n\n"
        f"### Changes applied\n"
        + "\n".join(f"- `{os.path.relpath(p, repo_dir)}`" for p in paths)
        + "\n\n> Review each change before merging. "
        "aicritic's fixer is deterministic for literal patches but LLM-assisted "
        "for anything ambiguous."
    )

    url = f"https://{api_host}/repos/{owner}/{repo}/pulls"
    payload = json.dumps({
        "title": pr_title,
        "body":  pr_body,
        "head":  branch,
        "base":  base,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "aicritic",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise PRError(f"GitHub API returned {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise PRError(f"Could not reach GitHub API: {e.reason}") from e

    pr_number = data.get("number")
    if pr_number and critic_result:
        _post_review_comments(api_host, owner, repo, pr_number, token, critic_result, repo_dir)

    return data.get("html_url", f"(PR created but URL missing — branch {branch})")

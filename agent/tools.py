"""Tool schemas (OpenAI function-calling format) and their handlers.

Each handler receives (args: dict, session: AgentSession) and returns a string
that goes back to Claude as the tool result. Handlers NEVER raise — they return
an error string so Claude can decide how to proceed.
"""
import json
import os
import subprocess

from agent.session import AgentSession

# ---------------------------------------------------------------------------
# Schema definitions — what Claude sees
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_changed_files",
            "description": (
                "List Python/source files changed between a git ref and HEAD. "
                "Use this before run_analysis when the task is PR-scoped."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "Git ref to diff against, e.g. 'main', 'HEAD~1', 'origin/main'",
                    }
                },
                "required": ["ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_files",
            "description": (
                "Load source files from the target path into the session. "
                "Required before run_analysis when NOT using get_changed_files. "
                "Accepts optional language filter."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "languages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional language filter e.g. ['python', 'typescript']",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_analysis",
            "description": (
                "Run the three-model critic chain (Sonnet → Gemini → Opus) on the "
                "loaded files. Returns a findings summary. Must call read_files or "
                "get_changed_files first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "description": (
                            "Analysis tool profile: security_review, secrets_scan, "
                            "error_handling, performance, pr_review, test_quality, "
                            "migration_safety, code_coverage, dependency_audit, "
                            "dockerfile_review, iac_review"
                        ),
                    },
                    "skip_checker": {
                        "type": "boolean",
                        "description": "Skip Gemini cross-check for speed (~20s vs ~90s)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_fixes",
            "description": (
                "Apply the critic's recommendations to source files. "
                "Phase 1 applies deterministic literal patches; phase 2 uses "
                "an LLM rewrite for the rest. Returns a diff summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "min_risk": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Only fix findings at or above this risk level",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_pr",
            "description": (
                "Create a branch with the applied fixes, push it, and open a GitHub "
                "pull request. Only call after apply_fixes has been run."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Optional PR title override",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a single source file and return its contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file. Use only for small targeted edits "
                "when the fixer is overkill (e.g. adding a single config line)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Full file content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command (linter, test suite, syntax check) and return "
                "stdout + exit code. Use to verify fixes didn't break anything. "
                "Commands are sandboxed to the target directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run, e.g. 'python -m pytest', 'ruff check .'",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 60)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_baseline",
            "description": (
                "Save the current run's findings as a baseline so future runs "
                "only surface NEW issues."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Where to save the baseline JSON (default: .aicritic_baseline.json)",
                    }
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_get_changed_files(args: dict, session: AgentSession) -> str:
    ref = args.get("ref", "HEAD~1")
    try:
        from inputs.git_diff import changed_files, changed_line_ranges, GitDiffError
        from inputs.loader import load_source_files, detect_language
        paths = changed_files(ref, session.target)
        if not paths:
            return f"No source files changed between '{ref}' and HEAD."
        files = []
        for p in paths:
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                files.append({"path": p, "content": content, "language": detect_language(p)})
            except OSError:
                continue
        if not files:
            return "Changed files found but none could be read."
        session.inputs = {"files": files, "coverage": None, "mode": "security", "diff": None}
        session.log(f"get_changed_files({ref}): {len(files)} file(s) loaded")
        return f"Loaded {len(files)} changed file(s): {', '.join(os.path.basename(f['path']) for f in files)}"
    except Exception as e:
        return f"Error: {e}"


def _handle_read_files(args: dict, session: AgentSession) -> str:
    languages = args.get("languages") or None
    try:
        from inputs.loader import load_inputs
        session.inputs = load_inputs(session.target, languages=languages)
        n = len(session.inputs["files"])
        session.log(f"read_files: {n} file(s) loaded")
        return f"Loaded {n} file(s) from {session.target}"
    except Exception as e:
        return f"Error loading files: {e}"


def _handle_run_analysis(args: dict, session: AgentSession) -> str:
    if not session.inputs:
        return "Error: no files loaded — call read_files or get_changed_files first."
    tool = args.get("tool") or session.tool_label or "security_review"
    skip_checker = args.get("skip_checker", False)

    import config
    from pipeline.analyst import run_analyst
    from pipeline.checker import run_checker, skipped_result as checker_skipped
    from pipeline.critic  import run_critic
    from pipeline.batching import split_into_batches, merge_stage_results

    roles_dir = session.roles_dir
    if not roles_dir and tool != "security_review":
        candidate = os.path.join(config.TOOLS_DIR, tool)
        if os.path.isdir(candidate):
            roles_dir = candidate

    try:
        batches = split_into_batches(session.inputs)
        analyst_results, checker_results = [], []
        for batch in batches:
            a = run_analyst(batch, roles_dir, token=session.token)
            c = checker_skipped("disabled via agent --skip-checker") if skip_checker else run_checker(batch, a, roles_dir, token=session.token)
            analyst_results.append(a)
            checker_results.append(c)
        session.analyst_result = merge_stage_results(analyst_results)
        session.checker_result = merge_stage_results(checker_results)
        session.critic_result  = run_critic(session.inputs, session.analyst_result, session.checker_result, roles_dir, token=session.token)
        session.log(f"run_analysis({tool}): {len(session.critic_result.get('findings', []))} finding(s)")
        return session.findings_summary()
    except Exception as e:
        return f"Analysis error: {e}"


def _handle_apply_fixes(args: dict, session: AgentSession) -> str:
    if not session.critic_result:
        return "Error: no analysis results — call run_analysis first."
    min_risk = args.get("min_risk", session.min_risk or "low")

    from pipeline.fixer import run_fixer
    from report.formatter import filter_by_risk

    critic_filtered = filter_by_risk(session.critic_result, min_risk)
    if not critic_filtered.get("findings") and not critic_filtered.get("recommendations"):
        return f"No findings at or above '{min_risk}' risk — nothing to fix."
    try:
        session.fixer_result = run_fixer(session.inputs, critic_filtered, session.roles_dir, min_risk, token=session.token)
    except Exception as e:
        return f"Fixer error: {e}"

    applied_literal = session.fixer_result.get("applied_literal", [])
    llm_files = session.fixer_result.get("files", [])
    skipped = session.fixer_result.get("skipped_recommendations", [])

    # Write files to disk
    from aicritic import _backup_and_apply
    try:
        backup_dir = _backup_and_apply(session.fixer_result, session.inputs)
    except Exception as e:
        return f"Error writing fixes: {e}"

    lines = [f"Applied fixes (backed up to {backup_dir}):"]
    if applied_literal:
        lines.append(f"  {len(applied_literal)} deterministic literal patch(es)")
    if llm_files:
        lines.append(f"  {len(llm_files)} LLM-rewritten file(s): {', '.join(f['path'] for f in llm_files)}")
    if skipped:
        lines.append(f"  {len(skipped)} skipped: {'; '.join(s[:80] for s in skipped)}")
    session.log(f"apply_fixes(min_risk={min_risk}): {len(applied_literal)} literal + {len(llm_files)} LLM")
    return "\n".join(lines)


def _handle_open_pr(args: dict, session: AgentSession) -> str:
    if not session.fixer_result:
        return "Error: no fixes applied — call apply_fixes first."
    import config
    from report.pr import open_pr_from_fixes, PRError
    title_override = args.get("title")
    try:
        url = open_pr_from_fixes(
            session.fixer_result,
            session.target,
            session.tool_label,
            config.GITHUB_TOKEN,
            summary=title_override or session.critic_result.get("summary", "") if session.critic_result else "",
        )
        session.pr_url = url
        session.log(f"open_pr: {url}")
        return f"Pull request opened: {url}"
    except PRError as e:
        return f"PR error: {e}"


def _handle_read_file(args: dict, session: AgentSession) -> str:
    path = args.get("path", "")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        return f"```\n{content[:8000]}\n```" + (" [truncated]" if len(content) > 8000 else "")
    except OSError as e:
        return f"Error reading {path}: {e}"


def _handle_write_file(args: dict, session: AgentSession) -> str:
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return "Error: path is required."
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        session.log(f"write_file: {path}")
        return f"Written: {path} ({len(content)} bytes)"
    except OSError as e:
        return f"Error writing {path}: {e}"


def _handle_run_shell(args: dict, session: AgentSession) -> str:
    command = args.get("command", "")
    timeout = int(args.get("timeout", 60))
    cwd = session.target if os.path.isdir(session.target) else os.path.dirname(session.target) or "."
    try:
        result = subprocess.run(
            command, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        session.last_shell_output = output
        session.last_shell_exit_code = result.returncode
        session.log(f"run_shell({command!r}): exit {result.returncode}")
        return f"Exit code: {result.returncode}\n{output[:3000]}" + (" [truncated]" if len(output) > 3000 else "")
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"Shell error: {e}"


def _handle_save_baseline(args: dict, session: AgentSession) -> str:
    if not session.critic_result:
        return "Error: no analysis results — call run_analysis first."
    path = args.get("path", ".aicritic_baseline.json")
    from report.baseline import save_baseline
    try:
        save_baseline(path, session.critic_result, session.target)
        session.log(f"save_baseline: {path}")
        return f"Baseline saved to {path}"
    except Exception as e:
        return f"Error saving baseline: {e}"


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_HANDLERS = {
    "get_changed_files": _handle_get_changed_files,
    "read_files":        _handle_read_files,
    "run_analysis":      _handle_run_analysis,
    "apply_fixes":       _handle_apply_fixes,
    "open_pr":           _handle_open_pr,
    "read_file":         _handle_read_file,
    "write_file":        _handle_write_file,
    "run_shell":         _handle_run_shell,
    "save_baseline":     _handle_save_baseline,
}


def dispatch(name: str, args: dict, session: AgentSession) -> str:
    handler = _HANDLERS.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    return handler(args, session)

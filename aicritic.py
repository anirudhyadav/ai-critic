#!/usr/bin/env python3
"""aicritic — multi-LLM code critic (Sonnet → Gemini → Opus)"""
import argparse
import os
import sys
from datetime import datetime

__version__ = "0.1.0"

_EXAMPLES = """
examples:
  aicritic "review my PR and fix high-risk issues" src/
  aicritic check src/ --tool secrets_scan
  aicritic check src/ --diff main --explain
  aicritic check src/ --fix --min-risk high
  aicritic ci src/
"""


def _backup_and_apply(fixer_result: dict, inputs: dict) -> str:
    """Write fixed files to disk; back up originals under .aicritic_backup/<timestamp>/."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(".aicritic_backup", timestamp)
    os.makedirs(backup_dir, exist_ok=True)

    original_map = {f["path"]: f["content"] for f in inputs["files"]}

    for fixed in fixer_result.get("files", []):
        path = fixed["path"]
        original = original_map.get(path)
        if original is None:
            continue

        # Backup: mirror the relative path under the backup directory
        rel = os.path.relpath(path)
        backup_path = os.path.join(backup_dir, rel)
        os.makedirs(os.path.dirname(backup_path) or backup_dir, exist_ok=True)
        with open(backup_path, "w", encoding="utf-8") as bak:
            bak.write(original)

        # Apply fix
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(fixed["content"])

    return backup_dir


def _run_agent_cmd(args) -> None:
    """Entry point for `aicritic agent <task> <target>`."""
    import config
    from agent.loop import run_agent
    from report.formatter import console
    from rich.panel import Panel
    from rich import box

    tool_label = args.tool or "security_review"
    roles_dir  = None
    if args.roles:
        roles_dir = args.roles
    elif args.tool:
        roles_dir = os.path.join(config.TOOLS_DIR, args.tool)
        if not os.path.isdir(roles_dir):
            console.print(
                f"[red]Error:[/red] unknown tool '{args.tool}'.\n"
                f"Available: {', '.join(config.TOOLS)}"
            )
            sys.exit(1)

    console.print()
    console.print(Panel(
        f"[bold cyan]aicritic agent[/bold cyan]\n[dim]{args.task}[/dim]",
        box=box.ROUNDED, expand=False,
    ))
    console.print(f"\n[bold]Target:[/bold] {args.target}  [dim]tool={tool_label}  min_risk={args.min_risk}[/dim]")
    if args.max_steps != 12:
        console.print(f"[dim]max_steps={args.max_steps}[/dim]")
    console.print("─" * 52 + "\n")

    import agent.loop as _agent_loop
    _agent_loop.MAX_STEPS = args.max_steps

    def _progress(msg: str) -> None:
        console.print(f"[dim]{msg}[/dim]")

    try:
        final_reply, session = run_agent(
            task=args.task,
            target=args.target,
            tool_label=tool_label,
            roles_dir=roles_dir,
            min_risk=args.min_risk,
            step_callback=_progress,
        )
    except RuntimeError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        sys.exit(1)

    console.print("\n" + "─" * 52)
    console.print("\n[bold cyan]aicritic[/bold cyan]\n")
    console.print(final_reply)
    console.print()


def _run_ci_cmd(args) -> None:
    """CI gate: run pipeline, apply policy, emit GitHub Actions output, exit 0/1."""
    import config
    import policy as _policy
    from inputs.loader import load_inputs
    from inputs.suppression import apply_suppressions
    from pipeline.analyst import run_analyst
    from pipeline.checker import run_checker, skipped_result as checker_skipped
    from pipeline.critic import run_critic
    from pipeline.batching import split_into_batches, merge_stage_results
    from report.formatter import filter_by_risk

    # --- Load policy --------------------------------------------------------
    pol = _policy.load(args.target)
    if getattr(args, "policy", None):
        import policy as _pol2
        pol = _pol2.load(args.policy)

    tool_label   = pol.get("tool") or "security_review"
    min_risk     = pol.get("min_risk", "low")
    skip_checker = pol.get("skip_checker", False)
    diff_only    = pol.get("diff_only", True) and not getattr(args, "no_diff", False)
    block_levels = [r.lower() for r in pol.get("block_on", ["critical", "high"])]

    # In GitHub Actions, auto-detect base branch for diff
    diff_ref = None
    if diff_only:
        base = os.environ.get("GITHUB_BASE_REF", "")
        diff_ref = f"origin/{base}" if base else None

    roles_dir = None
    if tool_label != "security_review":
        candidate = os.path.join(config.TOOLS_DIR, tool_label)
        if os.path.isdir(candidate):
            roles_dir = candidate

    if not config.GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN is not set.")
        sys.exit(1)

    print(f"aicritic ci  tool={tool_label}  block_on={block_levels}  diff={diff_ref or 'all'}")

    # --- Load files ---------------------------------------------------------
    try:
        inputs = load_inputs(args.target, diff_ref=diff_ref)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error loading files: {e}")
        sys.exit(1)

    if not inputs["files"]:
        print("No files to analyse — passing.")
        _ci_summary(passed=True, blocking=[], all_findings=[], suppressed=[],
                    block_levels=block_levels, file_count=0)
        sys.exit(0)

    print(f"Analysing {len(inputs['files'])} file(s)…")

    # --- Run pipeline -------------------------------------------------------
    batches = split_into_batches(inputs)
    analyst_results, checker_results = [], []
    for batch in batches:
        a = run_analyst(batch, roles_dir)
        c = checker_skipped("disabled via policy") if skip_checker \
            else run_checker(batch, a, roles_dir)
        analyst_results.append(a)
        checker_results.append(c)

    analyst_result = merge_stage_results(analyst_results)
    checker_result = merge_stage_results(checker_results)
    critic_result  = run_critic(inputs, analyst_result, checker_result, roles_dir)

    critic_filtered = filter_by_risk(critic_result, min_risk)

    # --- Apply suppressions -------------------------------------------------
    kept, suppressed = apply_suppressions(critic_filtered.get("findings", []), inputs)
    critic_final = {**critic_filtered, "findings": kept}

    # --- Evaluate policy ----------------------------------------------------
    blocked, blocking = _policy.check_policy(critic_final, pol)

    # --- Emit GitHub Actions annotations ------------------------------------
    _ci_annotate(kept)

    # --- Write step summary -------------------------------------------------
    _ci_summary(
        passed=not blocked,
        blocking=blocking,
        all_findings=kept,
        suppressed=suppressed,
        block_levels=block_levels,
        file_count=len(inputs["files"]),
    )

    # --- Final console output -----------------------------------------------
    if blocked:
        print(f"\n✖  BLOCKED — {len(blocking)} finding(s) at {block_levels} level require resolution.")
        for f in blocking:
            print(f"   [{f.get('risk','?').upper()}] {f.get('file','')}:{f.get('line_range','')}  {f.get('description','')}")
        print("\nTo suppress a finding add an accepted-risk comment:")
        print("  # aicritic: accepted-risk <your reason here>")
        sys.exit(1)
    else:
        total = len(kept)
        sup   = len(suppressed)
        print(f"\n✔  PASSED — no blocking findings.")
        if total:
            print(f"   {total} finding(s) below blocking threshold.")
        if sup:
            print(f"   {sup} finding(s) suppressed via accepted-risk comment.")
        sys.exit(0)


def _ci_annotate(findings: list) -> None:
    """Emit GitHub Actions workflow commands for each finding."""
    for f in findings:
        risk = f.get("risk", "low").lower()
        level = "error" if risk in ("critical", "high") else "warning"
        fname = f.get("file", "").lstrip("./")
        line_range = f.get("line_range", "1")
        line = line_range.split("-")[0].strip() or "1"
        desc = f.get("description", "").replace("\n", " ")
        print(f"::{level} file={fname},line={line},title=aicritic [{risk.upper()}]::{desc}")


def _ci_summary(
    passed: bool,
    blocking: list,
    all_findings: list,
    suppressed: list,
    block_levels: list,
    file_count: int,
) -> None:
    """Write a Markdown step summary to $GITHUB_STEP_SUMMARY if available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        return

    icon   = "✅" if passed else "❌"
    status = "PASSED" if passed else "BLOCKED"
    lines  = [
        f"## aicritic Security Gate — {icon} {status}",
        "",
        f"**Files analysed:** {file_count}  ",
        f"**Blocking levels:** `{', '.join(block_levels)}`",
        "",
    ]

    if not passed and blocking:
        lines += [
            f"### ❌ Blocking findings ({len(blocking)})",
            "",
            "| Risk | File | Lines | Description |",
            "|------|------|-------|-------------|",
        ]
        for f in blocking:
            risk = f.get("risk", "?").upper()
            lines.append(
                f"| **{risk}** | `{f.get('file','')}` "
                f"| {f.get('line_range','')} | {f.get('description','')} |"
            )
        lines.append("")

    below = [f for f in all_findings if f not in blocking]
    if below:
        lines += [
            f"### ℹ️ Below-threshold findings ({len(below)})",
            "",
            "| Risk | File | Lines | Description |",
            "|------|------|-------|-------------|",
        ]
        for f in below:
            risk = f.get("risk", "?").upper()
            lines.append(
                f"| {risk} | `{f.get('file','')}` "
                f"| {f.get('line_range','')} | {f.get('description','')} |"
            )
        lines.append("")

    if suppressed:
        lines += [
            f"### 🔕 Suppressed findings ({len(suppressed)})",
            "",
            "| Risk | File | Lines | Reason |",
            "|------|------|-------|--------|",
        ]
        for f in suppressed:
            risk = f.get("risk", "?").upper()
            reason = f.get("_suppressed_reason", "accepted-risk")
            lines.append(
                f"| {risk} | `{f.get('file','')}` "
                f"| {f.get('line_range','')} | {reason} |"
            )
        lines.append("")

    if passed:
        lines += ["_No blocking findings. Safe to merge._", ""]
    else:
        lines += [
            "**To suppress a finding**, add an accepted-risk comment on or before the flagged line:",
            "```python",
            "# aicritic: accepted-risk <your reason — reviewed by @lead on 2025-04-17>",
            "```",
            "",
        ]

    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError:
        pass


_SUBCOMMANDS = {"check", "ci", "agent", "cache-clear"}


def _rewrite_argv_for_shorthand() -> None:
    """Inject the 'agent' subcommand when the user types:

        aicritic "task description" <target> [flags]

    instead of the explicit form:

        aicritic agent "task description" <target> [flags]

    This lets @aicritic "task" target work as a shell alias.
    Mutates sys.argv in-place before argparse runs.
    """
    if len(sys.argv) < 2:
        return
    first = sys.argv[1]
    # If it looks like a natural-language task (not a known subcommand, not a flag)
    if first not in _SUBCOMMANDS and not first.startswith("-"):
        sys.argv.insert(1, "agent")


def _check_token() -> None:
    """Exit early with a helpful message if GITHUB_TOKEN is missing."""
    import config as _cfg
    if not _cfg.GITHUB_TOKEN:
        print(
            "Error: GITHUB_TOKEN is not set.\n\n"
            "aicritic needs a GitHub fine-grained PAT with Copilot Enterprise access.\n\n"
            "Quick fix:\n"
            "  1. Generate a token at: github.com → Settings → Developer settings\n"
            "                          → Personal access tokens → Fine-grained tokens\n"
            "  2. cp .env.example .env\n"
            "  3. Add:  GITHUB_TOKEN=ghp_your_token_here\n\n"
            "Or export it in your shell:\n"
            "  export GITHUB_TOKEN=ghp_your_token_here"
        )
        sys.exit(1)


def main() -> None:
    _rewrite_argv_for_shorthand()

    parser = argparse.ArgumentParser(
        prog="aicritic",
        description="Multi-LLM code critic — Sonnet → Gemini → Opus.",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version",
        version=f"aicritic {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    check_cmd = sub.add_parser("check", help="Analyse source code or coverage report")
    check_cmd.add_argument("target", help="Path to a .py file or directory")
    check_cmd.add_argument(
        "--tool",
        metavar="NAME",
        default=None,
        help=(
            "Built-in tool profile to use. "
            "Choices: migration_safety, secrets_scan, code_coverage, error_handling, "
            "pr_review, test_quality, dependency_audit, performance, "
            "dockerfile_review, iac_review. "
            "Defaults to security_review."
        ),
    )
    check_cmd.add_argument(
        "--lang",
        metavar="LANG",
        dest="languages",
        action="append",
        default=None,
        help=(
            "Restrict to this language (can repeat: --lang python --lang typescript). "
            "Supported: python, javascript, typescript, go, java, ruby, rust, csharp, "
            "php, kotlin, swift, shell, dockerfile, terraform, yaml, sql."
        ),
    )
    check_cmd.add_argument(
        "--json",
        metavar="FILE",
        default=None,
        dest="json_output",
        help="Also write findings as a JSON report to this path",
    )
    check_cmd.add_argument(
        "--html",
        metavar="FILE",
        default=None,
        dest="html_output",
        help="Also write findings as a self-contained HTML report to this path",
    )
    check_cmd.add_argument(
        "--notify-slack",
        metavar="URL",
        default=None,
        dest="notify_slack",
        help="Slack Incoming Webhook URL — posts a summary after the critic stage",
    )
    check_cmd.add_argument(
        "--notify-teams",
        metavar="URL",
        default=None,
        dest="notify_teams",
        help="Microsoft Teams webhook URL — posts a summary after the critic stage",
    )
    check_cmd.add_argument(
        "--coverage",
        metavar="FILE",
        help="Optional coverage.xml produced by `coverage xml` (used with code_coverage tool)",
    )
    check_cmd.add_argument(
        "--roles",
        metavar="DIR",
        default=None,
        help="Custom roles directory — overrides --tool and built-in profiles",
    )
    check_cmd.add_argument(
        "--min-risk",
        metavar="LEVEL",
        choices=["low", "medium", "high"],
        default=None,
        help="Only surface findings at or above this level (overrides critic.md min_risk)",
    )
    check_cmd.add_argument(
        "--skip-checker",
        action="store_true",
        default=False,
        help="Always skip Gemini — Sonnet → Opus only (fastest)",
    )
    check_cmd.add_argument(
        "--full",
        action="store_true",
        default=False,
        help="Always run Gemini even when no HIGH findings (disables adaptive skip)",
    )
    check_cmd.add_argument(
        "--parallel",
        action="store_true",
        default=False,
        help="Run Sonnet and Gemini in parallel (independent analyses) — faster than sequential",
    )
    check_cmd.add_argument(
        "--sarif",
        metavar="FILE",
        default=None,
        help="Write findings as SARIF 2.1.0 JSON for GitHub code-scanning upload",
    )
    check_cmd.add_argument(
        "--fix",
        action="store_true",
        default=False,
        help="Run the fixer stage: apply critic recommendations to source files",
    )
    check_cmd.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="With --fix: show the diff but do not write any files",
    )
    check_cmd.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="Markdown report path (default: aicritic_report.md)",
    )
    check_cmd.add_argument(
        "--diff",
        metavar="REF",
        default=None,
        help="Only analyse files changed between REF and HEAD (e.g. main, HEAD~1, origin/main)",
    )
    check_cmd.add_argument(
        "--baseline",
        metavar="FILE",
        default=None,
        help="Suppress findings present in the baseline JSON (shows only new issues)",
    )
    check_cmd.add_argument(
        "--save-baseline",
        metavar="FILE",
        default=None,
        dest="save_baseline",
        help="Save the current run's findings as a baseline JSON for future --baseline calls",
    )
    check_cmd.add_argument(
        "--pr",
        action="store_true",
        default=False,
        help="With --fix: create a branch, push, and open a PR with the applied fixes",
    )
    check_cmd.add_argument(
        "--explain",
        action="store_true",
        default=False,
        help=(
            "After the critic stage, explain WHY each finding is dangerous and "
            "show the exact fixed code for your specific file. "
            "Ideal for learning — adds ~15s."
        ),
    )

    # ------------------------------------------------------------------ agent
    agent_cmd = sub.add_parser(
        "agent",
        help="Autonomous agent — give a task in natural language, Claude does the rest",
    )
    agent_cmd.add_argument("task", help='Natural language task e.g. "review my PR and fix high-risk issues"')
    agent_cmd.add_argument("target", help="Path to a .py file or directory")
    agent_cmd.add_argument("--tool", metavar="NAME", default=None,
                           help="Default analysis tool profile (overridden by agent if task implies another)")
    agent_cmd.add_argument("--min-risk", metavar="LEVEL", choices=["low", "medium", "high"],
                           default="low", dest="min_risk")
    agent_cmd.add_argument("--roles", metavar="DIR", default=None)
    agent_cmd.add_argument("--max-steps", metavar="N", type=int, default=12,
                           dest="max_steps", help="Safety ceiling on tool-call iterations (default 12)")

    sub.add_parser(
        "cache-clear",
        help="Delete all cached pipeline results from .aicritic_cache/",
    )

    ci_cmd = sub.add_parser(
        "ci",
        help=(
            "CI gate: run analysis, apply .aicritic-policy.yaml rules, "
            "exit 1 if blocking findings exist. Designed for GitHub Actions."
        ),
    )
    ci_cmd.add_argument("target", help="Path to a file or directory to analyse")
    ci_cmd.add_argument(
        "--policy", metavar="FILE", default=None,
        help="Path to policy file (default: auto-discover .aicritic-policy.yaml)",
    )
    ci_cmd.add_argument(
        "--no-diff", action="store_true", default=False, dest="no_diff",
        help="Analyse all files, not just files changed in this PR",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        print(
            "\nGet started:\n"
            "  aicritic \"review this code for security issues\" src/\n"
            "  aicritic check src/ --tool secrets_scan\n"
            "  aicritic check src/ --diff main --explain\n"
        )
        sys.exit(0)

    # Token check — fast-fail before any work starts
    if args.command in ("check", "agent", "ci"):
        _check_token()

    if args.command == "agent":
        _run_agent_cmd(args)
        sys.exit(0)

    if args.command == "cache-clear":
        from pipeline.result_cache import clear as cache_clear
        n = cache_clear()
        print(f"Cleared {n} cached result(s) from .aicritic_cache/")
        sys.exit(0)

    if args.command == "ci":
        _run_ci_cmd(args)
        # _run_ci_cmd calls sys.exit() with the appropriate code

    if args.command != "check":
        parser.print_help()
        sys.exit(0)

    # --- apply .aicritic.yaml project defaults (CLI flags always win) ---
    import project_config as _pc
    _project_cfg = _pc.load(args.target)
    _pc.apply_to_args(args, _project_cfg)

    import config

    # Resolve roles directory
    # Priority: --roles (fully custom) > --tool (built-in profile) > roles/ (default)
    if args.roles:
        roles_dir = args.roles
    elif args.tool:
        roles_dir = os.path.join(config.TOOLS_DIR, args.tool)
        if not os.path.isdir(roles_dir):
            print(
                f"Error: unknown tool '{args.tool}'.\n"
                f"Available tools: {', '.join(config.TOOLS)}\n\n"
                f"Example: aicritic check src/ --tool secrets_scan"
            )
            sys.exit(1)
    else:
        roles_dir = None   # uses config.ROLES_DIR default

    # --- imports after arg-parse so errors surface cleanly --------------
    from inputs.loader import load_inputs
    from pipeline.analyst import run_analyst
    from pipeline.checker import run_checker, skipped_result as checker_skipped
    from pipeline.critic  import run_critic
    from pipeline.fixer   import run_fixer
    from pipeline.batching import split_into_batches, merge_stage_results
    from report.formatter import (
        console,
        print_header, print_analyst, print_checker,
        print_critic,  print_footer,  print_fixer,
        print_diff,    save_markdown,  filter_by_risk,
        save_json, save_html,
    )

    print_header(args.target)

    # Load files (+ optional coverage XML + optional diff filter + language filter)
    try:
        inputs = load_inputs(
            args.target, args.coverage,
            diff_ref=args.diff,
            languages=args.languages,
        )
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if args.diff:
        console.print(
            f"[dim]  Diff mode: {len(inputs['files'])} file(s) changed since {args.diff}[/dim]"
        )
    if args.languages:
        console.print(f"[dim]  Language filter: {', '.join(args.languages)}[/dim]")

    tool_label = args.tool or (os.path.basename(args.roles) if args.roles else "security_review")
    console.print(f"[dim]Tool: {tool_label} — {len(inputs['files'])} file(s)[/dim]\n")

    # design_review: always run explain + pre-compute complexity metrics
    is_design_review = (tool_label == "design_review")
    if is_design_review:
        args.explain = True
        from inputs.complexity import analyse_complexity, complexity_summary
        import patterns_config as _pcfg
        _complexity_report = analyse_complexity(inputs)
        _patterns_cfg = _pcfg.load(args.target)
        _complexity_text = complexity_summary(_complexity_report, _patterns_cfg)
    else:
        _complexity_text = ""
        _patterns_cfg = None

    # --parallel + --skip-checker is contradictory — parallel implies running the checker
    if args.parallel and args.skip_checker:
        console.print(
            "[yellow]Note:[/yellow] --skip-checker overrides --parallel; running Sonnet only."
        )

    # Auto-batch large codebases to stay within context window per LLM call
    batches = split_into_batches(inputs)
    if len(batches) > 1:
        console.print(
            f"[dim]  Codebase too large for a single call — splitting into "
            f"{len(batches)} batches[/dim]"
        )

    analyst_results: list = []
    checker_results: list = []

    for i, batch in enumerate(batches, 1):
        prefix = f"[dim]  [batch {i}/{len(batches)}][/dim] " if len(batches) > 1 else "[dim]  [/dim]"

        if args.parallel and not args.skip_checker:
            from concurrent.futures import ThreadPoolExecutor
            console.print(f"{prefix}Running Sonnet + Gemini in parallel…")
            try:
                with ThreadPoolExecutor(max_workers=2) as ex:
                    analyst_future = ex.submit(run_analyst, batch, roles_dir)
                    checker_future = ex.submit(
                        run_checker, batch, None, roles_dir, True   # independent=True
                    )
                    a_res = analyst_future.result()
                    c_res = checker_future.result()
            except Exception as e:
                console.print(f"[red]Analyst error:[/red] {e}")
                sys.exit(1)
        else:
            console.print(f"{prefix}Running Claude Sonnet…")
            try:
                a_res = run_analyst(batch, roles_dir)
            except Exception as e:
                console.print(f"[red]Sonnet error:[/red] {e}")
                sys.exit(1)

            if args.skip_checker:
                c_res = checker_skipped("disabled via --skip-checker")
            else:
                # Adaptive skip: Gemini adds the most value when HIGH/CRITICAL
                # findings need independent verification. For LOW/MEDIUM-only
                # results it rarely changes the verdict and costs ~60s.
                _high_found = any(
                    config.RISK_ORDER.get(f.get("risk", "low"), 0) >= config.RISK_ORDER["high"]
                    for f in a_res.get("findings", [])
                )
                if _high_found or getattr(args, "full", False):
                    console.print(f"{prefix}Running Gemini…")
                    c_res = run_checker(batch, a_res, roles_dir)
                else:
                    c_res = checker_skipped("no HIGH/CRITICAL findings — skipped for speed")
                    console.print(
                        f"{prefix}[dim]Gemini skipped — no HIGH or CRITICAL findings "
                        f"(add --full to always run it)[/dim]"
                    )

        analyst_results.append(a_res)
        checker_results.append(c_res)

    analyst_result = merge_stage_results(analyst_results)
    checker_result = merge_stage_results(checker_results)

    print_analyst(analyst_result)
    print_checker(checker_result)

    # Step 3 — Opus
    console.print("\n[dim]  Running Claude Opus…[/dim]")
    try:
        critic_result = run_critic(inputs, analyst_result, checker_result, roles_dir)
    except Exception as e:
        console.print(f"[red]Opus error:[/red] {e}")
        sys.exit(1)

    # Resolve effective min-risk: CLI flag > critic.md > "low" (show everything)
    effective_min_risk = (
        args.min_risk
        or critic_result.get("_role_config", {}).get("min_risk", "low")
    )

    analyst_filtered = filter_by_risk(analyst_result, effective_min_risk)
    checker_filtered = filter_by_risk(checker_result, effective_min_risk)
    critic_filtered  = filter_by_risk(critic_result,  effective_min_risk)

    if effective_min_risk != "low":
        console.print(
            f"[dim]  Risk filter active: showing {effective_min_risk.upper()} and above[/dim]"
        )

    # Optional: baseline filter — drop findings already present in a prior run
    if args.baseline:
        from report.baseline import load_baseline, filter_new
        try:
            baseline_fps = load_baseline(args.baseline)
            critic_filtered = filter_new(critic_filtered, baseline_fps)
            suppressed = critic_filtered.get("_baseline_suppressed", 0)
            console.print(
                f"[dim]  Baseline: {len(baseline_fps)} known finding(s), "
                f"{suppressed} suppressed, {len(critic_filtered.get('findings', []))} new[/dim]"
            )
        except (OSError, ValueError) as e:
            console.print(f"[yellow]Warning:[/yellow] could not load baseline: {e}")

    # Inline suppression — remove findings dismissed via accepted-risk comments
    from inputs.suppression import apply_suppressions
    kept_findings, suppressed_findings = apply_suppressions(
        critic_filtered.get("findings", []), inputs
    )
    if suppressed_findings:
        console.print(
            f"[dim]  {len(suppressed_findings)} finding(s) suppressed "
            f"via [italic]# aicritic: accepted-risk[/italic] comment[/dim]"
        )
    critic_display = {**critic_filtered, "findings": kept_findings,
                      "_suppressed": suppressed_findings}

    print_critic(critic_display)

    # Optional explainer — WHY each finding matters + exact fix for their code
    explainer_result = None
    if args.explain and critic_display.get("findings"):
        from pipeline.explainer import run_explainer
        from report.formatter import print_explainer
        console.print("\n[dim]  Running Explainer…[/dim]")
        explainer_result = run_explainer(inputs, critic_display)
        print_explainer(explainer_result)

    # design_review: pattern advisor runs after critic (with or without findings)
    pattern_advisor_result = None
    if is_design_review:
        from pipeline.pattern_advisor import run_pattern_advisor
        from report.formatter import print_pattern_advisor
        console.print("\n[dim]  Running Pattern Advisor…[/dim]")
        pattern_advisor_result = run_pattern_advisor(
            inputs,
            complexity_text=_complexity_text,
            patterns_config=_patterns_cfg,
        )
        print_pattern_advisor(pattern_advisor_result)

    # Save report
    report_path = save_markdown(
        args.target,
        analyst_filtered,
        checker_filtered,
        critic_display,
        args.output,
        explainer=explainer_result,
        pattern_advisor=pattern_advisor_result,
    )
    print_footer(report_path)

    # Optional: save baseline for next run
    if args.save_baseline:
        from report.baseline import save_baseline
        bpath = save_baseline(args.save_baseline, critic_result, args.target)
        console.print(f"[bold green]Baseline saved:[/bold green] {bpath}\n")

    # Optional: SARIF for GitHub code-scanning upload
    if args.sarif:
        from report.sarif import save_sarif
        sarif_path = save_sarif(critic_filtered, args.target, tool_label, args.sarif)
        console.print(f"[bold green]SARIF saved:[/bold green] {sarif_path}\n")

    # Optional: JSON report
    if args.json_output:
        jpath = save_json(args.target, analyst_filtered, checker_filtered, critic_display, args.json_output, explainer=explainer_result, pattern_advisor=pattern_advisor_result)
        console.print(f"[bold green]JSON saved:[/bold green] {jpath}\n")

    # Optional: HTML report
    if args.html_output:
        hpath = save_html(args.target, analyst_filtered, checker_filtered, critic_display, args.html_output, explainer=explainer_result, pattern_advisor=pattern_advisor_result)
        console.print(f"[bold green]HTML saved:[/bold green] {hpath}\n")

    # Optional: Slack/Teams notifications
    if args.notify_slack:
        from report.notify import notify_slack
        try:
            notify_slack(args.notify_slack, critic_filtered, args.target, tool_label, report_path)
            console.print("[bold green]Slack notification sent.[/bold green]\n")
        except RuntimeError as e:
            console.print(f"[yellow]Slack notification failed:[/yellow] {e}")

    if args.notify_teams:
        from report.notify import notify_teams
        try:
            notify_teams(args.notify_teams, critic_filtered, args.target, tool_label, report_path)
            console.print("[bold green]Teams notification sent.[/bold green]\n")
        except RuntimeError as e:
            console.print(f"[yellow]Teams notification failed:[/yellow] {e}")

    # Step 4 (optional) — Fixer
    if not args.fix:
        return

    console.print("[dim]  Running Fixer…[/dim]")
    try:
        fixer_result = run_fixer(inputs, critic_filtered, roles_dir, effective_min_risk)
    except Exception as e:
        console.print(f"[red]Fixer error:[/red] {e}")
        sys.exit(1)

    print_fixer(fixer_result)

    fixed_files = fixer_result.get("files", [])
    if not fixed_files:
        console.print("[dim]Nothing to apply.[/dim]")
        return

    # Show diffs
    original_map = {f["path"]: f["content"] for f in inputs["files"]}
    console.print("\n[bold]Proposed changes:[/bold]")
    for fixed in fixed_files:
        path = fixed["path"]
        original = original_map.get(path, "")
        print_diff(original, fixed["content"], path)

    if args.dry_run:
        console.print("\n[yellow]Dry run — no files written.[/yellow]")
        return

    # Confirm before writing
    console.print("\n[bold]Apply these changes?[/bold] [dim][y/N][/dim] ", end="")
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer == "y":
        backup_dir = _backup_and_apply(fixer_result, inputs)
        console.print(f"\n[bold green]✓ Changes applied.[/bold green]")
        console.print(f"[dim]Originals backed up to: {backup_dir}[/dim]\n")

        if args.pr:
            from report.pr import open_pr_from_fixes, PRError
            console.print("[dim]  Opening pull request…[/dim]")
            try:
                pr_url = open_pr_from_fixes(
                    fixer_result, args.target, tool_label,
                    config.GITHUB_TOKEN,
                    summary=critic_filtered.get("summary", ""),
                )
                console.print(f"[bold green]✓ Pull request opened:[/bold green] {pr_url}\n")
            except PRError as e:
                console.print(f"[yellow]Could not open PR:[/yellow] {e}")
                console.print(
                    "[dim]Fixes are applied locally — push the branch manually "
                    "if you still want a PR.[/dim]"
                )
    else:
        console.print("[dim]Changes not applied.[/dim]\n")


if __name__ == "__main__":
    main()

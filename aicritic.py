#!/usr/bin/env python3
"""
aicritic — multi-LLM critic chain

Usage:
    python aicritic.py check ./myproject
    python aicritic.py check ./myproject --tool code_coverage --coverage coverage.xml
    python aicritic.py check ./myproject --tool pr_review --min-risk medium
    python aicritic.py check ./myproject --tool secrets_scan --fix
    python aicritic.py check ./myproject --tool secrets_scan --fix --dry-run
    python aicritic.py check ./myproject --roles ./my-custom-roles

Built-in tools:
  Ship Safety    : migration_safety, secrets_scan
  Code Confidence: code_coverage, error_handling
  Review Depth   : pr_review, test_quality
  Codebase Health: dependency_audit, performance
"""
import argparse
import os
import sys
from datetime import datetime


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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aicritic",
        description="Route code through three AI models: Sonnet → Gemini → Opus.",
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
        help="Skip the Gemini cross-check stage — Sonnet → Opus only (faster, less reliable)",
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
        help="Report output path (default: aicritic_report.md)",
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

    args = parser.parse_args()

    if args.command != "check":
        parser.print_help()
        sys.exit(0)

    # --- apply .aicritic.yaml project defaults (CLI flags always win) ---
    import project_config as _pc
    _project_cfg = _pc.load(args.target)
    _pc.apply_to_args(args, _project_cfg)

    # --- guard: token present -------------------------------------------
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
                f"Available: {', '.join(config.TOOLS)}"
            )
            sys.exit(1)
    else:
        roles_dir = None   # uses config.ROLES_DIR default

    if not config.GITHUB_TOKEN:
        print(
            "Error: GITHUB_TOKEN is not set.\n"
            "Add it to a .env file or export it in your shell:\n"
            "  export GITHUB_TOKEN=ghp_..."
        )
        sys.exit(1)

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
                console.print(f"{prefix}Running Gemini…")
                c_res = run_checker(batch, a_res, roles_dir)

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

    print_critic(critic_filtered)

    # Save report
    report_path = save_markdown(
        args.target,
        analyst_filtered,
        checker_filtered,
        critic_filtered,
        args.output,
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
        jpath = save_json(args.target, analyst_filtered, checker_filtered, critic_filtered, args.json_output)
        console.print(f"[bold green]JSON saved:[/bold green] {jpath}\n")

    # Optional: HTML report
    if args.html_output:
        hpath = save_html(args.target, analyst_filtered, checker_filtered, critic_filtered, args.html_output)
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

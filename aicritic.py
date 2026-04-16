#!/usr/bin/env python3
"""
aicritic — multi-LLM critic chain

Usage:
    python aicritic.py check ./myproject
    python aicritic.py check ./myproject --tool code_coverage --coverage coverage.xml
    python aicritic.py check ./myproject --tool pr_review --min-risk medium
    python aicritic.py check ./myproject --tool security_review --fix
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
import shutil
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
            "pr_review, test_quality, dependency_audit, performance. "
            "Defaults to security_review."
        ),
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

    args = parser.parse_args()

    if args.command != "check":
        parser.print_help()
        sys.exit(0)

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
    from pipeline.checker import run_checker
    from pipeline.critic  import run_critic
    from pipeline.fixer   import run_fixer
    from report.formatter import (
        console,
        print_header, print_analyst, print_checker,
        print_critic,  print_footer,  print_fixer,
        print_diff,    save_markdown,  filter_by_risk,
    )

    print_header(args.target)

    # Load files (+ optional coverage XML)
    try:
        inputs = load_inputs(args.target, args.coverage)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    tool_label = args.tool or (os.path.basename(args.roles) if args.roles else "security_review")
    console.print(f"[dim]Tool: {tool_label} — {len(inputs['files'])} file(s)[/dim]\n")

    # Step 1 — Sonnet
    console.print("[dim]  Running Claude Sonnet…[/dim]")
    try:
        analyst_result = run_analyst(inputs, roles_dir)
    except Exception as e:
        console.print(f"[red]Sonnet error:[/red] {e}")
        sys.exit(1)
    print_analyst(analyst_result)

    # Step 2 — Gemini
    console.print("\n[dim]  Running Gemini…[/dim]")
    try:
        checker_result = run_checker(inputs, analyst_result, roles_dir)
    except Exception as e:
        console.print(f"[red]Gemini error:[/red] {e}")
        sys.exit(1)
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
    else:
        console.print("[dim]Changes not applied.[/dim]\n")


if __name__ == "__main__":
    main()

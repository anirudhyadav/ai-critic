#!/usr/bin/env python3
"""
aicritic — multi-LLM critic chain
Usage:
    python aicritic.py check ./myproject
    python aicritic.py check ./myproject --coverage coverage.xml
    python aicritic.py check ./myproject --roles ./my-roles --min-risk high
"""
import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="aicritic",
        description="Route code through three AI models: Sonnet → Gemini → Opus.",
    )
    sub = parser.add_subparsers(dest="command")

    check_cmd = sub.add_parser("check", help="Analyse source code or coverage report")
    check_cmd.add_argument("target", help="Path to a .py file or directory")
    check_cmd.add_argument(
        "--coverage",
        metavar="FILE",
        help="Optional coverage.xml produced by `coverage xml`",
    )
    check_cmd.add_argument(
        "--roles",
        metavar="DIR",
        default=None,
        help="Directory containing analyst.md / checker.md / critic.md "
             "(default: built-in roles/)",
    )
    check_cmd.add_argument(
        "--min-risk",
        metavar="LEVEL",
        choices=["low", "medium", "high"],
        default=None,
        help="Only surface findings at or above this risk level "
             "(overrides critic.md min_risk)",
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
    from report.formatter import (
        console,
        print_header, print_analyst, print_checker,
        print_critic,  print_footer,  save_markdown,
        filter_by_risk,
    )

    print_header(args.target)

    # Load files (+ optional coverage XML)
    try:
        inputs = load_inputs(args.target, args.coverage)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    mode_label = "coverage analysis" if inputs["mode"] == "coverage" else "security review"
    roles_note = f" · roles: {args.roles}" if args.roles else ""
    console.print(f"[dim]Mode: {mode_label} — {len(inputs['files'])} file(s){roles_note}[/dim]\n")

    # Step 1 — Sonnet
    console.print("[dim]  Running Claude Sonnet…[/dim]")
    try:
        analyst_result = run_analyst(inputs, args.roles)
    except Exception as e:
        console.print(f"[red]Sonnet error:[/red] {e}")
        sys.exit(1)
    print_analyst(analyst_result)

    # Step 2 — Gemini
    console.print("\n[dim]  Running Gemini…[/dim]")
    try:
        checker_result = run_checker(inputs, analyst_result, args.roles)
    except Exception as e:
        console.print(f"[red]Gemini error:[/red] {e}")
        sys.exit(1)
    print_checker(checker_result)

    # Step 3 — Opus
    console.print("\n[dim]  Running Claude Opus…[/dim]")
    try:
        critic_result = run_critic(inputs, analyst_result, checker_result, args.roles)
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


if __name__ == "__main__":
    main()

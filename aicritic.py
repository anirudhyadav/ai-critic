#!/usr/bin/env python3
"""
aicritic — multi-LLM critic chain
Usage:
    python aicritic.py check ./myproject
    python aicritic.py check ./myproject --coverage coverage.xml
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
        metavar="coverage.xml",
        help="Optional coverage.xml produced by `coverage xml`",
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
    )

    print_header(args.target)

    # Load files (+ optional coverage XML)
    try:
        inputs = load_inputs(args.target, args.coverage)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    mode_label = "coverage analysis" if inputs["mode"] == "coverage" else "security review"
    console.print(f"[dim]Mode: {mode_label} — {len(inputs['files'])} file(s)[/dim]\n")

    # Step 1 — Sonnet
    console.print("[dim]  Running Claude Sonnet…[/dim]")
    try:
        analyst_result = run_analyst(inputs)
    except Exception as e:
        console.print(f"[red]Sonnet error:[/red] {e}")
        sys.exit(1)
    print_analyst(analyst_result)

    # Step 2 — Gemini
    console.print("\n[dim]  Running Gemini…[/dim]")
    try:
        checker_result = run_checker(inputs, analyst_result)
    except Exception as e:
        console.print(f"[red]Gemini error:[/red] {e}")
        sys.exit(1)
    print_checker(checker_result)

    # Step 3 — Opus
    console.print("\n[dim]  Running Claude Opus…[/dim]")
    try:
        critic_result = run_critic(inputs, analyst_result, checker_result)
    except Exception as e:
        console.print(f"[red]Opus error:[/red] {e}")
        sys.exit(1)
    print_critic(critic_result)

    # Save report
    report_path = save_markdown(
        args.target,
        analyst_result,
        checker_result,
        critic_result,
        args.output,
    )
    print_footer(report_path)


if __name__ == "__main__":
    main()

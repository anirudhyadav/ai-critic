from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich import box

import config

console = Console()

_RISK_COLOR = {
    "high":     "bold red",
    "medium":   "yellow",
    "low":      "green",
    "critical": "bold red",
}


def _rc(risk: str) -> str:
    """Return a rich color tag for a risk level string."""
    return _RISK_COLOR.get(risk.lower(), "white")


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

def print_header(target: str) -> None:
    console.print()
    console.print(Panel(
        "[bold cyan]aicritic[/bold cyan]  —  multi-LLM critic chain",
        box=box.ROUNDED,
        expand=False,
    ))
    console.print(f"\n[bold]Analyzing:[/bold] {target}")
    console.print("─" * 52)


def print_analyst(result: dict) -> None:
    console.print("\n[bold cyan][[1/3] Claude Sonnet[/bold cyan]  [dim](primary analyst)[/dim]")
    for f in result.get("findings", []):
        risk = f.get("risk", "low")
        c = _rc(risk)
        console.print(
            f"  [{c}]● {risk.upper():<6}[/{c}]  "
            f"[dim]{f.get('file','')}:{f.get('line_range','')}[/dim]  "
            f"{f.get('description','')}"
        )
    summary = result.get("summary", "")
    if summary:
        console.print(f"  [dim italic]{summary}[/dim italic]")


def print_checker(result: dict) -> None:
    console.print("\n[bold green][[2/3] Gemini[/bold green]  [dim](cross-checker)[/dim]")
    for item in result.get("agreements", []):
        console.print(f"  [green]✓[/green] {item}")
    for item in result.get("disagreements", []):
        console.print(f"  [yellow]✗[/yellow] {item}")
    for f in result.get("findings", []):
        risk = f.get("risk", "low")
        c = _rc(risk)
        console.print(
            f"  [{c}]+ {risk.upper():<6}[/{c}]  "
            f"[dim]{f.get('file','')}:{f.get('line_range','')}[/dim]  "
            f"[italic]{f.get('description','')}[/italic]"
        )
    summary = result.get("summary", "")
    if summary:
        console.print(f"  [dim italic]{summary}[/dim italic]")


def print_critic(result: dict) -> None:
    console.print("\n[bold magenta][[3/3] Claude Opus[/bold magenta]  [dim](critic verdict)[/dim]")
    verdict = result.get("verdict", "")
    if verdict:
        console.print(f"  [bold]Verdict:[/bold] {verdict}")
    for f in result.get("findings", []):
        risk = f.get("risk", "low")
        c = _rc(risk)
        src = f"[dim]({f.get('source','')})[/dim]" if f.get("source") else ""
        console.print(
            f"  [{c}]■ {risk.upper():<6}[/{c}]  "
            f"[dim]{f.get('file','')}:{f.get('line_range','')}[/dim]  "
            f"{f.get('description','')} {src}"
        )
    recs = result.get("recommendations", [])
    if recs:
        console.print("\n  [bold]Recommendations:[/bold]")
        for r in recs:
            risk = r.get("risk_addressed", "low")
            c = _rc(risk)
            console.print(
                f"  [bold]{r.get('priority','?')}.[/bold] "
                f"[{c}][{risk.upper()}][/{c}]  {r.get('action','')}"
            )
    summary = result.get("summary", "")
    if summary:
        console.print(f"\n  [dim italic]{summary}[/dim italic]")


def print_footer(report_path: str) -> None:
    console.print()
    console.print("─" * 52)
    console.print(f"[bold green]Report saved:[/bold green] {report_path}\n")


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def save_markdown(
    target: str,
    analyst: dict,
    checker: dict,
    critic: dict,
    output_path: str = None,
) -> str:
    if output_path is None:
        output_path = config.REPORT_FILE

    lines = [
        "# aicritic Report",
        "",
        f"**Target:** `{target}`  ",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Mode:** {analyst.get('role', 'analyst')}",
        "",
        "---",
        "",
        "## [1/3] Claude Sonnet — Primary Analyst",
        "",
        f"> {analyst.get('summary', '')}",
        "",
    ]

    if analyst.get("findings"):
        lines += [
            "| File | Lines | Risk | Description |",
            "|------|-------|------|-------------|",
        ]
        for f in analyst["findings"]:
            lines.append(
                f"| `{f.get('file','')}` | {f.get('line_range','')} "
                f"| **{f.get('risk','').upper()}** | {f.get('description','')} |"
            )
        lines.append("")

    lines += [
        "## [2/3] Gemini — Cross-Checker",
        "",
        f"> {checker.get('summary', '')}",
        "",
    ]
    for item in checker.get("agreements", []):
        lines.append(f"- ✓ {item}")
    for item in checker.get("disagreements", []):
        lines.append(f"- ✗ {item}")

    if checker.get("findings"):
        lines += [
            "",
            "**Additional findings (analyst missed):**",
            "",
            "| File | Lines | Risk | Description |",
            "|------|-------|------|-------------|",
        ]
        for f in checker["findings"]:
            lines.append(
                f"| `{f.get('file','')}` | {f.get('line_range','')} "
                f"| **{f.get('risk','').upper()}** | {f.get('description','')} |"
            )
    lines.append("")

    lines += [
        "## [3/3] Claude Opus — Critic Verdict",
        "",
        f"**Overall Verdict:** {critic.get('verdict', 'N/A')}",
        "",
        f"> {critic.get('summary', '')}",
        "",
    ]

    if critic.get("findings"):
        lines += [
            "| File | Lines | Risk | Source | Description |",
            "|------|-------|------|--------|-------------|",
        ]
        for f in critic["findings"]:
            lines.append(
                f"| `{f.get('file','')}` | {f.get('line_range','')} "
                f"| **{f.get('risk','').upper()}** | {f.get('source','')} "
                f"| {f.get('description','')} |"
            )
        lines.append("")

    recs = critic.get("recommendations", [])
    if recs:
        lines += ["### Recommendations", ""]
        for r in recs:
            lines.append(
                f"{r.get('priority','?')}. "
                f"**[{r.get('risk_addressed','').upper()}]** {r.get('action','')}"
            )
        lines.append("")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    return output_path

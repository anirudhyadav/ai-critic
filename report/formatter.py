import difflib
import json
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


def filter_by_risk(result: dict, min_risk: str) -> dict:
    """
    Return a copy of result with findings filtered to >= min_risk.
    Also filters recommendations on critic output.
    Internal _role_config key is preserved unchanged.
    """
    threshold = config.RISK_ORDER.get(min_risk.lower(), 0)

    filtered = dict(result)

    if "findings" in filtered:
        filtered["findings"] = [
            f for f in filtered["findings"]
            if config.RISK_ORDER.get(f.get("risk", "low"), 0) >= threshold
        ]

    if "recommendations" in filtered:
        filtered["recommendations"] = [
            r for r in filtered["recommendations"]
            if config.RISK_ORDER.get(r.get("risk_addressed", "low"), 0) >= threshold
        ]

    return filtered


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
    if result.get("_skipped"):
        console.print(
            f"  [yellow]⚠ Checker stage unavailable[/yellow]  "
            f"[dim]({result.get('_skip_reason', 'unknown')})[/dim]"
        )
        console.print("  [dim]Findings are from Sonnet only — treat as unverified.[/dim]")
        return
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


def print_explainer(result: dict) -> None:
    explanations = result.get("explanations", [])
    if not explanations:
        return
    console.print(
        "\n[bold white on blue] EXPLAIN [/bold white on blue]  "
        "[bold]Why these matter and how to fix them[/bold]\n"
    )
    for i, e in enumerate(explanations, 1):
        risk = e.get("risk", "low")
        c = _rc(risk)
        console.print(
            f"[bold]{i}. {e.get('issue', e.get('description', 'Finding'))}[/bold]  "
            f"[{c}][{risk.upper()}][/{c}]  "
            f"[dim]{e.get('file', '')}:{e.get('line_range', '')}[/dim]"
        )
        console.print(f"\n  [yellow]⚠ Why this is dangerous[/yellow]")
        for line in e.get("why", "").splitlines():
            console.print(f"    {line}")

        vuln = e.get("vulnerable_snippet", "").strip()
        if vuln:
            console.print(f"\n  [red]✘ Vulnerable code[/red]")
            for line in vuln.splitlines():
                console.print(f"    [red]{line}[/red]")

        fixed = e.get("fixed_snippet", "").strip()
        if fixed:
            console.print(f"\n  [green]✔ How to fix it[/green]")
            for line in fixed.splitlines():
                console.print(f"    [green]{line}[/green]")

        tip = e.get("tip", "").strip()
        if tip:
            console.print(f"\n  [cyan]💡 Remember:[/cyan] {tip}")

        console.print()


def print_footer(report_path: str) -> None:
    console.print()
    console.print("─" * 52)
    console.print(f"[bold green]Report saved:[/bold green] {report_path}\n")


# ---------------------------------------------------------------------------
# Fixer output
# ---------------------------------------------------------------------------

def print_fixer(result: dict) -> None:
    console.print("\n[bold yellow][[4/4] Fixer[/bold yellow]  [dim](applying recommendations)[/dim]")
    applied_literal = result.get("applied_literal", [])
    if applied_literal:
        console.print(
            f"  [green]●[/green] [bold]{len(applied_literal)} literal patch(es)[/bold] "
            f"[dim](deterministic — no LLM rewrite)[/dim]"
        )
    files = result.get("files", [])
    if not files:
        console.print("  [dim]No changes to apply.[/dim]")
    for f in files:
        console.print(f"  [bold]{f.get('path', '')}[/bold]")
        for change in f.get("changes_applied", []):
            console.print(f"    [green]✓[/green] {change}")
    skipped = result.get("skipped_recommendations", [])
    if skipped:
        console.print("  [dim]Skipped:[/dim]")
        for s in skipped:
            console.print(f"    [dim]→ {s}[/dim]")
    summary = result.get("summary", "")
    if summary:
        console.print(f"  [dim italic]{summary}[/dim italic]")


def print_diff(original: str, fixed: str, path: str) -> None:
    """Print a colorised unified diff between original and fixed content."""
    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    ))
    if not diff:
        return
    console.print(f"\n[dim]─── {path} ───[/dim]")
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        else:
            console.print(f"[dim]{line}[/dim]")


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def save_markdown(
    target: str,
    analyst: dict,
    checker: dict,
    critic: dict,
    output_path: str = None,
    explainer: dict = None,
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
    if checker.get("_skipped"):
        lines += [
            f"> ⚠ **Checker stage unavailable** — {checker.get('_skip_reason', 'unknown')}.",
            "> Findings below are from the analyst only and have not been independently verified.",
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

    suppressed = critic.get("_suppressed", [])
    if suppressed:
        lines += ["", "---", "", "## Suppressed Findings (accepted-risk)", ""]
        lines += [
            "| Risk | File | Lines | Reason |",
            "|------|------|-------|--------|",
        ]
        for f in suppressed:
            reason = f.get("_suppressed_reason", "accepted-risk")
            lines.append(
                f"| {f.get('risk','').upper()} | `{f.get('file','')}` "
                f"| {f.get('line_range','')} | {reason} |"
            )
        lines.append("")

    if explainer and explainer.get("explanations"):
        lines += ["", "---", "", "## Understanding the Findings", ""]
        for i, e in enumerate(explainer["explanations"], 1):
            risk = e.get("risk", "low").upper()
            lines += [
                f"### {i}. {e.get('issue', 'Finding')} `[{risk}]`",
                f"**Location:** `{e.get('file', '')}` line {e.get('line_range', '')}",
                "",
                f"**Why this is dangerous**",
                f"{e.get('why', '')}",
                "",
            ]
            if e.get("vulnerable_snippet"):
                lines += [
                    "**Vulnerable code**",
                    "```",
                    e["vulnerable_snippet"].strip(),
                    "```",
                    "",
                ]
            if e.get("fixed_snippet"):
                lines += [
                    "**How to fix it**",
                    "```",
                    e["fixed_snippet"].strip(),
                    "```",
                    "",
                ]
            if e.get("tip"):
                lines += [f"> 💡 **Remember:** {e['tip']}", ""]

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def save_json(
    target: str,
    analyst: dict,
    checker: dict,
    critic: dict,
    output_path: str,
    explainer: dict = None,
) -> str:
    """Write the full run results as a single JSON document."""
    payload = {
        "meta": {
            "target": target,
            "generated": datetime.now().isoformat(timespec="seconds"),
        },
        "analyst":   {k: v for k, v in analyst.items()  if not k.startswith("_")},
        "checker":   {k: v for k, v in checker.items()  if not k.startswith("_")},
        "critic":    {k: v for k, v in critic.items()   if not k.startswith("_")},
    }
    if explainer:
        payload["explanations"] = explainer.get("explanations", [])
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

_RISK_BADGE = {
    "critical": "#c0392b",
    "high":     "#e74c3c",
    "medium":   "#e67e22",
    "low":      "#27ae60",
}


def _badge(risk: str) -> str:
    color = _RISK_BADGE.get(risk.lower(), "#888")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:.8em;font-weight:bold">'
        f'{risk.upper()}</span>'
    )


def _findings_table(findings: list, extra_col: str = None) -> str:
    if not findings:
        return "<p><em>No findings.</em></p>"
    header = "<tr><th>File</th><th>Lines</th><th>Risk</th>"
    if extra_col:
        header += f"<th>{extra_col}</th>"
    header += "<th>Description</th></tr>"
    rows = ""
    for f in findings:
        rows += (
            f"<tr>"
            f"<td><code>{f.get('file','')}</code></td>"
            f"<td>{f.get('line_range','')}</td>"
            f"<td>{_badge(f.get('risk','low'))}</td>"
        )
        if extra_col:
            rows += f"<td>{f.get(extra_col.lower(),'')}</td>"
        rows += f"<td>{f.get('description','')}</td></tr>"
    return f"<table>{header}{rows}</table>"


def _explain_html(explainer: dict | None) -> str:
    if not explainer or not explainer.get("explanations"):
        return ""
    rows = ""
    for i, e in enumerate(explainer["explanations"], 1):
        risk = e.get("risk", "low")
        vuln = e.get("vulnerable_snippet", "").strip().replace("<", "&lt;").replace(">", "&gt;")
        fixed = e.get("fixed_snippet", "").strip().replace("<", "&lt;").replace(">", "&gt;")
        rows += (
            f'<div class="explain-card">'
            f'<h3>{i}. {e.get("issue","Finding")} {_badge(risk)} '
            f'<span style="font-weight:normal;font-size:.85em">'
            f'<code>{e.get("file","")}</code> line {e.get("line_range","")}</span></h3>'
            f'<p><strong>Why this is dangerous</strong><br>{e.get("why","")}</p>'
        )
        if vuln:
            rows += f'<p><strong>✘ Vulnerable code</strong><pre class="bad">{vuln}</pre></p>'
        if fixed:
            rows += f'<p><strong>✔ How to fix it</strong><pre class="good">{fixed}</pre></p>'
        if e.get("tip"):
            rows += f'<div class="tip">💡 <strong>Remember:</strong> {e["tip"]}</div>'
        rows += "</div>"
    return (
        "<h2>Understanding the Findings</h2>"
        "<style>"
        ".explain-card{background:#f8f9fa;border-left:4px solid #3498db;"
        "padding:14px 18px;margin:16px 0;border-radius:0 6px 6px 0}"
        "pre.bad{background:#fdecea;padding:10px;border-radius:4px;overflow-x:auto}"
        "pre.good{background:#eafaf1;padding:10px;border-radius:4px;overflow-x:auto}"
        ".tip{background:#fffde7;border-left:3px solid #f9a825;"
        "padding:8px 12px;margin-top:10px;border-radius:0 4px 4px 0}"
        "</style>"
        + rows
    )


def save_html(
    target: str,
    analyst: dict,
    checker: dict,
    critic: dict,
    output_path: str,
    explainer: dict = None,
) -> str:
    """Write a self-contained HTML report with inline CSS."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    verdict = critic.get("verdict", "")
    summary = critic.get("summary", "")

    recs_html = ""
    for r in critic.get("recommendations", []):
        recs_html += (
            f"<li><strong>{r.get('priority','?')}.</strong> "
            f"{_badge(r.get('risk_addressed','low'))} "
            f"{r.get('action','')}</li>"
        )
    recs_html = f"<ol>{recs_html}</ol>" if recs_html else "<p><em>None.</em></p>"

    checker_note = ""
    if checker.get("_skipped"):
        checker_note = (
            f'<div class="warn">⚠ Checker stage unavailable — '
            f'{checker.get("_skip_reason","unknown")}. '
            f'Findings are from the analyst only.</div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>aicritic Report — {target}</title>
<style>
  body {{font-family:system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;color:#222}}
  h1 {{color:#2c3e50}} h2 {{color:#34495e;border-bottom:2px solid #ecf0f1;padding-bottom:6px}}
  table {{width:100%;border-collapse:collapse;margin:12px 0}}
  th {{background:#2c3e50;color:#fff;padding:8px 12px;text-align:left}}
  td {{padding:8px 12px;border-bottom:1px solid #ecf0f1}}
  tr:hover td {{background:#f8f9fa}}
  code {{background:#f1f1f1;padding:2px 6px;border-radius:3px;font-size:.9em}}
  .verdict {{background:#2c3e50;color:#fff;padding:12px 18px;border-radius:6px;margin:12px 0}}
  .summary {{background:#f8f9fa;border-left:4px solid #3498db;padding:10px 14px;margin:10px 0}}
  .warn {{background:#fff3cd;border-left:4px solid #ffc107;padding:10px 14px;margin:10px 0}}
  ol li {{margin:6px 0}}
  .meta {{color:#888;font-size:.9em}}
</style>
</head>
<body>
<h1>aicritic Report</h1>
<p class="meta">Target: <code>{target}</code> &nbsp;|&nbsp; Generated: {now}</p>

<div class="verdict">Overall Verdict: {verdict}</div>
<div class="summary">{summary}</div>

<h2>[1/3] Claude Sonnet — Primary Analyst</h2>
<div class="summary">{analyst.get('summary','')}</div>
{_findings_table(analyst.get('findings', []))}

<h2>[2/3] Gemini — Cross-Checker</h2>
{checker_note}
<div class="summary">{checker.get('summary','')}</div>
{_findings_table(checker.get('findings', []))}

<h2>[3/3] Claude Opus — Critic Verdict</h2>
{_findings_table(critic.get('findings', []), extra_col="Source")}

<h2>Recommendations</h2>
{recs_html}
{_explain_html(explainer)}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path

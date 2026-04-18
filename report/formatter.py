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


def print_pattern_advisor(result: dict) -> None:
    anti = result.get("anti_patterns", [])
    opps = result.get("pattern_opportunities", [])
    metrics = result.get("metrics_summary", "")
    summary = result.get("summary", "")
    error = result.get("_error")

    console.print(
        "\n[bold white on dark_green] DESIGN REVIEW [/bold white on dark_green]  "
        "[bold]Anti-patterns & Pattern Opportunities[/bold]\n"
    )

    if error:
        console.print(f"  [red]Pattern advisor error:[/red] {error}")
        return

    if metrics:
        console.print(f"  [dim]Metrics: {metrics}[/dim]\n")

    if anti:
        console.print("[bold]Anti-patterns detected:[/bold]")
        for i, ap in enumerate(anti, 1):
            sev = ap.get("severity", "low")
            c = _rc(sev)
            console.print(
                f"\n  [bold]{i}. {ap.get('name', '')}[/bold]  "
                f"[{c}][{sev.upper()}][/{c}]  "
                f"[dim]{ap.get('file', '')}:{ap.get('line_range', '')}[/dim]"
            )
            console.print(f"    {ap.get('description', '')}")
            refactored = ap.get("refactored_version", "").strip()
            if refactored:
                console.print(f"\n    [green]→ Refactored:[/green]")
                for line in refactored.splitlines():
                    console.print(f"      [green]{line}[/green]")

    if opps:
        console.print("\n[bold]Pattern opportunities:[/bold]")
        for i, op in enumerate(opps, 1):
            console.print(
                f"\n  [bold]{i}. {op.get('pattern', '')} Pattern[/bold]  "
                f"[dim]{op.get('file', '')}:{op.get('line_range', '')}[/dim]"
            )
            console.print(f"    {op.get('description', '')}")
            before = op.get("before", "").strip()
            after  = op.get("after",  "").strip()
            if before:
                console.print(f"\n    [red]✘ Before:[/red]")
                for line in before.splitlines():
                    console.print(f"      [red]{line}[/red]")
            if after:
                console.print(f"\n    [green]✔ After:[/green]")
                for line in after.splitlines():
                    console.print(f"      [green]{line}[/green]")

    if not anti and not opps:
        console.print("  [dim]No design issues found.[/dim]")

    if summary:
        console.print(f"\n  [italic]{summary}[/italic]")
    console.print()


def print_test_generator(result: dict) -> None:
    """Console output for the test generation stage."""
    from pipeline.test_generator import coverage_trend_summary

    console.print("\n[bold magenta][[T] Test Generator[/bold magenta]  [dim](coverage intelligence)[/dim]")

    # Coverage trend
    trend = coverage_trend_summary(result)
    if trend:
        color = "red bold" if result.get("policy_violation") else "green"
        console.print(f"  [{color}]{trend}[/{color}]")

    # Per-file deltas where coverage dropped
    for fname, d in result.get("per_file_delta", {}).items():
        delta = d.get("delta")
        if delta is not None and delta < -0.5:
            console.print(
                f"  [yellow]↓ {fname}[/yellow]  "
                f"{d.get('prev','?')}% → {d.get('curr','?')}%  "
                f"([red]{delta:+.1f}%[/red])"
            )

    if result.get("policy_violation"):
        floor = result.get("policy_floor", "?")
        curr  = result.get("overall_coverage", "?")
        console.print(
            f"\n  [bold red]⚠ Coverage below policy floor[/bold red]  "
            f"({curr:.1f}% < {floor}% — set in .aicritic-policy.yaml)"
        )

    # Generated tests
    tests = result.get("tests", [])
    targets = result.get("targets", [])
    if targets and not tests:
        console.print(f"  [dim]{len(targets)} high-risk uncovered path(s) found — no tests generated.[/dim]")
    elif tests:
        framework = result.get("framework", "")
        console.print(
            f"  [green]✔ {len(tests)} test(s) generated[/green]  "
            f"[dim]framework={framework}[/dim]"
        )
        for t in tests:
            console.print(
                f"    [dim]→ {t.get('test_function_name','test_?')}  "
                f"({t.get('target_file','')})  [{t.get('finding_risk','?').upper()}][/dim]"
            )
        if result.get("output_file"):
            console.print(
                f"  [bold green]Tests written to:[/bold green] {result['output_file']}"
            )
            console.print(
                "  [dim italic]Review generated tests before committing — "
                "they are NOT auto-committed.[/dim italic]"
            )

    summary = result.get("summary", "")
    if summary:
        console.print(f"\n  [italic]{summary}[/italic]")
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
    pattern_advisor: dict = None,
    test_generator: dict = None,
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

    if pattern_advisor:
        anti = pattern_advisor.get("anti_patterns", [])
        opps = pattern_advisor.get("pattern_opportunities", [])
        metrics = pattern_advisor.get("metrics_summary", "")
        pa_summary = pattern_advisor.get("summary", "")

        lines += ["", "---", "", "## Design Review", ""]
        if metrics:
            lines += [f"_{metrics}_", ""]

        if anti:
            lines += ["### Anti-patterns", ""]
            for ap in anti:
                sev = ap.get("severity", "low").upper()
                lines += [
                    f"#### {ap.get('name','')} `[{sev}]`",
                    f"**Location:** `{ap.get('file','')}` line {ap.get('line_range','')}",
                    "",
                    ap.get("description", ""),
                    "",
                ]
                if ap.get("refactored_version"):
                    lines += [
                        "**Refactored:**",
                        "```",
                        ap["refactored_version"].strip(),
                        "```",
                        "",
                    ]

        if opps:
            lines += ["### Pattern Opportunities", ""]
            for op in opps:
                lines += [
                    f"#### {op.get('pattern','')} Pattern",
                    f"**Location:** `{op.get('file','')}` line {op.get('line_range','')}",
                    "",
                    op.get("description", ""),
                    "",
                ]
                if op.get("before"):
                    lines += ["**Before:**", "```", op["before"].strip(), "```", ""]
                if op.get("after"):
                    lines += ["**After:**", "```", op["after"].strip(), "```", ""]

        if pa_summary:
            lines += [f"> {pa_summary}", ""]

    if test_generator and (test_generator.get("tests") or test_generator.get("overall_coverage") is not None):
        from pipeline.test_generator import coverage_trend_summary
        lines += ["", "---", "", "## Test Coverage Intelligence", ""]

        trend = coverage_trend_summary(test_generator)
        if trend:
            lines.append(f"**{trend}**\n")

        per_file = test_generator.get("per_file_delta", {})
        drops = [(f, d) for f, d in per_file.items() if d.get("delta") is not None and d["delta"] < -0.5]
        if drops:
            lines += ["### Coverage drops this run", "", "| File | Previous | Current | Delta |",
                      "|------|----------|---------|-------|"]
            for fname, d in drops:
                lines.append(f"| `{fname}` | {d.get('prev','?')}% | {d.get('curr','?')}% | **{d['delta']:+.1f}%** |")
            lines.append("")

        if test_generator.get("policy_violation"):
            lines.append(
                f"> ⚠ **Coverage below policy floor** "
                f"({test_generator.get('overall_coverage','?'):.1f}% < "
                f"{test_generator.get('policy_floor','?')}%)\n"
            )

        tests = test_generator.get("tests", [])
        if tests:
            framework = test_generator.get("framework", "")
            out_file = test_generator.get("output_file", "")
            lines += [f"### Generated Tests ({framework})", ""]
            if out_file:
                lines.append(f"_Written to `{out_file}` — review before committing._\n")
            for t in tests:
                lines += [
                    f"#### `{t.get('test_function_name','test_?')}`",
                    f"**Covers:** `{t.get('target_file','')}` — "
                    f"[{t.get('finding_risk','?').upper()}] {t.get('finding_description','')}",
                    "",
                    f"_{t.get('explanation','')}_",
                    "",
                    "```python",
                    t.get("test_code", "").strip(),
                    "```",
                    "",
                ]

        tg_summary = test_generator.get("summary", "")
        if tg_summary:
            lines += [f"> {tg_summary}", ""]

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
    pattern_advisor: dict = None,
    test_generator: dict = None,
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
    if pattern_advisor:
        payload["pattern_advisor"] = {k: v for k, v in pattern_advisor.items() if not k.startswith("_")}
    if test_generator:
        payload["test_generator"] = {k: v for k, v in test_generator.items() if not k.startswith("_")}
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


def _pattern_advisor_html(result: dict | None) -> str:
    if not result:
        return ""
    anti = result.get("anti_patterns", [])
    opps = result.get("pattern_opportunities", [])
    metrics = result.get("metrics_summary", "")
    summary = result.get("summary", "")
    if not anti and not opps and not metrics:
        return ""

    html = (
        "<h2>Design Review</h2>"
        "<style>"
        ".pa-card{background:#f0fdf4;border-left:4px solid #22c55e;"
        "padding:14px 18px;margin:16px 0;border-radius:0 6px 6px 0}"
        ".pa-opp{background:#fefce8;border-left:4px solid #eab308;"
        "padding:14px 18px;margin:16px 0;border-radius:0 6px 6px 0}"
        "pre.before{background:#fdecea;padding:10px;border-radius:4px;overflow-x:auto}"
        "pre.after{background:#eafaf1;padding:10px;border-radius:4px;overflow-x:auto}"
        "</style>"
    )
    if metrics:
        html += f'<p><em>{metrics}</em></p>'

    if anti:
        html += "<h3>Anti-patterns</h3>"
        for ap in anti:
            sev = ap.get("severity", "low")
            desc = ap.get("description", "").replace("<", "&lt;").replace(">", "&gt;")
            ref = ap.get("refactored_version", "").strip().replace("<", "&lt;").replace(">", "&gt;")
            html += (
                f'<div class="pa-card">'
                f'<h4>{ap.get("name","")} {_badge(sev)} '
                f'<span style="font-weight:normal;font-size:.85em">'
                f'<code>{ap.get("file","")}</code> line {ap.get("line_range","")}</span></h4>'
                f'<p>{desc}</p>'
            )
            if ref:
                html += f'<p><strong>Refactored:</strong><pre class="after">{ref}</pre></p>'
            html += "</div>"

    if opps:
        html += "<h3>Pattern Opportunities</h3>"
        for op in opps:
            desc = op.get("description", "").replace("<", "&lt;").replace(">", "&gt;")
            before = op.get("before", "").strip().replace("<", "&lt;").replace(">", "&gt;")
            after  = op.get("after",  "").strip().replace("<", "&lt;").replace(">", "&gt;")
            html += (
                f'<div class="pa-opp">'
                f'<h4>{op.get("pattern","")} Pattern '
                f'<span style="font-weight:normal;font-size:.85em">'
                f'<code>{op.get("file","")}</code> line {op.get("line_range","")}</span></h4>'
                f'<p>{desc}</p>'
            )
            if before:
                html += f'<p><strong>Before:</strong><pre class="before">{before}</pre></p>'
            if after:
                html += f'<p><strong>After:</strong><pre class="after">{after}</pre></p>'
            html += "</div>"

    if summary:
        html += f'<div class="summary">{summary}</div>'

    return html


def _test_generator_html(result: dict | None) -> str:
    if not result or (not result.get("tests") and result.get("overall_coverage") is None):
        return ""
    from pipeline.test_generator import coverage_trend_summary

    trend = coverage_trend_summary(result)
    tests = result.get("tests", [])
    per_file = result.get("per_file_delta", {})
    drops = [(f, d) for f, d in per_file.items() if d.get("delta") is not None and d["delta"] < -0.5]
    violation = result.get("policy_violation", False)

    html = (
        "<h2>Test Coverage Intelligence</h2>"
        "<style>"
        ".tg-card{background:#fdf4ff;border-left:4px solid #a855f7;"
        "padding:14px 18px;margin:16px 0;border-radius:0 6px 6px 0}"
        ".tg-warn{background:#fef3c7;border-left:4px solid #f59e0b;"
        "padding:10px 14px;margin:10px 0;border-radius:0 4px 4px 0}"
        "pre.testcode{background:#f8f9fa;padding:10px;border-radius:4px;overflow-x:auto;font-size:.85em}"
        "</style>"
    )

    if trend:
        color = "#dc2626" if violation else "#16a34a"
        html += f'<p style="font-weight:bold;color:{color}">{trend}</p>'

    if violation:
        html += (
            f'<div class="tg-warn">⚠ <strong>Coverage below policy floor</strong> — '
            f'{result.get("overall_coverage","?"):.1f}% &lt; {result.get("policy_floor","?")}% '
            f'(set in .aicritic-policy.yaml)</div>'
        )

    if drops:
        rows = "".join(
            f"<tr><td><code>{f}</code></td>"
            f"<td>{d.get('prev','?')}%</td>"
            f"<td>{d.get('curr','?')}%</td>"
            f"<td style='color:#dc2626'>{d['delta']:+.1f}%</td></tr>"
            for f, d in drops
        )
        html += (
            "<h3>Coverage drops this run</h3>"
            "<table><tr><th>File</th><th>Previous</th><th>Current</th><th>Delta</th></tr>"
            f"{rows}</table>"
        )

    if tests:
        framework = result.get("framework", "")
        out_file = result.get("output_file", "")
        html += f"<h3>Generated Tests ({framework})</h3>"
        if out_file:
            html += f'<p><em>Written to <code>{out_file}</code> — review before committing.</em></p>'
        for t in tests:
            code = t.get("test_code", "").strip().replace("<", "&lt;").replace(">", "&gt;")
            html += (
                f'<div class="tg-card">'
                f'<h4><code>{t.get("test_function_name","test_?")}</code></h4>'
                f'<p><strong>Covers:</strong> <code>{t.get("target_file","")}</code> — '
                f'{_badge(t.get("finding_risk","low"))} {t.get("finding_description","")}</p>'
                f'<p><em>{t.get("explanation","")}</em></p>'
                f'<pre class="testcode">{code}</pre>'
                f'</div>'
            )

    if result.get("summary"):
        html += f'<div class="summary">{result["summary"]}</div>'

    return html


def save_html(
    target: str,
    analyst: dict,
    checker: dict,
    critic: dict,
    output_path: str,
    explainer: dict = None,
    pattern_advisor: dict = None,
    test_generator: dict = None,
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
{_pattern_advisor_html(pattern_advisor)}
{_test_generator_html(test_generator)}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path

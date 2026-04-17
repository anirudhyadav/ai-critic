"""Webhook notifications — Slack Incoming Webhooks and Teams connectors.

Both use a simple HTTP POST with a JSON body. No SDK dependency.

Usage:
    from report.notify import notify_slack, notify_teams
    notify_slack(webhook_url, critic_result, target, tool_label)
    notify_teams(webhook_url, critic_result, target, tool_label)
"""
import json
import urllib.request
import urllib.error
from typing import Optional

_RISK_EMOJI = {
    "critical": "🔴",
    "high":     "🔴",
    "medium":   "🟡",
    "low":      "🟢",
}


def _top_findings_text(critic: dict, n: int = 5) -> list:
    findings = critic.get("findings", [])
    return [
        f"{_RISK_EMOJI.get(f.get('risk','low'), '⚪')} "
        f"*{f.get('risk','low').upper()}* — "
        f"`{f.get('file','')}:{f.get('line_range','')}` — "
        f"{f.get('description','')}"
        for f in findings[:n]
    ]


def _post(url: str, payload: dict, label: str) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "aicritic"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"{label} returned HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{label} webhook error {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {label} webhook: {e.reason}") from e


def notify_slack(
    webhook_url: str,
    critic: dict,
    target: str,
    tool_label: str,
    report_path: Optional[str] = None,
) -> None:
    """Post a summary to a Slack Incoming Webhook."""
    verdict = critic.get("verdict", "unknown")
    summary = critic.get("summary", "")
    findings = critic.get("findings", [])
    high_count = sum(1 for f in findings if f.get("risk") in ("high", "critical"))

    lines = _top_findings_text(critic)
    findings_text = "\n".join(lines) if lines else "_No findings at this risk level._"

    footer = f"Report: `{report_path}`" if report_path else ""

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"aicritic — {tool_label}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Target*\n`{target}`"},
                    {"type": "mrkdwn", "text": f"*Verdict*\n{verdict}"},
                    {"type": "mrkdwn", "text": f"*Total findings*\n{len(findings)}"},
                    {"type": "mrkdwn", "text": f"*HIGH / CRITICAL*\n{high_count}"},
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Summary*\n{summary}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Top findings*\n{findings_text}"}},
        ]
    }
    if footer:
        payload["blocks"].append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]}
        )

    _post(webhook_url, payload, "Slack")


def notify_teams(
    webhook_url: str,
    critic: dict,
    target: str,
    tool_label: str,
    report_path: Optional[str] = None,
) -> None:
    """Post a summary to a Microsoft Teams Incoming Webhook (connector card)."""
    verdict = critic.get("verdict", "unknown")
    summary = critic.get("summary", "")
    findings = critic.get("findings", [])
    high_count = sum(1 for f in findings if f.get("risk") in ("high", "critical"))

    lines = _top_findings_text(critic)
    findings_md = "\n\n".join(lines) if lines else "_No findings at this risk level._"

    facts = [
        {"name": "Target",           "value": f"`{target}`"},
        {"name": "Tool",             "value": tool_label},
        {"name": "Verdict",          "value": verdict},
        {"name": "Total findings",   "value": str(len(findings))},
        {"name": "HIGH / CRITICAL",  "value": str(high_count)},
    ]
    if report_path:
        facts.append({"name": "Report", "value": f"`{report_path}`"})

    payload = {
        "@type":      "MessageCard",
        "@context":   "https://schema.org/extensions",
        "summary":    f"aicritic — {tool_label} — {verdict}",
        "themeColor": "c0392b" if high_count else "27ae60",
        "title":      f"aicritic — {tool_label}",
        "sections": [
            {"facts": facts},
            {"text": f"**Summary:** {summary}"},
            {"text": f"**Top findings:**\n\n{findings_md}"},
        ],
    }

    _post(webhook_url, payload, "Teams")

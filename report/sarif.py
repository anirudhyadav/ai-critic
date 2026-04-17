"""
Convert aicritic critic results to SARIF 2.1.0 JSON.

SARIF (Static Analysis Results Interchange Format) is GitHub's native format
for code-scanning alerts. Uploaded SARIF files render as PR annotations and
appear in the repository's Security tab — and GitHub tracks dismissed alerts
across runs, giving the project a feedback loop for free.

Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""
import json
from datetime import datetime, timezone
from pathlib import Path

# SARIF level mapping — high/critical surface as error (red dot in PRs),
# medium as warning (yellow), low as note (blue).
_LEVEL = {
    "critical": "error",
    "high":     "error",
    "medium":   "warning",
    "low":      "note",
}

_TOOL_NAME = "aicritic"
_TOOL_URI  = "https://github.com/anirudhyadav/ai-critic"


def _parse_line_range(line_range) -> tuple:
    """Return (start_line, end_line) ints from '12-15' or '12' or int. Defaults to (1, 1)."""
    if isinstance(line_range, int):
        return (line_range, line_range)
    if not line_range:
        return (1, 1)
    s = str(line_range).strip()
    if "-" in s:
        a, _, b = s.partition("-")
        try:
            return (int(a), int(b))
        except ValueError:
            return (1, 1)
    try:
        n = int(s)
        return (n, n)
    except ValueError:
        return (1, 1)


def _rule_id(finding: dict, tool: str) -> str:
    """Stable rule id per (tool, risk). Coarse but consistent across runs."""
    risk = (finding.get("risk") or "low").lower()
    return f"aicritic.{tool}.{risk}"


def to_sarif(
    critic_output: dict,
    target: str,
    tool: str = "security_review",
) -> dict:
    """Build a SARIF 2.1.0 document from a critic result dict."""
    findings = critic_output.get("findings", [])

    # Collect unique rules referenced by the findings
    rules_by_id: dict = {}
    for f in findings:
        rid = _rule_id(f, tool)
        if rid not in rules_by_id:
            rules_by_id[rid] = {
                "id": rid,
                "name": rid.replace(".", "_"),
                "shortDescription": {
                    "text": f"{tool} ({(f.get('risk') or 'low').upper()})",
                },
                "fullDescription": {
                    "text": (
                        f"Findings produced by aicritic's {tool} tool, "
                        f"risk level {(f.get('risk') or 'low')}."
                    ),
                },
                "defaultConfiguration": {
                    "level": _LEVEL.get((f.get("risk") or "low").lower(), "note"),
                },
            }

    results = []
    for f in findings:
        start, end = _parse_line_range(f.get("line_range"))
        risk = (f.get("risk") or "low").lower()
        rid = _rule_id(f, tool)
        path = f.get("file") or "unknown"
        # SARIF requires forward-slash relative URIs
        uri = path.replace("\\", "/")

        result = {
            "ruleId": rid,
            "level": _LEVEL.get(risk, "note"),
            "message": {
                "text": f.get("description") or "(no description)",
            },
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": start, "endLine": end},
                }
            }],
        }
        if f.get("source"):
            result["properties"] = {"aicritic.source": f["source"]}
        results.append(result)

    return {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [{
            "tool": {
                "driver": {
                    "name": _TOOL_NAME,
                    "informationUri": _TOOL_URI,
                    "version": "0.1.0",
                    "rules": list(rules_by_id.values()),
                }
            },
            "invocations": [{
                "executionSuccessful": True,
                "endTimeUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "properties": {"target": target, "tool": tool},
            }],
            "results": results,
        }],
    }


def save_sarif(critic_output: dict, target: str, tool: str, output_path: str) -> str:
    doc = to_sarif(critic_output, target, tool)
    Path(output_path).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return output_path

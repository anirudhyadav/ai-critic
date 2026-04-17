"""Structured audit log for the Copilot Extension.

Each request is logged as a single JSON line so it can be ingested by any
log aggregator (Datadog, Splunk, CloudWatch, grep).

Set AICRITIC_AUDIT_LOG=/path/to/audit.jsonl to enable file logging.
Logs always go to the Python logger at INFO level regardless of the env var.

Log line shape:
{
  "ts":           "2025-04-17T12:34:56Z",
  "user":         "anirudhyadav",
  "tool":         "secrets_scan",
  "files":        3,
  "findings":     5,
  "high_count":   2,
  "agent_mode":   false,
  "duration_ms":  4200,
  "verdict":      "HIGH — 2 issues found"
}
"""
import json
import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger("aicritic.audit")
_audit_file = os.getenv("AICRITIC_AUDIT_LOG", "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False)
    logger.info(line)
    if _audit_file:
        try:
            with open(_audit_file, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def log_request(
    *,
    user: str,
    tool: str,
    files: int,
    critic_result: dict,
    agent_mode: bool = False,
    duration_ms: int = 0,
) -> None:
    """Log one completed analysis request."""
    findings = critic_result.get("findings", []) if critic_result else []
    high_count = sum(1 for f in findings if f.get("risk") in ("high", "critical"))
    _write({
        "ts":          _now_iso(),
        "user":        user,
        "tool":        tool,
        "files":       files,
        "findings":    len(findings),
        "high_count":  high_count,
        "agent_mode":  agent_mode,
        "duration_ms": duration_ms,
        "verdict":     critic_result.get("verdict", "") if critic_result else "",
    })


def log_denied(*, user: str, reason: str) -> None:
    """Log a request that was rejected (signature failure, non-member, etc.)."""
    _write({
        "ts":     _now_iso(),
        "user":   user,
        "denied": True,
        "reason": reason,
    })

"""
Format pipeline results as Server-Sent Events for the Copilot Extension.

Each public function is a sync generator that yields SSE data strings.
The server wraps these in an async generator via asyncio.to_thread /
async for.
"""
import json


# ---------------------------------------------------------------------------
# SSE primitives
# ---------------------------------------------------------------------------

def sse_start() -> str:
    """Opening frame — establishes role=assistant."""
    payload = {
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None,
        }]
    }
    return f"data: {json.dumps(payload)}\n\n"


def sse_chunk(text: str) -> str:
    payload = {
        "choices": [{
            "index": 0,
            "delta": {"content": text},
            "finish_reason": None,
        }]
    }
    return f"data: {json.dumps(payload)}\n\n"


def sse_done() -> str:
    payload = {
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop",
        }]
    }
    return f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Stage formatters
# ---------------------------------------------------------------------------

def format_analyst(result: dict):
    yield sse_chunk("### [1/3] Claude Sonnet — Primary Analysis\n\n")
    for f in result.get("findings", []):
        risk = f.get("risk", "low").upper()
        yield sse_chunk(
            f"- **{risk}** "
            f"`{f.get('file', '')}:{f.get('line_range', '')}` — "
            f"{f.get('description', '')}\n"
        )
    if result.get("summary"):
        yield sse_chunk(f"\n_{result['summary']}_\n")


def format_checker(result: dict):
    yield sse_chunk("\n### [2/3] Gemini — Cross-Check\n\n")
    if result.get("_skipped"):
        yield sse_chunk(
            f"⚠ _Checker stage unavailable_ — {result.get('_skip_reason', 'unknown')}.\n"
            f"Findings are from analyst only.\n"
        )
        return
    for item in result.get("agreements", []):
        yield sse_chunk(f"✓ {item}\n")
    for item in result.get("disagreements", []):
        yield sse_chunk(f"✗ {item}\n")
    for f in result.get("findings", []):
        risk = f.get("risk", "low").upper()
        yield sse_chunk(
            f"- **{risk}** (missed) "
            f"`{f.get('file', '')}:{f.get('line_range', '')}` — "
            f"{f.get('description', '')}\n"
        )
    if result.get("summary"):
        yield sse_chunk(f"\n_{result['summary']}_\n")


def format_critic(result: dict):
    yield sse_chunk("\n### [3/3] Claude Opus — Verdict\n\n")
    verdict = result.get("verdict", "")
    if verdict:
        yield sse_chunk(f"**{verdict}**\n\n")
    for f in result.get("findings", []):
        risk = f.get("risk", "low").upper()
        src = f" _{f.get('source', '')}_" if f.get("source") else ""
        yield sse_chunk(
            f"- **{risk}**{src} "
            f"`{f.get('file', '')}:{f.get('line_range', '')}` — "
            f"{f.get('description', '')}\n"
        )
    recs = result.get("recommendations", [])
    if recs:
        yield sse_chunk("\n**Recommendations:**\n\n")
        for r in recs:
            risk = r.get("risk_addressed", "low").upper()
            yield sse_chunk(
                f"{r.get('priority', '?')}. [{risk}] {r.get('action', '')}\n"
            )
    if result.get("summary"):
        yield sse_chunk(f"\n_{result['summary']}_\n")


def format_explainer(result: dict):
    explanations = result.get("explanations", [])
    if not explanations:
        return
    yield sse_chunk("\n### Why these matter — and how to fix them\n\n")
    for i, e in enumerate(explanations, 1):
        risk = e.get("risk", "low").upper()
        yield sse_chunk(
            f"---\n\n"
            f"**{i}. {e.get('issue', 'Finding')}** `[{risk}]` — "
            f"`{e.get('file', '')}:{e.get('line_range', '')}`\n\n"
        )
        if e.get("why"):
            yield sse_chunk(f"⚠️ **Why this is dangerous**\n{e['why']}\n\n")
        if e.get("vulnerable_snippet"):
            yield sse_chunk(
                f"✘ **Vulnerable code**\n```\n{e['vulnerable_snippet'].strip()}\n```\n\n"
            )
        if e.get("fixed_snippet"):
            yield sse_chunk(
                f"✔ **How to fix it**\n```\n{e['fixed_snippet'].strip()}\n```\n\n"
            )
        if e.get("tip"):
            yield sse_chunk(f"> 💡 **Remember:** {e['tip']}\n\n")

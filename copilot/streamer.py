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

"""
aicritic — GitHub Copilot Extension (Agent)

Run locally:
    uvicorn server:app --reload --port 8000

Expose publicly for GitHub App registration:
    ngrok http 8000   →  https://abc123.ngrok.io

Set in .env:
    GITHUB_TOKEN=...         (same token as CLI)
    AICRITIC_DEV_MODE=true   (skips signature verification during local dev)
"""
import asyncio
import json
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

import config
from copilot.auth import verify_request
from copilot.parser import parse_request
from copilot.streamer import (
    format_analyst, format_checker, format_critic,
    sse_chunk, sse_done, sse_start,
)
from report.formatter import filter_by_risk

app = FastAPI(title="aicritic", description="Multi-LLM critic chain — Copilot Extension")


# ---------------------------------------------------------------------------
# Health check — GitHub pings this on App registration
# ---------------------------------------------------------------------------

@app.get("/")
async def health():
    return {"status": "ok", "service": "aicritic"}


# ---------------------------------------------------------------------------
# Copilot Extension endpoint
# ---------------------------------------------------------------------------

@app.post("/")
async def copilot_agent(request: Request):
    body = await request.body()

    # Verify GitHub's ECDSA signature
    key_id   = request.headers.get("x-github-public-key-identifier", "")
    signature = request.headers.get("x-github-public-key-signature", "")

    if not await verify_request(body, key_id, signature):
        raise HTTPException(status_code=401, detail="Invalid request signature")

    data     = json.loads(body)
    messages = data.get("messages", [])
    parsed   = parse_request(messages)

    # No code found — ask the user to paste some
    if parsed.get("error") or not parsed.get("inputs"):
        return StreamingResponse(
            _no_code_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _pipeline_stream(parsed),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Streaming pipeline
# ---------------------------------------------------------------------------

async def _pipeline_stream(parsed: dict):
    """
    Async generator — yields SSE strings as each pipeline stage completes.
    Blocking LLM calls are dispatched to a thread so the event loop stays free.
    """
    from pipeline.analyst import run_analyst
    from pipeline.checker import run_checker
    from pipeline.critic  import run_critic

    tool      = parsed["tool"]
    inputs    = parsed["inputs"]
    roles_dir = (
        os.path.join(config.TOOLS_DIR, tool)
        if tool != "security_review" else None
    )

    yield sse_start()
    yield sse_chunk(f"**aicritic** — `{tool}`\n\n---\n\n")

    # Step 1 — Sonnet
    yield sse_chunk("_Running Claude Sonnet…_\n\n")
    analyst_result = await asyncio.to_thread(run_analyst, inputs, roles_dir)
    for chunk in format_analyst(analyst_result):
        yield chunk

    # Step 2 — Gemini
    yield sse_chunk("\n_Running Gemini…_\n\n")
    checker_result = await asyncio.to_thread(run_checker, inputs, analyst_result, roles_dir)
    for chunk in format_checker(checker_result):
        yield chunk

    # Step 3 — Opus
    yield sse_chunk("\n_Running Claude Opus…_\n\n")
    critic_result = await asyncio.to_thread(
        run_critic, inputs, analyst_result, checker_result, roles_dir
    )

    min_risk = critic_result.get("_role_config", {}).get("min_risk", "low")
    critic_filtered = filter_by_risk(critic_result, min_risk)

    for chunk in format_critic(critic_filtered):
        yield chunk

    yield sse_chunk("\n\n---\n_Analysis complete._\n")
    yield sse_done()


async def _no_code_response():
    yield sse_start()
    yield sse_chunk(
        "I couldn't find any code to analyse.\n\n"
        "Paste your code in a fenced block and try again:\n\n"
        "````\n"
        "```python\n"
        "def your_function():\n"
        "    ...\n"
        "```\n"
        "````\n\n"
        "You can also ask for a specific analysis — for example:\n"
        "- _check this for security issues_\n"
        "- _scan for hardcoded secrets_\n"
        "- _review my error handling_\n"
    )
    yield sse_done()

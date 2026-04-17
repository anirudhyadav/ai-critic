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
from copilot.auth import verify_request, verify_org_membership, extract_user_token
from copilot.audit import log_request, log_denied
from copilot.parser import parse_request
from copilot.streamer import (
    format_analyst, format_checker, format_critic,
    sse_chunk, sse_done, sse_start,
)
from report.formatter import filter_by_risk

_AGENT_TRIGGER = "@agent"   # user adds this to enable agentic mode in chat

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

    # 1 — Verify GitHub's ECDSA signature
    key_id    = request.headers.get("x-github-public-key-identifier", "")
    signature = request.headers.get("x-github-public-key-signature", "")

    if not await verify_request(body, key_id, signature):
        log_denied(user="unknown", reason="invalid_signature")
        raise HTTPException(status_code=401, detail="Invalid request signature")

    # 2 — Extract per-request user token (uses org's Copilot licence for model calls)
    user_token = extract_user_token(dict(request.headers))

    # 3 — Org membership gate
    allowed, username = await verify_org_membership(user_token)
    if not allowed:
        log_denied(user=username or "unknown", reason="not_org_member")
        raise HTTPException(status_code=403, detail="Access restricted to org members")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    messages = data.get("messages", [])
    parsed   = parse_request(messages)
    parsed["_user"]  = username
    parsed["_token"] = user_token

    # Detect agent mode: user typed "@aicritic @agent <task>" or just "@agent <task>"
    raw_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    ).lower()
    agent_mode = _AGENT_TRIGGER in raw_text

    sse_headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

    if agent_mode:
        task_text  = raw_text.split(_AGENT_TRIGGER, 1)[-1].strip() or "review the provided code"
        snippet_dir = _write_snippets(parsed.get("inputs"))
        return StreamingResponse(
            _agent_stream(task_text, snippet_dir, parsed.get("tool", "security_review"),
                          user_token, username),
            media_type="text/event-stream", headers=sse_headers,
        )

    if parsed.get("error") or not parsed.get("inputs"):
        return StreamingResponse(_no_code_response(),
                                 media_type="text/event-stream", headers=sse_headers)

    return StreamingResponse(
        _pipeline_stream(parsed, user_token, username),
        media_type="text/event-stream", headers=sse_headers,
    )


# ---------------------------------------------------------------------------
# Streaming pipeline
# ---------------------------------------------------------------------------

async def _pipeline_stream(parsed: dict, user_token: str = "", username: str = ""):
    """Async generator — yields SSE strings as each pipeline stage completes."""
    import time
    from pipeline.analyst import run_analyst
    from pipeline.checker import run_checker
    from pipeline.critic  import run_critic

    tool      = parsed["tool"]
    inputs    = parsed["inputs"]
    roles_dir = os.path.join(config.TOOLS_DIR, tool) if tool != "security_review" else None
    t_start   = time.time()

    yield sse_start()
    yield sse_chunk(f"**aicritic** — `{tool}`\n\n---\n\n")

    yield sse_chunk("_Running Claude Sonnet…_\n\n")
    analyst_result = await asyncio.to_thread(run_analyst, inputs, roles_dir, user_token)
    for chunk in format_analyst(analyst_result):
        yield chunk

    yield sse_chunk("\n_Running Gemini…_\n\n")
    checker_result = await asyncio.to_thread(
        run_checker, inputs, analyst_result, roles_dir, False, user_token
    )
    if checker_result.get("_skipped"):
        yield sse_chunk(
            f"> ⚠ **Checker stage unavailable** — {checker_result.get('_skip_reason')}.\n"
            f"> Continuing with analyst-only findings.\n\n"
        )
    for chunk in format_checker(checker_result):
        yield chunk

    yield sse_chunk("\n_Running Claude Opus…_\n\n")
    critic_result = await asyncio.to_thread(
        run_critic, inputs, analyst_result, checker_result, roles_dir, user_token
    )

    min_risk = critic_result.get("_role_config", {}).get("min_risk", "low")
    critic_filtered = filter_by_risk(critic_result, min_risk)

    for chunk in format_critic(critic_filtered):
        yield chunk

    yield sse_chunk("\n\n---\n_Analysis complete._\n")
    yield sse_done()

    log_request(
        user=username, tool=tool,
        files=len(inputs.get("files", [])),
        critic_result=critic_result,
        agent_mode=False,
        duration_ms=int((time.time() - t_start) * 1000),
    )


def _write_snippets(inputs: dict | None) -> str:
    """Write code snippets from chat to a temp directory so the agent can load them."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="aicritic_agent_")
    if inputs:
        for f in inputs.get("files", []):
            path = os.path.join(tmp, os.path.basename(f.get("path", "snippet.py")))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f.get("content", ""))
    return tmp


async def _agent_stream(
    task: str, target: str, tool_label: str,
    user_token: str = "", username: str = "",
):
    """Stream agent progress and final reply as SSE."""
    import time
    from agent.loop import stream_agent

    t_start = time.time()
    yield sse_start()
    yield sse_chunk(f"**aicritic agent** — _{task}_\n\n---\n\n")

    async for chunk in stream_agent(task, target, tool_label, token=user_token):
        yield sse_chunk(chunk)

    yield sse_chunk("\n\n---\n_Agent run complete._\n")
    yield sse_done()

    log_request(
        user=username, tool=tool_label,
        files=0,  # agent manages its own file loading
        critic_result=None,
        agent_mode=True,
        duration_ms=int((time.time() - t_start) * 1000),
    )


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

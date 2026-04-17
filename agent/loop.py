"""Agentic loop — Claude drives the pipeline via tool-use.

The loop runs until Claude stops calling tools (delivers its final answer)
or MAX_STEPS is hit. Each tool call is dispatched to agent/tools.py; the
result feeds back into the conversation.

Usage:
    from agent.loop import run_agent
    final_reply = run_agent(
        task="review my PR and fix high-risk issues",
        target="./src",
        tool_label="security_review",
        step_callback=lambda msg: print(msg),
    )

Streaming (for Copilot Extension):
    async for chunk in stream_agent(task, target, ...):
        yield sse_chunk(chunk)
"""
import json
import os
from typing import Callable, Optional, AsyncGenerator

from openai import OpenAI

import config
from agent.session import AgentSession
from agent.tools import TOOL_SCHEMAS, dispatch

MAX_STEPS = 12  # safety ceiling — prevents runaway loops

SYSTEM_PROMPT = """You are aicritic, an autonomous code-review and fix agent.

You receive a task in natural language and complete it using the tools available.
The tools map directly to aicritic's pipeline (Sonnet → Gemini → Opus) and fixer.

## Workflow rules
1. If the task is PR-scoped ("review my changes", "check what I changed"):
   call get_changed_files(ref="HEAD~1") or get_changed_files(ref="main") first.
   Otherwise call read_files() to load the full target.

2. Always call run_analysis() before apply_fixes() or open_pr().

3. Before calling apply_fixes(), summarise the findings for the user in your message.
   Let them know what you're about to change.

4. Only call open_pr() when the user's task explicitly requests a pull request.

5. After apply_fixes(), optionally call run_shell() with a linter or test command
   to verify the fixes didn't break anything — only if a test/lint command is
   obvious from context (e.g. "pytest", "ruff check .").

6. Call save_baseline() only when the task explicitly asks to set a new baseline.

7. When the task is fully done, give a concise final answer summarising:
   - What was analysed
   - What was found (counts + top issues)
   - What was fixed (if anything)
   - PR URL (if opened)
   Do NOT call any more tools after this final summary.

## Tone
Be direct and concise. No unnecessary padding. Lead with the most important finding.
"""


def _make_client(token: Optional[str] = None) -> OpenAI:
    return OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=token or config.GITHUB_TOKEN,
    )


def run_agent(
    task: str,
    target: str,
    tool_label: str = "security_review",
    roles_dir: Optional[str] = None,
    min_risk: str = "low",
    token: Optional[str] = None,
    step_callback: Optional[Callable[[str], None]] = None,
) -> tuple[str, AgentSession]:
    """Run the agent synchronously.

    Args:
        task: Natural language instruction.
        target: File or directory to operate on.
        tool_label: Default analysis tool profile.
        roles_dir: Custom roles directory (overrides tool_label).
        min_risk: Default minimum risk threshold.
        step_callback: Called with a one-line progress string after each tool call.

    Returns:
        (final_reply, session) — the agent's final message and full session state.
    """
    session = AgentSession(
        target=target,
        tool_label=tool_label,
        roles_dir=roles_dir,
        min_risk=min_risk,
        token=token,
    )
    client = _make_client(token)

    # Inject target context so Claude doesn't have to guess
    context = (
        f"Target path: `{target}`\n"
        f"Default tool: `{tool_label}`\n"
        f"Min risk filter: `{min_risk}`\n\n"
        f"Task: {task}"
    )

    session.messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": context},
    ]

    for step in range(MAX_STEPS):
        response = client.chat.completions.create(
            model=config.MODELS.get("critic", "claude-opus-4-5"),
            messages=session.messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_tokens=2048,
            temperature=0.2,
        )

        msg = response.choices[0].message

        # Append assistant message (may contain tool_calls + optional text)
        session.messages.append(msg.model_dump(exclude_none=True))

        # If Claude says something before/alongside tool calls, surface it
        if msg.content and step_callback:
            step_callback(f"\n{msg.content}\n")

        # No tool calls → final answer
        if not msg.tool_calls:
            return msg.content or "(no response)", session

        # Execute each tool call
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if step_callback:
                step_callback(f"  → {name}({_args_preview(args)})")

            result = dispatch(name, args, session)

            session.messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })

            if step_callback:
                # Show first line of result
                first_line = result.splitlines()[0] if result else ""
                step_callback(f"     {first_line}")

    return "Agent reached maximum steps without completing the task.", session


async def stream_agent(
    task: str,
    target: str,
    tool_label: str = "security_review",
    roles_dir: Optional[str] = None,
    min_risk: str = "low",
    token: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Async generator for streaming agent output (used by Copilot Extension).

    Yields text chunks as Claude reasons and tool results arrive.
    Blocking pipeline calls are run in a thread to keep the event loop free.
    """
    import asyncio

    chunks: list[str] = []
    done_event = asyncio.Event()
    final_reply_holder: list[str] = []

    def _callback(msg: str) -> None:
        chunks.append(msg)

    async def _run() -> None:
        loop = asyncio.get_event_loop()
        reply, _ = await loop.run_in_executor(
            None,
            lambda: run_agent(task, target, tool_label, roles_dir, min_risk, token, _callback),
        )
        final_reply_holder.append(reply)
        done_event.set()

    task_handle = asyncio.create_task(_run())

    while not done_event.is_set() or chunks:
        if chunks:
            yield chunks.pop(0)
        else:
            await asyncio.sleep(0.05)

    # Drain any remaining chunks
    while chunks:
        yield chunks.pop(0)

    # Final reply
    if final_reply_holder:
        yield f"\n{final_reply_holder[0]}\n"

    await task_handle


def _args_preview(args: dict) -> str:
    """Short display of tool arguments for the progress log."""
    parts = []
    for k, v in list(args.items())[:3]:
        if isinstance(v, str) and len(v) > 40:
            v = v[:40] + "…"
        parts.append(f"{k}={v!r}")
    return ", ".join(parts)

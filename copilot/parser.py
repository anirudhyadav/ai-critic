"""
Parse inbound Copilot Extension messages into a tool + inputs dict
that the pipeline can consume.
"""
import re

# Keyword → tool mapping. First match wins; order matters.
_TOOL_KEYWORDS: list[tuple[str, list[str]]] = [
    ("secrets_scan",     ["secret", "credential", "hardcoded", "api key", "token leak"]),
    ("migration_safety", ["migration", "alter table", "schema change", "db migration"]),
    ("code_coverage",    ["coverage", "untested", "test coverage", "missing test"]),
    ("error_handling",   ["error handling", "exception", "swallow", "silent fail", "bare except"]),
    ("performance",      ["performance", "slow", "n+1", "optimize", "bottleneck", "latency"]),
    ("dependency_audit", ["dependency", "dependencies", "requirements", "package", "pip", "npm"]),
    ("test_quality",     ["test quality", "flaky", "bad test", "weak assertion", "test suite"]),
    ("pr_review",        ["pull request", "pr review", "diff", "code review", "my changes"]),
]


def detect_tool(message: str) -> str:
    """Detect which aicritic tool the user is asking for."""
    msg = message.lower()
    for tool, keywords in _TOOL_KEYWORDS:
        if any(k in msg for k in keywords):
            return tool
    return "security_review"   # default


def extract_code_blocks(message: str) -> dict:
    """
    Extract fenced code blocks from a message.
    Returns {filename: content} — filenames are inferred from the language tag
    or defaulted to snippet_N.py.
    """
    pattern = r"```([a-zA-Z0-9]*)\n(.*?)```"
    matches = re.findall(pattern, message, re.DOTALL)

    files: dict = {}
    for i, (lang, code) in enumerate(matches, start=1):
        code = code.strip()
        if not code:
            continue
        ext = lang if lang else "py"
        files[f"snippet_{i}.{ext}"] = code

    return files


def parse_request(messages: list) -> dict:
    """
    Parse a Copilot conversation into {tool, inputs, error?}.

    inputs is a dict compatible with pipeline stages:
      {"files": [{path, content}], "coverage": None, "mode": "security"}
    """
    # Walk backwards to find the last user message
    user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            # content can be a string or a list of content parts
            if isinstance(content, list):
                user_content = " ".join(
                    part.get("text", "") for part in content
                    if isinstance(part, dict)
                )
            else:
                user_content = content
            break

    tool = detect_tool(user_content)
    code_files = extract_code_blocks(user_content)

    if not code_files:
        return {
            "tool": tool,
            "inputs": None,
            "error": "no_code",
        }

    from inputs.loader import from_text
    inputs = from_text(code_files)

    return {"tool": tool, "inputs": inputs}

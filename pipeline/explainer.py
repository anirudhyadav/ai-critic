"""Explainer stage — teaches WHY each finding matters and shows the exact fix.

Designed for junior developers: plain English, concrete attack scenarios,
and fixed versions of their actual code (not generic template examples).

Runs after the critic. Uses Claude Sonnet for speed.
Integrated into the cache so repeated runs on unchanged code are free.
"""
import json
from openai import OpenAI
import config
from pipeline import parse_llm_json
from pipeline.batching import build_finding_context
from pipeline.result_cache import get as cache_get, put as cache_put

_MODEL = config.MODELS.get("analyst", "claude-3-5-sonnet")

_SYSTEM_PROMPT = (
    "You are a senior developer mentoring a junior colleague.\n\n"
    "You receive a list of code findings and the relevant source code.\n"
    "For EACH finding produce four things:\n\n"
    "1. **why** — What concretely goes wrong? Describe the actual attack vector, "
    "failure mode, or production incident. Be specific: what does an attacker type? "
    "What exception fires? What data is lost?\n\n"
    "2. **vulnerable_snippet** — The exact lines from their code that are problematic. "
    "Copy verbatim — do not paraphrase.\n\n"
    "3. **fixed_snippet** — A corrected version of those exact lines. "
    "Fix THEIR specific code, not a generic example.\n\n"
    "4. **tip** — One sentence they can carry forward as a rule of thumb.\n\n"
    "Audience: someone who can write code but does not yet know security or "
    "reliability patterns. Use plain English. No unexplained jargon.\n\n"
    "Respond with ONLY a valid JSON object. No markdown fences.\n\n"
    "Schema:\n"
    "{\n"
    '  "model": "explainer",\n'
    '  "explanations": [\n'
    '    {\n'
    '      "file": "<filename>",\n'
    '      "line_range": "<line range>",\n'
    '      "risk": "<high|medium|low>",\n'
    '      "issue": "<short title, e.g. SQL Injection>",\n'
    '      "why": "<2-4 sentences — concrete scenario>",\n'
    '      "vulnerable_snippet": "<exact vulnerable lines>",\n'
    '      "fixed_snippet": "<fixed version of those lines>",\n'
    '      "tip": "<one-sentence rule to remember>"\n'
    '    }\n'
    '  ]\n'
    "}\n\n"
    "One entry per finding, same order as the input list."
)


def run_explainer(
    inputs: dict,
    critic_result: dict,
    token: str = None,
) -> dict:
    """Explain every critic finding to a junior developer.

    Returns {"model": "explainer", "explanations": [...]} with one entry per
    finding.  Never raises — returns empty explanations on any failure.
    """
    findings = critic_result.get("findings", [])
    if not findings:
        return {"model": "explainer", "explanations": []}

    clean_findings = [
        {k: v for k, v in f.items() if not k.startswith("_")}
        for f in findings
    ]
    findings_json = json.dumps(clean_findings, indent=2)
    context_text = build_finding_context(inputs, findings)

    user_message = (
        f"# Findings to Explain\n\n```json\n{findings_json}\n```\n\n"
        f"# Relevant Source Code\n\n{context_text}"
    )

    cached = cache_get("explainer", _MODEL, _SYSTEM_PROMPT, user_message)
    if cached is not None:
        cached["_from_cache"] = True
        return cached

    try:
        client = OpenAI(
            base_url=config.GITHUB_MODELS_BASE_URL,
            api_key=token or config.GITHUB_TOKEN,
        )
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=config.MAX_TOKENS,
            temperature=0.3,
        )
        result = parse_llm_json(response.choices[0].message.content)
        if "explanations" not in result:
            result["explanations"] = []
        cache_put("explainer", _MODEL, _SYSTEM_PROMPT, user_message, result)
        return result
    except Exception:
        return {"model": "explainer", "explanations": []}

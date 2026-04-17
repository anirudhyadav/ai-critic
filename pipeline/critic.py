import json
from openai import OpenAI
import config
from pipeline import parse_llm_json
from pipeline.batching import build_finding_context
from pipeline.result_cache import get as cache_get, put as cache_put


def run_critic(
    inputs: dict,
    analyst_output: dict,
    checker_output: dict,
    roles_dir: str = None,
    token: str = None,
) -> dict:
    """Step 3: Claude Opus — critic/arbiter.

    The critic no longer receives full source files. Instead it gets:
      - a compact 'relevant code' section with ±5 lines around each flagged range
      - the full analyst JSON
      - the full checker JSON (or a skipped notice)

    This cuts critic input tokens by ~40% without affecting arbitration quality —
    the critic's job is to reconcile existing findings, not discover new ones.
    """
    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=token or config.GITHUB_TOKEN,
    )

    role = config.load_role("critic", roles_dir)
    base_prompt = config.SYSTEM_PROMPTS["critic"]
    system_prompt = (
        f"{base_prompt}\n\n"
        f"## Role Instructions\n{role['instructions']}"
        if role["instructions"] else base_prompt
    )

    analyst_clean = {k: v for k, v in analyst_output.items() if not k.startswith("_")}
    checker_clean = {k: v for k, v in checker_output.items() if not k.startswith("_")}
    analyst_json  = json.dumps(analyst_clean, indent=2)
    checker_json  = json.dumps(checker_clean, indent=2)

    # Build a compact context window from only the flagged line ranges
    all_findings = (
        analyst_clean.get("findings", []) + checker_clean.get("findings", [])
    )
    context_text = build_finding_context(inputs, all_findings)

    checker_skipped = checker_output.get("_skipped")
    checker_section = (
        f"# Cross-Checker — UNAVAILABLE\n\n"
        f"The Gemini cross-check stage was not run "
        f"(reason: {checker_output.get('_skip_reason', 'unknown')}). "
        f"Treat the analyst findings as unverified and apply extra scrutiny."
        if checker_skipped
        else f"# Cross-Checker Findings (Gemini)\n\n```json\n{checker_json}\n```"
    )

    user_message = (
        f"# Relevant Code (context around flagged lines only)\n\n{context_text}\n\n"
        f"# Primary Analyst Findings (Claude Sonnet)\n\n```json\n{analyst_json}\n```\n\n"
        f"{checker_section}"
    )

    cached = cache_get("critic", role["model"], system_prompt, user_message)
    if cached is not None:
        cached["_role_config"] = role
        cached["_from_cache"] = True
        return cached

    response = client.chat.completions.create(
        model=role["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
    )

    result = parse_llm_json(response.choices[0].message.content)
    cache_put("critic", role["model"], system_prompt, user_message, result)
    result["_role_config"] = role
    return result

import json
from openai import OpenAI
import config
from pipeline import parse_llm_json


def run_critic(
    inputs: dict,
    analyst_output: dict,
    checker_output: dict,
    roles_dir: str = None,
) -> dict:
    """Step 3: Claude Opus — critic/arbiter, receives all prior context."""
    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=config.GITHUB_TOKEN,
    )

    role = config.load_role("critic", roles_dir)
    base_prompt = config.SYSTEM_PROMPTS["critic"]
    system_prompt = (
        f"{base_prompt}\n\n"
        f"## Role Instructions\n{role['instructions']}"
        if role["instructions"] else base_prompt
    )

    source_parts = [
        f"## File: {f['path']}\n\n```python\n{f['content']}\n```"
        for f in inputs["files"]
    ]
    source_text  = "\n\n".join(source_parts)

    analyst_clean = {k: v for k, v in analyst_output.items() if not k.startswith("_")}
    checker_clean = {k: v for k, v in checker_output.items() if not k.startswith("_")}
    analyst_json  = json.dumps(analyst_clean, indent=2)
    checker_json  = json.dumps(checker_clean, indent=2)

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
        f"# Source Code\n\n{source_text}\n\n"
        f"# Primary Analyst Findings (Claude Sonnet)\n\n```json\n{analyst_json}\n```\n\n"
        f"{checker_section}"
    )

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
    result["_role_config"] = role
    return result

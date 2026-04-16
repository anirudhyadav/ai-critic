import json
from openai import OpenAI
import config
from pipeline import parse_llm_json


def run_checker(inputs: dict, analyst_output: dict, roles_dir: str = None) -> dict:
    """Step 2: Gemini — cross-checker, receives source + Sonnet's findings."""
    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=config.GITHUB_TOKEN,
    )

    role = config.load_role("checker", roles_dir)
    base_prompt = config.SYSTEM_PROMPTS["checker"]
    system_prompt = (
        f"{base_prompt}\n\n"
        f"## Role Instructions\n{role['instructions']}"
        if role["instructions"] else base_prompt
    )

    source_parts = [
        f"## File: {f['path']}\n\n```python\n{f['content']}\n```"
        for f in inputs["files"]
    ]
    source_text = "\n\n".join(source_parts)

    # Strip internal config key before passing to next model
    analyst_clean = {k: v for k, v in analyst_output.items() if not k.startswith("_")}
    analyst_json  = json.dumps(analyst_clean, indent=2)

    user_message = (
        f"# Source Code\n\n{source_text}\n\n"
        f"# Primary Analyst Findings\n\n```json\n{analyst_json}\n```"
    )

    response = client.chat.completions.create(
        model=config.MODELS["checker"],
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

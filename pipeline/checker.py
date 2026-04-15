import json
from openai import OpenAI
import config
from pipeline import parse_llm_json


def run_checker(inputs: dict, analyst_output: dict) -> dict:
    """Step 2: Gemini — cross-checker, receives source + Sonnet's findings."""
    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=config.GITHUB_TOKEN,
    )

    source_parts = [
        f"## File: {f['path']}\n\n```python\n{f['content']}\n```"
        for f in inputs["files"]
    ]
    source_text = "\n\n".join(source_parts)
    analyst_json = json.dumps(analyst_output, indent=2)

    user_message = (
        f"# Source Code\n\n{source_text}\n\n"
        f"# Primary Analyst Findings\n\n```json\n{analyst_json}\n```"
    )

    response = client.chat.completions.create(
        model=config.MODELS["checker"],
        messages=[
            {"role": "system", "content": config.SYSTEM_PROMPTS["checker"]},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
    )

    return parse_llm_json(response.choices[0].message.content)

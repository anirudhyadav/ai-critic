from openai import OpenAI
import config
from pipeline import parse_llm_json


def _build_user_message(inputs: dict) -> str:
    parts = []
    for f in inputs["files"]:
        parts.append(f"## File: {f['path']}\n\n```python\n{f['content']}\n```")

    if inputs.get("coverage"):
        cov_lines = ["## Coverage Data\n"]
        for fname, data in inputs["coverage"].items():
            rate = data["line_rate"] * 100
            missing = data["missing_lines"]
            missing_str = ", ".join(str(n) for n in missing) if missing else "none"
            cov_lines.append(
                f"- **{fname}**: {rate:.0f}% line coverage — "
                f"missing lines: {missing_str}"
            )
        parts.append("\n".join(cov_lines))

    return "\n\n".join(parts)


def run_analyst(inputs: dict) -> dict:
    """Step 1: Claude Sonnet — primary analyst."""
    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=config.GITHUB_TOKEN,
    )

    system_prompt = config.SYSTEM_PROMPTS[f"analyst_{inputs['mode']}"]
    user_message = _build_user_message(inputs)

    response = client.chat.completions.create(
        model=config.MODELS["analyst"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=config.MAX_TOKENS,
        temperature=config.TEMPERATURE,
    )

    return parse_llm_json(response.choices[0].message.content)

from openai import OpenAI
import config
from pipeline import parse_llm_json


def _build_user_message(inputs: dict) -> str:
    parts = []
    for f in inputs["files"]:
        lang = f.get("language", "python")
        parts.append(f"## File: {f['path']}\n\n```{lang}\n{f['content']}\n```")

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


def run_analyst(inputs: dict, roles_dir: str = None, token: str = None) -> dict:
    """Step 1: Claude Sonnet — primary analyst."""
    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=token or config.GITHUB_TOKEN,
    )

    role = config.load_role("analyst", roles_dir)

    # role["mode"] wins (set by tool profile); fall back to inputs["mode"] (security/coverage)
    prompt_key = f"analyst_{role['mode'] or inputs['mode']}"
    base_prompt = config.SYSTEM_PROMPTS.get(
        prompt_key,
        config.SYSTEM_PROMPTS["analyst_security"],   # last-resort fallback
    )
    system_prompt = (
        f"{base_prompt}\n\n"
        f"## Role Instructions\n{role['instructions']}"
        if role["instructions"] else base_prompt
    )

    user_message = _build_user_message(inputs)

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


    role = config.load_role("analyst", roles_dir)

    # role["mode"] wins (set by tool profile); fall back to inputs["mode"] (security/coverage)
    prompt_key = f"analyst_{role['mode'] or inputs['mode']}"
    base_prompt = config.SYSTEM_PROMPTS.get(
        prompt_key,
        config.SYSTEM_PROMPTS["analyst_security"],   # last-resort fallback
    )
    system_prompt = (
        f"{base_prompt}\n\n"
        f"## Role Instructions\n{role['instructions']}"
        if role["instructions"] else base_prompt
    )

    user_message = _build_user_message(inputs)

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
    result["_role_config"] = role   # carry config forward for downstream filtering
    return result

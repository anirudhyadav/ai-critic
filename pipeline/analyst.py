from openai import OpenAI, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
import config
from pipeline import parse_llm_json
from pipeline.result_cache import get as cache_get, put as cache_put


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
    role = config.load_role("analyst", roles_dir)

    prompt_key = f"analyst_{role['mode'] or inputs['mode']}"
    base_prompt = config.SYSTEM_PROMPTS.get(
        prompt_key,
        config.SYSTEM_PROMPTS["analyst_security"],
    )
    system_prompt = (
        f"{base_prompt}\n\n"
        f"## Role Instructions\n{role['instructions']}"
        if role["instructions"] else base_prompt
    )

    user_message = _build_user_message(inputs)

    cached = cache_get("analyst", role["model"], system_prompt, user_message)
    if cached is not None:
        cached["_role_config"] = role
        cached["_from_cache"] = True
        return cached

    try:
        client = OpenAI(
            base_url=config.GITHUB_MODELS_BASE_URL,
            api_key=token or config.GITHUB_TOKEN,
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
    except AuthenticationError:
        raise RuntimeError(
            "GITHUB_TOKEN is invalid or expired.\n"
            "Regenerate it at: github.com → Settings → Developer settings → Personal access tokens"
        )
    except RateLimitError:
        raise RuntimeError(
            "GitHub Models API rate limit reached.\n"
            "Wait a minute and try again, or add --skip-checker to reduce API calls."
        )
    except APIConnectionError:
        raise RuntimeError(
            "Could not connect to the GitHub Models API.\n"
            "Check your internet connection and try again."
        )
    except APIStatusError as e:
        raise RuntimeError(
            f"GitHub Models API returned an error ({e.status_code}).\n"
            f"Details: {e.message}"
        )

    result = parse_llm_json(response.choices[0].message.content)
    cache_put("analyst", role["model"], system_prompt, user_message, result)
    result["_role_config"] = role
    return result

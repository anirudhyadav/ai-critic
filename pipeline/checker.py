import json
from openai import OpenAI
import config
from pipeline import parse_llm_json


def skipped_result(reason: str, role: dict = None) -> dict:
    """Return a synthetic checker result that downstream stages can consume safely."""
    return {
        "model": "checker",
        "role": "checker",
        "agreements": [],
        "disagreements": [],
        "findings": [],
        "summary": f"Checker stage skipped: {reason}",
        "_skipped": True,
        "_skip_reason": reason,
        "_role_config": role or config.load_role("checker"),
    }


def run_checker(inputs: dict, analyst_output: dict, roles_dir: str = None) -> dict:
    """Step 2: Gemini — cross-checker, receives source + Sonnet's findings.

    Never raises. If the model call fails or the response can't be parsed,
    returns a skipped_result so the pipeline can continue with analyst-only data.
    """
    role = config.load_role("checker", roles_dir)

    try:
        client = OpenAI(
            base_url=config.GITHUB_MODELS_BASE_URL,
            api_key=config.GITHUB_TOKEN,
        )

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

        analyst_clean = {k: v for k, v in analyst_output.items() if not k.startswith("_")}
        analyst_json  = json.dumps(analyst_clean, indent=2)

        user_message = (
            f"# Source Code\n\n{source_text}\n\n"
            f"# Primary Analyst Findings\n\n```json\n{analyst_json}\n```"
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
    except Exception as e:
        return skipped_result(f"{type(e).__name__}: {e}", role)

    result["_role_config"] = role
    return result

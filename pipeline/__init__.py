import json
import re


def parse_llm_json(text: str) -> dict:
    """
    Extract and parse JSON from an LLM response.
    Handles: raw JSON, ```json ... ``` fences, or a bare {...} block.
    """
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from model response:\n{text[:400]}")

import json
from openai import OpenAI
import config
from pipeline import parse_llm_json


def run_fixer(
    inputs: dict,
    critic_output: dict,
    roles_dir: str = None,
    min_risk: str = None,
) -> dict:
    """
    Step 4 (optional): Apply critic recommendations to source files.

    Filters recommendations by min_risk, sends source + recommendations to
    the fixer model, and returns fixed file content ready to write to disk.
    """
    threshold = config.RISK_ORDER.get((min_risk or "low").lower(), 0)
    recommendations = [
        r for r in critic_output.get("recommendations", [])
        if config.RISK_ORDER.get(r.get("risk_addressed", "low"), 0) >= threshold
    ]

    if not recommendations:
        return {
            "model": "fixer",
            "role": "fixer",
            "files": [],
            "skipped_recommendations": [],
            "summary": "No recommendations met the risk threshold — nothing to fix.",
        }

    role = config.load_role("fixer", roles_dir)
    system_prompt = config.SYSTEM_PROMPTS["fixer"]
    if role["instructions"]:
        system_prompt += f"\n\n## Additional Instructions\n{role['instructions']}"

    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=config.GITHUB_TOKEN,
    )

    # Source files section
    source_parts = [
        f"## File: {f['path']}\n\n```\n{f['content']}\n```"
        for f in inputs["files"]
    ]
    source_text = "\n\n".join(source_parts)

    # Recommendations section (numbered, with priority and risk)
    rec_lines = ["## Recommendations to Apply\n"]
    for r in recommendations:
        rec_lines.append(
            f"{r.get('priority', '?')}. "
            f"[{r.get('risk_addressed', '').upper()}] {r.get('action', '')}"
        )

    # Findings context — gives the fixer precise file/line references
    findings = [
        f for f in critic_output.get("findings", [])
        if config.RISK_ORDER.get(f.get("risk", "low"), 0) >= threshold
    ]
    if findings:
        rec_lines.append("\n## Finding Locations (file and line references)\n")
        for f in findings:
            rec_lines.append(
                f"- `{f.get('file', '')}` lines {f.get('line_range', '?')}: "
                f"{f.get('description', '')}"
            )

    user_message = f"# Source Files\n\n{source_text}\n\n" + "\n".join(rec_lines)

    response = client.chat.completions.create(
        model=role["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        max_tokens=config.FIXER_MAX_TOKENS,
        temperature=config.FIXER_TEMPERATURE,
    )

    return parse_llm_json(response.choices[0].message.content)

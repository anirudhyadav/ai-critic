import json
from openai import OpenAI
import config
from pipeline import parse_llm_json


def _meets_threshold(item: dict, key: str, threshold: int) -> bool:
    return config.RISK_ORDER.get(item.get(key, "low"), 0) >= threshold


def _apply_literal_patches(
    inputs: dict,
    recommendations: list,
) -> tuple:
    """
    Apply find/replace recommendations directly without calling an LLM.

    Returns (patched_files_by_path, applied_recs, deferred_recs, skipped_recs).
    A literal patch is applied only when:
      - both `find` and `replace` are present
      - `confidence` is 'high'
      - `find` appears EXACTLY ONCE in the target file (no ambiguity)
    """
    files_by_path = {f["path"]: f["content"] for f in inputs["files"]}
    patched: dict = {}
    applied: list = []
    deferred: list = []   # ambiguous / non-literal — fall through to LLM
    skipped: list = []    # literal patches that failed safety checks

    for rec in recommendations:
        find = rec.get("find")
        replace = rec.get("replace")
        target_path = rec.get("file")
        confidence = (rec.get("confidence") or "").lower()

        if not (find and replace is not None and target_path):
            deferred.append(rec)
            continue

        if confidence != "high":
            deferred.append(rec)
            continue

        if target_path not in files_by_path:
            skipped.append({
                "rec": rec,
                "reason": f"file '{target_path}' not in source set",
            })
            continue

        # Use the latest patched version if we've already touched this file
        current = patched.get(target_path, files_by_path[target_path])
        occurrences = current.count(find)

        if occurrences == 0:
            skipped.append({
                "rec": rec,
                "reason": f"`find` text not present in {target_path}",
            })
            continue
        if occurrences > 1:
            skipped.append({
                "rec": rec,
                "reason": f"`find` text appears {occurrences} times in {target_path} (ambiguous)",
            })
            continue

        patched[target_path] = current.replace(find, replace, 1)
        applied.append({
            "path": target_path,
            "action": rec.get("action", ""),
            "risk_addressed": rec.get("risk_addressed", ""),
        })

    return patched, applied, deferred, skipped


def _format_skipped(skipped: list) -> list:
    return [
        f"{s['rec'].get('action', '<no action>')} — skipped: {s['reason']}"
        for s in skipped
    ]


def _llm_rewrite(
    inputs: dict,
    recommendations: list,
    findings: list,
    role: dict,
    pre_patched_files: dict,
    token: str = None,
) -> dict:
    """Fall back to LLM-based rewrite for recommendations without literal patches."""
    if not recommendations:
        return {"files": [], "skipped_recommendations": [], "summary": ""}

    system_prompt = config.SYSTEM_PROMPTS["fixer"]
    if role["instructions"]:
        system_prompt += f"\n\n## Additional Instructions\n{role['instructions']}"

    client = OpenAI(
        base_url=config.GITHUB_MODELS_BASE_URL,
        api_key=token or config.GITHUB_TOKEN,
    )

    # Use already-patched content if available — chain literal patches into the LLM context
    source_parts = []
    for f in inputs["files"]:
        content = pre_patched_files.get(f["path"], f["content"])
        source_parts.append(f"## File: {f['path']}\n\n```\n{content}\n```")
    source_text = "\n\n".join(source_parts)

    rec_lines = ["## Recommendations to Apply\n"]
    for r in recommendations:
        rec_lines.append(
            f"{r.get('priority', '?')}. "
            f"[{r.get('risk_addressed', '').upper()}] {r.get('action', '')}"
        )

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


def run_fixer(
    inputs: dict,
    critic_output: dict,
    roles_dir: str = None,
    min_risk: str = None,
    token: str = None,
) -> dict:
    """
    Step 4 (optional): Apply critic recommendations to source files.

    Two-phase strategy:
      1. Deterministic literal patches for high-confidence find/replace recommendations
      2. LLM rewrite for everything else (ambiguous or architectural)

    The deterministic phase is the trustworthy path — no LLM error compounding.
    """
    threshold = config.RISK_ORDER.get((min_risk or "low").lower(), 0)
    recommendations = [
        r for r in critic_output.get("recommendations", [])
        if _meets_threshold(r, "risk_addressed", threshold)
    ]

    if not recommendations:
        return {
            "model": "fixer",
            "role": "fixer",
            "files": [],
            "skipped_recommendations": [],
            "applied_literal": [],
            "summary": "No recommendations met the risk threshold — nothing to fix.",
        }

    role = config.load_role("fixer", roles_dir)
    original_by_path = {f["path"]: f["content"] for f in inputs["files"]}

    # Phase 1 — deterministic literal patches
    patched, applied, deferred, skipped = _apply_literal_patches(inputs, recommendations)

    # Phase 2 — LLM rewrite for the leftovers
    findings = [
        f for f in critic_output.get("findings", [])
        if _meets_threshold(f, "risk", threshold)
    ]
    llm_result = _llm_rewrite(inputs, deferred, findings, role, patched, token=token)

    # Merge: LLM-rewritten files override literal-patched ones for the same path
    final_files: dict = {}
    for path, content in patched.items():
        final_files[path] = {
            "path": path,
            "content": content,
            "changes_applied": [
                a["action"] for a in applied if a["path"] == path
            ] or ["literal patch applied"],
        }
    for f in llm_result.get("files", []):
        path = f.get("path")
        if not path:
            continue
        existing = final_files.get(path, {})
        final_files[path] = {
            "path": path,
            "content": f.get("content", existing.get("content", original_by_path.get(path, ""))),
            "changes_applied": (
                existing.get("changes_applied", []) + f.get("changes_applied", [])
            ),
        }

    skipped_messages = _format_skipped(skipped) + llm_result.get("skipped_recommendations", [])

    summary_bits = []
    if applied:
        summary_bits.append(f"{len(applied)} literal patch(es)")
    if llm_result.get("files"):
        summary_bits.append(f"{len(llm_result['files'])} LLM rewrite(s)")
    if not summary_bits:
        summary_bits.append("no changes")
    summary = (
        f"Fixer applied {' + '.join(summary_bits)}. "
        + (llm_result.get("summary") or "")
    ).strip()

    return {
        "model": "fixer",
        "role": "fixer",
        "files": list(final_files.values()),
        "skipped_recommendations": skipped_messages,
        "applied_literal": applied,
        "summary": summary,
    }

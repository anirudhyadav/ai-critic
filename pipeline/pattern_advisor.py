"""Pattern Advisor stage — detects anti-patterns and suggests design patterns.

Runs after the critic stage when --tool design_review is active.
Uses Claude Sonnet (fast, cost-effective) with complexity metrics pre-computed
by inputs/complexity.py injected into the prompt for grounded analysis.

Output schema:
{
  "model": "pattern_advisor",
  "anti_patterns": [
    {
      "name": "God Class",
      "file": "models.py",
      "line_range": "1-450",
      "description": "UserManager has 42 methods spanning auth, billing, and notifications",
      "severity": "high|medium|low",
      "refactored_version": "Split into AuthService, BillingService, NotificationService ..."
    }
  ],
  "pattern_opportunities": [
    {
      "pattern": "Strategy",
      "file": "processor.py",
      "line_range": "12-80",
      "description": "PaymentProcessor uses if/elif chains for each payment type",
      "before": "if self.type == 'stripe': ... elif self.type == 'paypal': ...",
      "after": "class StripeStrategy(PaymentStrategy): ..."
    }
  ],
  "metrics_summary": "2 functions exceed cyclomatic threshold, 1 God class detected",
  "summary": "3 high-severity anti-patterns found. Priority: extract God class first."
}
"""
import json
from openai import OpenAI

import config
from pipeline import parse_llm_json
from pipeline.batching import build_finding_context
from pipeline.result_cache import get as cache_get, put as cache_put

_MODEL = config.MODELS.get("analyst", "claude-3-5-sonnet")

_SYSTEM_PROMPT = """\
You are a senior software architect and design pattern advisor.

You receive:
1. Source code files
2. Static complexity metrics (cyclomatic complexity, class sizes, coupling)
3. Team conventions (if a .aicritic-patterns.yaml was found)

Your job is to identify:

## Anti-patterns to detect

- **God Class**: A class with too many responsibilities (methods, lines, or domains)
- **Feature Envy**: A method that uses more data from another class than its own
- **Long Method**: A function too long to understand at a glance
- **Magic Numbers**: Unnamed numeric/string literals that should be named constants
- **Deep Nesting**: Conditional nesting > 4 levels that should be flattened
- **Primitive Obsession**: Using primitives (str, int, dict) where a small class would clarify intent
- **Shotgun Surgery**: A single change requiring edits in many unrelated places

For each anti-pattern include:
- The exact file and line range
- Specific description using the actual class/method/variable names from the code
- A refactored version showing the structural change (use the developer's actual names)

## Pattern opportunities to suggest

Only suggest a pattern if the code would genuinely benefit. Use the developer's
exact class and method names in before/after — never write generic examples.

Applicable patterns:
- **Strategy**: if/elif chains switching behavior on a type or flag
- **Factory**: direct instantiation with isinstance/type checks scattered around
- **Observer**: event callbacks mixed into business logic or long notify() methods
- **Repository**: raw DB/API calls scattered across service/controller classes
- **Decorator**: cross-cutting concerns (logging, auth, retry) copy-pasted around methods
- **Command**: operations that need undo, queuing, or audit trails

## Complexity metrics

Flag any function/class that exceeds the thresholds provided in the metrics data.
Report the actual value vs the threshold.

## Output rules

- Use the developer's EXACT class names, method names, and variable names.
  Never write generic examples like `MyClass` or `doSomething`.
- Only report genuine issues — do not invent problems.
- `refactored_version` and `after` should be concise structural sketches,
  not complete implementations. Show the shape of the change, not every line.
- Order anti_patterns by severity (high first).

Respond with ONLY a valid JSON object. No markdown fences, no explanation outside the JSON.

Schema:
{
  "model": "pattern_advisor",
  "anti_patterns": [
    {
      "name": "<God Class|Feature Envy|Long Method|Magic Numbers|Deep Nesting|Primitive Obsession|Shotgun Surgery>",
      "file": "<filename>",
      "line_range": "<start>-<end>",
      "description": "<specific description using the actual names from the code>",
      "severity": "<high|medium|low>",
      "refactored_version": "<structural sketch using the actual names>"
    }
  ],
  "pattern_opportunities": [
    {
      "pattern": "<Strategy|Factory|Observer|Repository|Decorator|Command>",
      "file": "<filename>",
      "line_range": "<start>-<end>",
      "description": "<why this code would benefit from this pattern>",
      "before": "<concise before snippet using actual names>",
      "after": "<concise after snippet using actual names>"
    }
  ],
  "metrics_summary": "<1-2 sentence summary of metric violations>",
  "summary": "<2-3 sentence overall assessment and recommended priority>"
}

Return empty arrays if no issues found. Always include metrics_summary and summary.
"""


def run_pattern_advisor(
    inputs: dict,
    complexity_text: str = "",
    patterns_config: dict | None = None,
    token: str = None,
) -> dict:
    """Analyse source for design anti-patterns and pattern opportunities.

    Args:
        inputs: loader inputs dict (files list)
        complexity_text: pre-rendered complexity summary from inputs/complexity.py
        patterns_config: team conventions dict from patterns_config.py
        token: optional per-request Copilot bearer token

    Returns pattern advisor result dict. Never raises.
    """
    files = inputs.get("files", [])
    if not files:
        return _empty()

    # Build source context (reuse the finding-context builder for consistency)
    source_parts = []
    for f in files:
        path = f.get("path", "")
        content = f.get("content", "").strip()
        if content:
            source_parts.append(f"### {path}\n```\n{content}\n```")
    source_text = "\n\n".join(source_parts)

    # Build conventions section
    conventions_text = ""
    if patterns_config:
        lines = ["## Team Conventions (.aicritic-patterns.yaml)"]
        thresholds = [
            ("max_method_lines",           "Max method lines",           patterns_config.get("max_method_lines")),
            ("max_cyclomatic_complexity",  "Max cyclomatic complexity",   patterns_config.get("max_cyclomatic_complexity")),
            ("max_class_lines",            "Max class lines",             patterns_config.get("max_class_lines")),
            ("max_nesting_depth",          "Max nesting depth",           patterns_config.get("max_nesting_depth")),
        ]
        for _, label, val in thresholds:
            if val is not None:
                lines.append(f"- {label}: {val}")
        approved = patterns_config.get("approved_patterns", [])
        if approved:
            lines.append(f"- Approved patterns: {', '.join(approved)}")
        avoid = patterns_config.get("avoid_patterns", [])
        if avoid:
            lines.append(f"- Patterns to avoid: {', '.join(avoid)}")
        prefer_comp = patterns_config.get("prefer_composition")
        if prefer_comp is not None:
            lines.append(f"- Prefer composition over inheritance: {prefer_comp}")
        use_repo = patterns_config.get("use_repository")
        if use_repo is not None:
            lines.append(f"- Use Repository pattern for DB access: {use_repo}")
        conventions_text = "\n".join(lines)

    user_message = (
        "# Source Files\n\n"
        + source_text
        + ("\n\n" + complexity_text if complexity_text else "")
        + ("\n\n" + conventions_text if conventions_text else "")
    )

    # Truncate to avoid token limits (pattern advisor is context-heavy)
    if len(user_message) > 60000:
        user_message = user_message[:60000] + "\n\n[... truncated for length ...]"

    cached = cache_get("pattern_advisor", _MODEL, _SYSTEM_PROMPT, user_message)
    if cached is not None:
        cached["_from_cache"] = True
        return cached

    try:
        client = OpenAI(
            base_url=config.GITHUB_MODELS_BASE_URL,
            api_key=token or config.GITHUB_TOKEN,
        )
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=config.MAX_TOKENS,
            temperature=0.2,
        )
        result = parse_llm_json(response.choices[0].message.content)
        _normalise(result)
        cache_put("pattern_advisor", _MODEL, _SYSTEM_PROMPT, user_message, result)
        return result
    except Exception as exc:
        return _empty(error=str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty(error: str = "") -> dict:
    base = {
        "model": "pattern_advisor",
        "anti_patterns": [],
        "pattern_opportunities": [],
        "metrics_summary": "",
        "summary": "",
    }
    if error:
        base["_error"] = error
    return base


def _normalise(result: dict) -> None:
    result.setdefault("model", "pattern_advisor")
    result.setdefault("anti_patterns", [])
    result.setdefault("pattern_opportunities", [])
    result.setdefault("metrics_summary", "")
    result.setdefault("summary", "")

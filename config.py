import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"

# Model names on GitHub Models API — update here if the catalog changes
MODELS = {
    "analyst": "claude-3-5-sonnet",
    "checker": "gemini-1.5-pro",
    "critic":  "claude-opus-4-5",
    "fixer":   "claude-3-5-sonnet",
}

MAX_TOKENS       = 4096
FIXER_MAX_TOKENS = 8192   # fixer returns full file content — needs more room
TEMPERATURE      = 0.2
FIXER_TEMPERATURE = 0.1   # lower = more precise code changes
REPORT_FILE = "aicritic_report.md"

# Default roles directory — used when no --tool or --roles flag is passed
ROLES_DIR = os.path.join(os.path.dirname(__file__), "roles")

# Built-in tool profiles live here; --tool <name> resolves to tools/<name>/
TOOLS_DIR = os.path.join(os.path.dirname(__file__), "tools")

# Risk level ordering for threshold filtering
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Available built-in tools
TOOLS = [
    # Ship Safety
    "migration_safety",
    "secrets_scan",
    # Code Confidence
    "code_coverage",
    "error_handling",
    # Review Depth
    "pr_review",
    "test_quality",
    # Codebase Health
    "dependency_audit",
    "performance",
    # Infrastructure
    "dockerfile_review",
    "iac_review",
]


def load_role(name: str, roles_dir: str = None) -> dict:
    """
    Parse a role markdown file and return its configuration.

    Returns:
        {
            "mode":         str,   # system prompt key suffix e.g. "security", "pr_review"
            "focus":        str,   # human label e.g. "security"
            "strictness":   str,   # "low" | "medium" | "high"
            "min_risk":     str,   # "low" | "medium" | "high"
            "model":        str,   # LLM to use — falls back to MODELS[name] if unset
            "instructions": str,   # freeform markdown body injected into the prompt
        }
    """
    path = os.path.join(roles_dir or ROLES_DIR, f"{name}.md")

    defaults = {
        "mode":         "security",
        "focus":        "security",
        "strictness":   "medium",
        "min_risk":     "low",
        "model":        MODELS.get(name, ""),
        "instructions": "",
    }

    if not os.path.exists(path):
        return defaults

    with open(path, encoding="utf-8") as fh:
        content = fh.read()

    meta: dict = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2].strip()

    return {
        "mode":         meta.get("mode",        defaults["mode"]),
        "focus":        meta.get("focus",        defaults["focus"]),
        "strictness":   meta.get("strictness",   defaults["strictness"]),
        "min_risk":     meta.get("min_risk",     defaults["min_risk"]),
        "model":        meta.get("model",        defaults["model"]),
        "instructions": body,
    }


# ---------------------------------------------------------------------------
# Shared JSON schema fragments
# ---------------------------------------------------------------------------

_JSON_NOTE = (
    "Respond with ONLY a valid JSON object. "
    "No markdown fences, no explanation outside the JSON."
)

_FINDING_SCHEMA = (
    '  "findings": [\n'
    '    {\n'
    '      "file": "<filename>",\n'
    '      "line_range": "<start>-<end or line number>",\n'
    '      "description": "<clear description of the issue>",\n'
    '      "risk": "<high|medium|low>"\n'
    '    }\n'
    '  ],\n'
    '  "summary": "<1-2 sentence overall summary>"\n'
)

_CHECKER_SCHEMA = (
    '  "agreements": ["<what you confirm from the analyst>"],\n'
    '  "disagreements": ["<what you challenge, with reasoning>"],\n'
    '  "findings": [\n'
    '    {\n'
    '      "file": "<filename>",\n'
    '      "line_range": "<start>-<end>",\n'
    '      "description": "<issue the analyst missed>",\n'
    '      "risk": "<high|medium|low>"\n'
    '    }\n'
    '  ],\n'
    '  "summary": "<1-2 sentence cross-check summary>"\n'
)

_CRITIC_SCHEMA = (
    '  "verdict": "<CRITICAL|HIGH|MEDIUM|LOW> — one-line overall verdict",\n'
    '  "findings": [\n'
    '    {\n'
    '      "file": "<filename>",\n'
    '      "line_range": "<start>-<end>",\n'
    '      "description": "<consolidated description>",\n'
    '      "risk": "<high|medium|low>",\n'
    '      "source": "<analyst|checker|both>"\n'
    '    }\n'
    '  ],\n'
    '  "agreements": ["<where both models agreed>"],\n'
    '  "disagreements": ["<how you resolved model conflicts>"],\n'
    '  "recommendations": [\n'
    '    {\n'
    '      "priority": 1,\n'
    '      "action": "<specific remediation step>",\n'
    '      "risk_addressed": "<high|medium|low>",\n'
    '      "file": "<filename — required if a literal fix is provided>",\n'
    '      "find": "<exact source string to replace — OPTIONAL, omit if ambiguous>",\n'
    '      "replace": "<replacement string — OPTIONAL, paired with find>",\n'
    '      "confidence": "<high|medium|low — confidence the literal fix is safe>"\n'
    '    }\n'
    '  ],\n'
    '  "summary": "<2-3 sentence final verdict>"\n'
)


def _analyst_prompt(description: str) -> str:
    return (
        f"{description}\n\n"
        + _JSON_NOTE + "\n\n"
        "Use exactly this schema:\n"
        "{\n"
        '  "model": "analyst",\n'
        '  "role": "analyst",\n'
        + _FINDING_SCHEMA +
        "}\n\n"
        "Be precise about line numbers. Return an empty findings array if nothing found."
    )


# ---------------------------------------------------------------------------
# System prompts — analyst has one per tool mode; checker/critic are generic
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS = {

    # ------------------------------------------------------------------
    # SHIP SAFETY
    # ------------------------------------------------------------------

    "analyst_migration_safety": _analyst_prompt(
        "You are a database migration safety analyst. "
        "Review the provided SQL migration files or ORM migration code for risks that "
        "could cause data loss, extended downtime, lock contention, or failed rollbacks "
        "in a production environment."
    ),

    "analyst_secrets_scan": _analyst_prompt(
        "You are a secrets and credential scanner. "
        "Review the provided source code for hardcoded credentials, API keys, tokens, "
        "private keys, connection strings, and any other sensitive values that should "
        "not be committed to source control."
    ),

    # ------------------------------------------------------------------
    # CODE CONFIDENCE
    # ------------------------------------------------------------------

    "analyst_coverage": _analyst_prompt(
        "You are a code coverage analyst. "
        "Review the provided Python source code and coverage data to identify "
        "untested paths, missing branch coverage, and risky uncovered logic."
    ),

    "analyst_error_handling": _analyst_prompt(
        "You are an error handling analyst. "
        "Review the provided source code for swallowed exceptions, missing error handling, "
        "bare except clauses, missing timeouts, silent failures, and error paths that "
        "could corrupt state or leave the system in an undefined condition."
    ),

    # ------------------------------------------------------------------
    # REVIEW DEPTH
    # ------------------------------------------------------------------

    "analyst_pr_review": _analyst_prompt(
        "You are a pull request reviewer. "
        "Review the provided code changes (diff or modified files) for correctness, "
        "regressions, logic errors, missing test coverage for new code, and any "
        "security issues introduced by the changes."
    ),

    "analyst_test_quality": _analyst_prompt(
        "You are a test quality analyst. "
        "Review the provided test files and assess whether the tests are meaningful. "
        "Identify: assertions that always pass, missing edge cases, tests that only "
        "check happy paths, brittle tests tied to implementation details, and "
        "scenarios that are completely absent."
    ),

    # ------------------------------------------------------------------
    # CODEBASE HEALTH
    # ------------------------------------------------------------------

    "analyst_dependency_audit": _analyst_prompt(
        "You are a dependency auditor. "
        "Review the provided dependency files (requirements.txt, package.json, pyproject.toml, etc.) "
        "for outdated packages, known vulnerable versions, unnecessary bloat, "
        "licence conflicts, and packages that introduce excessive transitive dependencies."
    ),

    "analyst_performance": _analyst_prompt(
        "You are a performance analyst. "
        "Review the provided source code for performance bottlenecks: N+1 database queries, "
        "unnecessary loops inside loops, blocking I/O on the main thread, missing caching, "
        "inefficient data structures, and memory allocation patterns that could cause "
        "pressure under load."
    ),

    # ------------------------------------------------------------------
    # INFRASTRUCTURE
    # ------------------------------------------------------------------

    "analyst_dockerfile_review": _analyst_prompt(
        "You are a Dockerfile security and best-practices analyst. "
        "Review the provided Dockerfile(s) for security vulnerabilities, bloat, "
        "and deviations from container hardening best practices."
    ),

    "analyst_iac_review": _analyst_prompt(
        "You are an Infrastructure-as-Code security analyst. "
        "Review the provided Terraform, CloudFormation, Kubernetes YAML, or Pulumi "
        "files for misconfigurations, overly permissive access controls, missing "
        "encryption, exposed secrets, and reliability issues."
    ),

    # ------------------------------------------------------------------
    # FALLBACK — generic security (used by default roles/ profile)
    # ------------------------------------------------------------------

    "analyst_security": _analyst_prompt(
        "You are a security-focused code analyst. "
        "Review the provided source code for security vulnerabilities, "
        "risky patterns, and exploitable logic."
    ),

    # ------------------------------------------------------------------
    # Checker — generic, works across all tools
    # ------------------------------------------------------------------

    "checker": (
        "You are a cross-checking analyst. "
        "You will receive source code and a primary analyst's findings.\n\n"
        "Your job:\n"
        "- Verify each finding (agree or disagree, with brief reasoning)\n"
        "- Identify anything the analyst missed\n"
        "- Note if any risk levels should be adjusted\n\n"
        + _JSON_NOTE + "\n\n"
        "Use exactly this schema:\n"
        "{\n"
        '  "model": "checker",\n'
        '  "role": "checker",\n'
        + _CHECKER_SCHEMA +
        "}\n\n"
        "Only include in findings what the original analyst MISSED."
    ),

    # ------------------------------------------------------------------
    # Critic — generic, works across all tools
    # ------------------------------------------------------------------

    "critic": (
        "You are a senior critic and arbiter. "
        "You receive source code, a primary analyst's findings, and a cross-checker's findings. "
        "Synthesise both perspectives, resolve disagreements, assign final risk levels, "
        "and produce a prioritised action plan.\n\n"
        + _JSON_NOTE + "\n\n"
        "Use exactly this schema:\n"
        "{\n"
        '  "model": "critic",\n'
        '  "role": "critic",\n'
        + _CRITIC_SCHEMA +
        "}\n\n"
        "Be decisive. Resolve all disagreements. Order recommendations by urgency.\n\n"
        "## Literal fixes (find/replace)\n"
        "When a recommendation is a small, mechanical change you are highly confident about "
        "(e.g. replacing a hardcoded value with os.environ.get, narrowing 'except Exception' "
        "to a specific type, adding a missing timeout argument), include `file`, `find`, and "
        "`replace` so a deterministic patch can be applied without an LLM rewrite. "
        "`find` MUST appear verbatim exactly once in the named file. "
        "Set `confidence` to 'high' for these. Omit find/replace for ambiguous, multi-location, "
        "or architectural changes — those should be described in `action` only."
    ),

    # ------------------------------------------------------------------
    # Fixer — applies critic recommendations to source files
    # ------------------------------------------------------------------

    "fixer": (
        "You are a precise code fixer. "
        "You receive source files and a prioritised list of recommendations from a code critic. "
        "Apply ONLY the listed recommendations — do not refactor, rename, or improve anything "
        "beyond what is explicitly requested.\n\n"
        + _JSON_NOTE + "\n\n"
        "Use exactly this schema:\n"
        "{\n"
        '  "model": "fixer",\n'
        '  "role": "fixer",\n'
        '  "files": [\n'
        '    {\n'
        '      "path": "<exact file path as provided>",\n'
        '      "content": "<complete fixed file content — the ENTIRE file, not just changed lines>",\n'
        '      "changes_applied": ["<what was changed and why>"]\n'
        '    }\n'
        '  ],\n'
        '  "skipped_recommendations": [\n'
        '    "<recommendation text> — skipped: <one-line reason>"\n'
        '  ],\n'
        '  "summary": "<1-2 sentence summary of what was fixed>"\n'
        "}\n\n"
        "Rules:\n"
        "1. Only include files that were actually modified.\n"
        "2. Return the COMPLETE file content for every modified file — not a diff, not a snippet.\n"
        "3. If a fix requires a new import, add it.\n"
        "4. If a recommendation is ambiguous or unsafe to apply without more context, "
        "add it to skipped_recommendations with a reason.\n"
        "5. Preserve all existing comments, formatting, and unrelated code exactly as-is.\n"
        "6. Do not add docstrings, type hints, or any improvements beyond the specific fix."
    ),
}

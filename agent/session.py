"""In-memory state carried across tool calls in a single agent run."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentSession:
    # Set at start of run
    target: str
    tool_label: str = "security_review"
    roles_dir: Optional[str] = None
    min_risk: str = "low"

    # Populated as tools execute
    inputs: Optional[dict] = None          # loader output
    analyst_result: Optional[dict] = None
    checker_result: Optional[dict] = None
    critic_result: Optional[dict] = None
    fixer_result: Optional[dict] = None
    pr_url: Optional[str] = None

    # Shell command results (last run)
    last_shell_output: str = ""
    last_shell_exit_code: int = 0

    # Conversation history for the LLM
    messages: list = field(default_factory=list)

    # Running log shown to the user
    step_log: list = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.step_log.append(msg)

    def findings_summary(self) -> str:
        """Compact critic findings summary Claude can reason about."""
        if not self.critic_result:
            return "No analysis run yet."
        findings = self.critic_result.get("findings", [])
        if not findings:
            return "No findings."
        lines = [f"Verdict: {self.critic_result.get('verdict', 'N/A')}"]
        for f in findings:
            lines.append(
                f"  [{f.get('risk','?').upper()}] {f.get('file','')}:"
                f"{f.get('line_range','')} — {f.get('description','')}"
            )
        lines.append(f"Summary: {self.critic_result.get('summary','')}")
        return "\n".join(lines)

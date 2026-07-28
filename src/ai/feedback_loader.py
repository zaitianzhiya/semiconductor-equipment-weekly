"""Feedback loader — read reader corrections from feedback/*.md files."""

from pathlib import Path


class FeedbackLoader:
    """Parse feedback files and extract confirmed rules for AI prompt injection."""

    def __init__(self, feedback_dir: str = None):
        self.feedback_dir = Path(feedback_dir) if feedback_dir else Path("feedback")
        self.feedback_dir.mkdir(parents=True, exist_ok=True)

    def get_rules_for_prompt(self, max_weeks: int = 4) -> str:
        """Build a prompt section from recent confirmed feedback."""
        files = sorted(self.feedback_dir.glob("*.md"), reverse=True)
        if not files:
            return ""

        rules: list[str] = []
        for f in files[:max_weeks]:
            week = f.stem
            try:
                content = f.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("- [x]"):
                        rules.append(stripped)
            except OSError:
                continue

        if not rules:
            return ""

        return (
            "## 反馈修正（来自上期读者）\n"
            + "\n".join(rules)
            + "\n"
        )

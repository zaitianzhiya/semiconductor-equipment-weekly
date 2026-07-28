"""AI deep analyzer — generate weekly deep analysis using LLM."""

from pathlib import Path

from src.ai.llm_client import LLMClient
from src.collectors.base import EventRecord


class DeepAnalyzer:
    """Generate structured deep analysis for top-ranked events."""

    def __init__(self, llm_client: LLMClient, prompts_dir: Path = None):
        self.client = llm_client
        self.prompts_dir = prompts_dir or Path("prompts")
        self.system_prompt = self._load_prompt("weekly-deep.md")
        self.taxonomy = self._load_prompt("taxonomy.md")
        self.feedback_rules = self._load_prompt("feedback-rules.md")

    def _load_prompt(self, filename: str) -> str:
        path = self.prompts_dir / filename
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def analyze(self, records: list[EventRecord], top_n: int = 15) -> str:
        """Generate a deep analysis report for the top N events."""
        if not records:
            return "*(本周无足够事件进行深度分析)*"

        top = records[:top_n]
        data_text = self._format_events_for_llm(top, records)

        try:
            result = self.client.chat(self.system_prompt, data_text, temperature=0.7)
            return result
        except Exception as e:
            print(f"[AI] Deep analysis skipped (LLM unavailable): {e}")
            return self._fallback_output(top)

    def _format_events_for_llm(
        self, top: list[EventRecord], all_records: list[EventRecord]
    ) -> str:
        """Build the user message containing all event data for the LLM."""
        lines = [
            "## 本周评分规则",
            "",
            self.taxonomy or "(见 taxonomy.md)",
            "",
            self.feedback_rules or "",
            "",
            "---",
            "",
            f"## 本周 TOP {len(top)} 事件（按影响力排序）",
            "",
        ]

        for i, r in enumerate(top, 1):
            cats = ", ".join(r.categories) if r.categories else "未分类"
            sources = ", ".join(
                f"{c.source_name}(T{c.tier})" for c in r.citations
            )
            lines.extend([
                f"### {i}. {r.title}",
                "",
                f"- **组织**: {r.organization}",
                f"- **链接**: {r.url}" if r.url else f"- **组织**: {r.organization}",
                f"- **可信度**: {r.confidence_grade} ({r.confidence_score:.0f}/100)",
                f"- **分类**: {cats}",
                f"- **来源**: {sources}",
                f"- **独立生态数**: {r.independent_ecosystems}",
                "",
                r.description if r.description else "(无详细描述)",
                "",
            ])

        grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
        for r in all_records:
            grade_dist[r.confidence_grade] = grade_dist.get(r.confidence_grade, 0) + 1

        lines.extend([
            "---",
            "",
            "## 统计信息",
            "",
            f"- 本周总采集: {len(all_records)}",
            f"- A级: {grade_dist['A']} | B级: {grade_dist['B']} | C级: {grade_dist['C']} | D级: {grade_dist['D']}",
            "",
        ])

        return "\n".join(lines)

    def _fallback_output(self, top: list[EventRecord]) -> str:
        lines = [
            "## 本周事件数据（AI 摘要暂时不可用）",
            "",
            "| # | 事件 | 组织 | 可信度 | 分类 |",
            "|---|------|------|--------|------|",
        ]
        for i, r in enumerate(top, 1):
            cats = ", ".join(r.categories[:2]) if r.categories else "-"
            lines.append(
                f"| {i} | {r.title[:60]} | {r.organization} | "
                f"{r.confidence_grade}({r.confidence_score:.0f}) | {cats} |"
            )
        return "\n".join(lines)

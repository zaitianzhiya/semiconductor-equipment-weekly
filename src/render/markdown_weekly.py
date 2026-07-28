"""Markdown renderer — weekly report with link + poster columns."""

from datetime import datetime
from pathlib import Path

from src.collectors.base import EventRecord


class MarkdownRenderer:
    """Render weekly reports with separate link and poster image columns."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _event_title(self, r: EventRecord) -> str:
        """Bilingual title: English (main) + Chinese subtitle via <br> if available."""
        en = r.title[:70]
        cn = (r.title_cn or "").strip()[:50]
        if cn and cn != en:
            return f"{en}<br/><small>{cn}</small>"
        return en

    def _poster_img(self, r: EventRecord) -> str:
        """Poster thumbnail as Markdown image or empty."""
        if r.image_url:
            title_short = r.title[:40].replace('"', '')
            return f'<img src="{r.image_url}" alt="{title_short}" width="100" style="border-radius:4px"/>'
        return ""

    def render_weekly_report(
        self,
        records: list[EventRecord],
        deep_analysis: str = "",
        stats: dict = None,
    ) -> str:
        """Generate the main weekly report Markdown file."""
        now = datetime.utcnow()
        week_str = now.strftime("%Y-W%V")

        lines = [
            "---",
            f"date: {now.strftime('%Y-%m-%d')}",
            "type: weekly-moc",
            f"week: {week_str}",
            f"total_events: {len(records)}",
            "---",
            "",
            f"# {week_str} 半导体设备每周周报",
            "",
            f"> 本期共收录 **{len(records)}** 个事件",
            f"> 生成时间: {now.strftime('%Y-%m-%d %H:%M')} UTC",
            "",
            "---",
            "",
        ]

        if deep_analysis:
            lines.append(deep_analysis)
            lines.extend(["", "---", ""])

        top_n = min(len(records), 20)
        lines.append(f"## Top {top_n} 事件")
        lines.append("")
        lines.append("| # | 事件 | 链接 | 海报 | 组织 | 可信度 | 独立源 | 分类 |")
        lines.append("|---|------|------|------|------|--------|--------|------|")

        for i, r in enumerate(records[:top_n], 1):
            cats = " ".join(f"`{c}`" for c in r.categories[:3]) if r.categories else "-"
            poster = self._poster_img(r)
            title_col = self._event_title(r)
            link_col = f"[🔗]({r.url})" if r.url else "-"
            lines.append(
                f"| {i} | {title_col} | {link_col} | {poster} | {r.organization} | "
                f"{r.confidence_grade}({r.confidence_score:.0f}) | "
                f"{r.independent_ecosystems} | {cats} |"
            )

        lines.extend(["", "---", ""])

        lines.append("## 分类整理")
        lines.append("")
        cats = self._group_by_category(records)
        for cat, crecs in sorted(cats.items()):
            lines.append(f"### {cat}")
            lines.append("")
            lines.append("| # | 事件 | 链接 | 海报 | 组织 | 可信度 |")
            lines.append("|---|------|------|------|------|--------|")
            for i, r in enumerate(crecs, 1):
                poster = self._poster_img(r)
                title_col = self._event_title(r)
                link_col = f"[🔗]({r.url})" if r.url else "-"
                lines.append(
                    f"| {i} | {title_col} | {link_col} | {poster} | {r.organization} | "
                    f"{r.confidence_grade} |"
                )
            lines.append("")

        if stats:
            lines.extend(["---", "", "## 数据洞察", ""])
            for k, v in stats.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 反馈",
            "",
            f"> 对本期周报有意见？请提交到 `feedback/{week_str}.md`",
            "> 格式：`- [x] 事件标题: 正确分类为 #分类 (理由)`",
            "> 标记为 `[x]` 表示已确认的永久规则",
            "",
            f"*本期自动生成 | {now.strftime('%Y-%m-%d')}*",
        ])

        content = "\n".join(lines)
        week_dir = self.output_dir / "weekly" / now.strftime("%Y")
        week_dir.mkdir(parents=True, exist_ok=True)
        (week_dir / f"{week_str}.md").write_text(content, encoding="utf-8")
        return content

    def _group_by_category(self, records: list[EventRecord]) -> dict[str, list[EventRecord]]:
        cats: dict[str, list[EventRecord]] = {}
        for r in records:
            for c in r.categories:
                cats.setdefault(c, []).append(r)
        uncat = [r for r in records if not r.categories]
        if uncat:
            cats["未分类"] = uncat
        return cats

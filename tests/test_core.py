"""Core pipeline tests: scorer, quality filter, dedup, categorize, renderer.

Run: pytest tests/ -q
"""
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collectors.base import EventRecord, SourceCitation  # noqa: E402
from src.filters.dedup import Deduplicator  # noqa: E402
from src.filters.quality import QualityFilter  # noqa: E402
from src.filters.scorer import Scorer  # noqa: E402
from src.render.markdown_weekly import MarkdownRenderer  # noqa: E402


def load_config() -> dict:
    cfg: dict = {}
    for fn in ("sources.yml", "keywords.yml", "quality.yml"):
        p = ROOT / "config" / fn
        if p.exists():
            cfg.update(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    return cfg


CONFIG = load_config()


def make_event(eid, title="A long enough title", desc="A" * 40, url="https://example.com/x",
               citations=None, raw=None, published=""):
    return EventRecord(event_id=eid, title=title, description=desc, url=url,
                       raw_data=raw or {}, citations=citations or [], published_at=published)


C1 = SourceCitation(source_key="s1", source_name="S1", tier=1, ecosystem="eco_a")
C2 = SourceCitation(source_key="s2", source_name="S2", tier=1, ecosystem="eco_b")
C3 = SourceCitation(source_key="s3", source_name="S3", tier=2, ecosystem="eco_a")


class TestScorer:
    def test_single_tier1_scores_base_weight(self):
        scorer = Scorer(CONFIG)
        r = make_event("e1", citations=[C1])
        scorer.score([r])
        assert r.confidence_score == pytest.approx(scorer.tier_1_weight, abs=0.01)
        assert r.confidence_grade in ("C", "D")

    def test_single_tier2_scores_base_weight(self):
        scorer = Scorer(CONFIG)
        r = make_event("e2", citations=[C3])
        scorer.score([r])
        assert r.confidence_score == pytest.approx(scorer.tier_2_weight, abs=0.01)
        assert r.confidence_grade in ("C", "D")

    def test_dual_ecosystem_tier1_reaches_high_grade(self):
        scorer = Scorer(CONFIG)
        r = make_event("e3", citations=[C1, C2])
        scorer.score([r])
        expected = (scorer.tier_1_weight * scorer.ecosystem_weights.get("eco_a", 1.0)
                    + scorer.tier_1_weight * scorer.ecosystem_weights.get("eco_b", 1.0))
        assert r.confidence_score == pytest.approx(min(expected, float(scorer.max_score)), abs=0.01)
        assert r.confidence_grade in ("A", "B")

    def test_no_citation_is_zero_and_d(self):
        scorer = Scorer(CONFIG)
        r = make_event("e4", citations=[])
        scorer.score([r])
        assert r.confidence_score == 0.0
        assert r.confidence_grade == "D"

    def test_same_ecosystem_best_tier_wins(self):
        scorer = Scorer(CONFIG)
        r = make_event("e5", citations=[C1, C3])  # T1 + T2 same eco → only T1 counts
        scorer.score([r])
        assert r.confidence_score == pytest.approx(
            scorer.tier_1_weight * scorer.ecosystem_weights.get("eco_a", 1.0), abs=0.01)

    def test_score_capped_at_max(self):
        scorer = Scorer(CONFIG)
        citations = [SourceCitation(source_key=f"s{i}", source_name=f"S{i}", tier=1,
                                    ecosystem=f"eco_{i}") for i in range(10)]
        r = make_event("e6", citations=citations)
        scorer.score([r])
        assert r.confidence_score <= float(scorer.max_score) + 0.01


class TestQualityFilter:
    def test_fallback_records_excluded(self):
        qf = QualityFilter(CONFIG)
        kept, stats = qf.filter([make_event("e1", raw={"fallback": True}, citations=[C1])])
        assert kept == []
        assert stats["fallback_excluded"] == 1

    def test_short_title_excluded(self):
        qf = QualityFilter(CONFIG)
        kept, stats = qf.filter([make_event("e1", title="X", citations=[C1])])
        assert kept == []
        assert stats["title_too_short"] == 1

    def test_too_old_excluded(self):
        qf = QualityFilter(CONFIG)
        if not qf.max_age_days:
            pytest.skip("max_age_days not configured")
        kept, stats = qf.filter([make_event("e1", published="2020-01-01", citations=[C1])])
        assert kept == []
        assert stats["too_old"] == 1

    def test_recent_event_kept(self):
        qf = QualityFilter(CONFIG)
        kept, _ = qf.filter([make_event("e1", published="2099-01-01", citations=[C1])])
        assert len(kept) == 1

    def test_unknown_date_kept_and_counted(self):
        qf = QualityFilter(CONFIG)
        kept, stats = qf.filter([make_event("e1", published="not a date", citations=[C1])])
        assert len(kept) == 1


class TestDedup:
    def test_state_persists_and_second_run_dedups(self, tmp_path):
        state = tmp_path / "dedup_state.json"
        d1 = Deduplicator(str(state))
        new1, seen1 = d1.deduplicate([make_event("evt:aaa"), make_event("evt:bbb")])
        assert len(new1) == 2 and seen1 == 0
        d1.save()
        d2 = Deduplicator(str(state))
        new2, seen2 = d2.deduplicate([make_event("evt:aaa")])
        assert new2 == [] and seen2 == 1

    def test_corrupt_state_recovers_with_backup(self, tmp_path):
        state = tmp_path / "dedup_state.json"
        state.write_text("{ not json", encoding="utf-8")
        d = Deduplicator(str(state))
        assert d.state == {"events": {}}
        assert list(tmp_path.glob("dedup_state.json.corrupt-*"))

    def test_report_week_uses_separate_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPORT_WEEK", "2026-W37")
        d = Deduplicator(str(tmp_path / "dedup_state.json"))
        assert d.state_file.name == "dedup_state_2026-W37.json"
        monkeypatch.delenv("REPORT_WEEK")
        d2 = Deduplicator(str(tmp_path / "dedup_state.json"))
        assert d2.state_file.name == "dedup_state.json"

    def test_invalid_report_week_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPORT_WEEK", "../../evil")
        d = Deduplicator(str(tmp_path / "dedup_state.json"))
        assert d.state_file.name == "dedup_state.json"


class TestCategorize:
    def test_word_boundary_ascii(self):
        from src.main import _kw_match
        assert _kw_match("ip", "anime clip from studio") is False
        assert _kw_match("ip", "the IP adaptation is coming".lower()) is True
        assert _kw_match("ost", "production cost rises") is False

    def test_cjk_substring(self):
        from src.main import _kw_match
        assert _kw_match("声优", "这部动画的声优阵容公布") is True


class TestMerge:
    def test_same_event_id_merges_citations(self):
        from src.main import _merge_records
        r1 = make_event("evt:x", url="https://example.com/a", citations=[C1])
        r2 = make_event("evt:x", url="https://example.com/a", citations=[C2])
        merged = _merge_records([r1, r2])
        assert len(merged) == 1
        assert len(merged[0].citations) == 2


class TestRenderer:
    def test_cell_escaping(self):
        r = MarkdownRenderer(str(ROOT / "output"))
        assert r._cell("a | b") == "a \\| b"
        assert r._cell("x\ny") == "x y"

    def test_report_week_env_controls_filename(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPORT_WEEK", "2026-W37")
        r = MarkdownRenderer(str(tmp_path), category_order=[])
        out = r.render_weekly_report([make_event("evt:1", citations=[C1])])
        p = tmp_path / "weekly" / "2026" / "2026-W37.md"
        assert p.exists()
        assert "2026-W37" in out

    def test_category_order_respected(self, tmp_path):
        order = ["B类", "A类"]
        r = MarkdownRenderer(str(tmp_path), category_order=order)
        recs = [
            make_event("evt:1", citations=[C1], title="Alpha title here"),
            make_event("evt:2", citations=[C2], title="Beta title here"),
        ]
        recs[0].categories = ["A类"]
        recs[1].categories = ["B类"]
        out = r.render_weekly_report(recs)
        assert out.index("### B类") < out.index("### A类")

    def test_iso_week_across_year_boundary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("REPORT_WEEK", "2027-W01")
        r = MarkdownRenderer(str(tmp_path), category_order=[])
        r.render_weekly_report([make_event("evt:1", citations=[C1])])
        p = tmp_path / "weekly" / "2027" / "2027-W01.md"
        assert p.exists()

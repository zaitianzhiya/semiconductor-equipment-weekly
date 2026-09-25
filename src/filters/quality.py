"""Quality filter — apply config-driven health checks to event records."""

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from src.collectors.base import EventRecord


class QualityFilter:
    """Quality gates: placeholder exclusion, title/desc length, citation, freshness.

    filter() returns (kept_records, stats_dict).
    """

    def __init__(self, config: dict):
        fcfg = config.get("filter") or config.get("filters") or {}
        self.min_title_length = fcfg.get("min_title_length", 0)
        self.min_desc_length = fcfg.get("min_desc_length", 0)
        self.require_citation = fcfg.get("require_citation", False)
        self.max_age_days = fcfg.get("max_age_days")

    def filter(self, records: list[EventRecord]):
        kept: list[EventRecord] = []
        stats = {"fallback_excluded": 0, "too_old": 0, "title_too_short": 0,
                 "desc_too_short": 0, "no_citation": 0, "unknown_date": 0, "kept": 0}
        for r in records:
            if (r.raw_data or {}).get("fallback"):
                stats["fallback_excluded"] += 1
                continue
            if len((r.title or "").strip()) < self.min_title_length:
                stats["title_too_short"] += 1
                continue
            if len((r.description or "").strip()) < self.min_desc_length:
                stats["desc_too_short"] += 1
                continue
            if self.require_citation and not r.citations:
                stats["no_citation"] += 1
                continue
            if self.max_age_days:
                verdict = self._freshness(r.published_at)
                if verdict == "old":
                    stats["too_old"] += 1
                    continue
                if verdict == "unknown":
                    stats["unknown_date"] += 1
            kept.append(r)
        stats["kept"] = len(kept)
        return kept, stats

    def _freshness(self, published_at: str) -> str:
        """Return 'fresh' | 'old' | 'unknown'."""
        if not published_at:
            return "unknown"
        dt = self._parse_date(published_at)
        if dt is None:
            return "unknown"
        age = datetime.now(timezone.utc) - dt
        return "fresh" if age <= timedelta(days=self.max_age_days) else "old"

    @staticmethod
    def _parse_date(s: str):
        s = (s or "").strip()
        if not s:
            return None
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            except ValueError:
                return None
        try:
            return parsedate_to_datetime(s)
        except Exception:
            return None

"""Quality filter — apply basic health checks to event records."""

from datetime import datetime

from src.collectors.base import EventRecord


class QualityFilter:
    """Apply quality gates with graceful handling: unknown data passes through."""

    def __init__(self, config: dict):
        self.filters = config.get("filters", {})

    def filter(self, records: list[EventRecord]) -> list[EventRecord]:
        return [r for r in records if self._check(r)]

    def _check(self, record: EventRecord) -> bool:
        if not record.title or not record.citations:
            return False
        return True

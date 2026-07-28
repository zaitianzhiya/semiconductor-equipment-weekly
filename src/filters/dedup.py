"""Deduplicator — JSON-backed state tracking across weeks."""

import json
from datetime import datetime
from pathlib import Path

from src.collectors.base import EventRecord


class Deduplicator:
    """Track which events have been seen across weeks using a JSON state file."""

    def __init__(self, state_path: str = None):
        if state_path:
            self.data_dir = Path(state_path).parent
        else:
            self.data_dir = Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "dedup_state.json"
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"events": {}}

    def _save_state(self):
        self.state_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def deduplicate(self, records: list[EventRecord]) -> tuple[list[EventRecord], int]:
        """Return (new_records, already_seen_count)."""
        now = datetime.utcnow()
        current_week = now.strftime("%Y-W%V")
        new_records: list[EventRecord] = []
        already_seen = 0

        for record in records:
            if record.event_id in self.state["events"]:
                self.state["events"][record.event_id]["last_seen_week"] = current_week
                already_seen += 1
            else:
                self.state["events"][record.event_id] = {
                    "first_seen_week": current_week,
                    "last_seen_week": current_week,
                    "title": record.title,
                }
                new_records.append(record)

        self._save_state()
        return new_records, already_seen

    def get_stats(self) -> dict:
        now = datetime.utcnow()
        current_week = now.strftime("%Y-W%V")
        total = len(self.state["events"])
        new_this_week = sum(
            1
            for e in self.state["events"].values()
            if e.get("first_seen_week") == current_week
        )
        return {"total_seen": total, "new_this_week": new_this_week}

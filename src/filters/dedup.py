"""Deduplicator — JSON-backed state tracking across weeks."""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from src.collectors.base import EventRecord


class Deduplicator:
    """Track which events have been seen across weeks using a JSON state file.

    State is only persisted via save() — call it after the report has been
    written successfully, so a failed render never burns events.
    """

    def __init__(self, state_path: str = None):
        if state_path:
            self.state_file = Path(state_path)
        else:
            self.state_file = Path("data") / "dedup_state.json"
        week_override = os.environ.get("REPORT_WEEK", "")
        if week_override and re.fullmatch(r"\d{4}-W\d{2}", week_override):
            self.state_file = self.state_file.parent / f"dedup_state_{week_override}.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("events"), dict):
                    return data
                raise ValueError("unexpected schema")
            except (json.JSONDecodeError, OSError, ValueError):
                backup = self.state_file.with_name(
                    f"{self.state_file.name}.corrupt-{int(datetime.now().timestamp())}"
                )
                try:
                    self.state_file.replace(backup)
                    print(f"[Dedup] Corrupt state file backed up to {backup.name}")
                except OSError:
                    pass
        return {"events": {}}

    def deduplicate(self, records: list[EventRecord]) -> tuple[list[EventRecord], int]:
        """Return (new_records, already_seen_count). In-memory only; call save() to persist."""
        now = datetime.utcnow()
        current_week = now.strftime("%G-W%V")
        new_records: list[EventRecord] = []
        already_seen = 0

        for record in records:
            if record.event_id in self.state["events"]:
                # Already seen — update last_seen
                self.state["events"][record.event_id]["last_seen_week"] = current_week
                already_seen += 1
            else:
                self.state["events"][record.event_id] = {
                    "first_seen_week": current_week,
                    "last_seen_week": current_week,
                    "title": record.title,
                }
                new_records.append(record)

        return new_records, already_seen

    def save(self):
        """Persist state atomically (tmp file + os.replace)."""
        tmp = self.state_file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.state_file)

    def get_stats(self) -> dict:
        now = datetime.utcnow()
        current_week = now.strftime("%G-W%V")
        total = len(self.state["events"])
        new_this_week = sum(
            1
            for e in self.state["events"].values()
            if e.get("first_seen_week") == current_week
        )
        return {"total_seen": total, "new_this_week": new_this_week}

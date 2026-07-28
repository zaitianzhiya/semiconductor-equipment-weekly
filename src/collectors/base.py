"""Base classes for event collectors."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SourceCitation:
    """Track where an event was discovered."""
    source_key: str
    source_name: str
    tier: int  # 1 = primary, 2 = citation
    ecosystem: str
    url: str = ""
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class EventRecord:
    """Standardized event record across all sources."""

    event_id: str
    title: str
    title_cn: str = ""  # AI-translated Chinese title
    description: str = ""
    url: str = ""
    image_url: str = ""
    published_at: str = ""

    # Organization / source entity
    organization: str = ""
    organization_type: str = ""  # enterprise, research, government, media

    # Scoring
    raw_data: dict = field(default_factory=dict)
    citations: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    confidence_score: float = 0.0
    confidence_grade: str = "D"

    # Modalities (for multimodal AI)
    modalities: list = field(default_factory=list)

    # Tracking
    first_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def citation_count(self) -> int:
        return len(self.citations)

    @property
    def tier1_citations(self) -> int:
        return sum(1 for c in self.citations if c.tier == 1)

    @property
    def independent_ecosystems(self) -> int:
        return len(set(c.ecosystem for c in self.citations))

    def to_frontmatter(self) -> dict:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "organization": self.organization,
            "published_at": self.published_at[:10] if self.published_at else "",
            "confidence_score": round(self.confidence_score, 1),
            "confidence_grade": self.confidence_grade,
            "categories": self.categories,
            "modalities": self.modalities,
            "citation_count": self.citation_count,
            "first_seen": self.first_seen[:10],
        }


class BaseCollector:
    """Base class for all event collectors."""

    def __init__(self, config: dict):
        self.config = config

    def collect(self) -> list[EventRecord]:
        raise NotImplementedError

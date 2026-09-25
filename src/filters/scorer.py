"""Scorer — compute confidence and quality scores for event records."""

from src.collectors.base import EventRecord


class Scorer:
    """Score events based on multi-source consensus and ecosystem independence.

    The scoring model:
      - confidence_score = weighted cross-ecosystem citation count (0-100)
      - confidence_grade = A/B/C/D based on thresholds
    """

    def __init__(self, config: dict):
        scoring_cfg = config.get("scoring", {})
        self.tier_1_weight = scoring_cfg.get("tier_1_weight", 40)
        self.tier_2_weight = scoring_cfg.get("tier_2_weight", 25)
        self.max_score = scoring_cfg.get("max_score", 100)
        grades = scoring_cfg.get("grades", {})
        self.min_a = scoring_cfg.get("min_score_for_A", grades.get("A", 80))
        self.min_b = scoring_cfg.get("min_score_for_B", grades.get("B", 60))
        self.min_c = scoring_cfg.get("min_score_for_C", grades.get("C", 30))
        self.ecosystem_weights = config.get("ecosystem_weights", {})

    def score(self, records: list[EventRecord]) -> list[EventRecord]:
        for r in records:
            r.confidence_score = self._compute_confidence(r)
            r.confidence_grade = self._assign_grade(r.confidence_score)
        return records

    def _compute_confidence(self, record: EventRecord) -> float:
        """Cross-ecosystem independent citation score.

        Each unique ecosystem contributes weighted points:
        - Tier 1 source: tier_1_weight base points
        - Tier 2 source: tier_2_weight base points
        - Multiply by ecosystem weight
        - Cap at max_score
        """
        if not record.citations:
            return 0.0

        # Group by ecosystem, take best tier per ecosystem
        eco_best: dict[str, int] = {}
        for c in record.citations:
            tier_val = 1 if c.tier == 1 else 2  # T1→best
            existing = eco_best.get(c.ecosystem)
            if existing is None or tier_val < existing:
                eco_best[c.ecosystem] = tier_val

        score = 0.0
        for eco, best_tier in eco_best.items():
            eco_weight = self.ecosystem_weights.get(eco, 1.0)
            base = self.tier_1_weight if best_tier == 1 else self.tier_2_weight
            score += base * eco_weight

        return min(score, float(self.max_score))

    def _assign_grade(self, score: float) -> str:
        if score >= self.min_a:
            return "A"
        if score >= self.min_b:
            return "B"
        if score >= self.min_c:
            return "C"
        return "D"

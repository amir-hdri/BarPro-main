"""
Ensemble captcha solver combining multiple strategies.
"""

import logging
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SolveCandidate:
    value: str
    confidence: float
    source: str


class EnsembleSolver:
    """Combine multiple solving attempts for higher accuracy."""

    @staticmethod
    def vote_best_solution(candidates: list[SolveCandidate], min_confidence: float = 0.6) -> str | None:
        """Use voting and confidence weighting to select best solution."""
        if not candidates:
            return None

        # Filter by minimum confidence
        valid = [c for c in candidates if c.confidence >= min_confidence]
        if not valid:
            # Fallback to best confidence if none meet threshold
            valid = sorted(candidates, key=lambda c: c.confidence, reverse=True)[:3]

        # Weighted voting
        vote_scores = {}
        for candidate in valid:
            if candidate.value not in vote_scores:
                vote_scores[candidate.value] = 0.0
            vote_scores[candidate.value] += candidate.confidence

        if not vote_scores:
            return None

        # Get top voted
        best_value = max(vote_scores.items(), key=lambda x: x[1])

        # Require minimum support
        if best_value[1] < 0.5:
            return None

        return best_value[0]

    @staticmethod
    def consensus_filter(results: list[tuple[str, float]], threshold: float = 0.7) -> str | None:
        """Filter results by consensus."""
        if not results:
            return None

        # Count occurrences
        counter = Counter(r[0] for r in results)
        most_common = counter.most_common(1)[0]

        # Check if consensus is strong enough
        consensus_ratio = most_common[1] / len(results)
        if consensus_ratio >= threshold:
            return most_common[0]

        # Fallback to highest confidence
        best = max(results, key=lambda r: r[1])
        if best[1] >= 0.8:
            return best[0]

        return None

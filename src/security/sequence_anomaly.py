from __future__ import annotations

"""Simple sequence-based anomaly detection using a Markov model."""

from collections import defaultdict
import math
from typing import Dict, Iterable, List, Tuple


class MarkovModel:
    def __init__(self) -> None:
        self.transitions: Dict[Tuple[str, str], int] = defaultdict(int)
        self.counts: Dict[str, int] = defaultdict(int)

    def update(self, sequence: Iterable[str]) -> None:
        prev = "<START>"
        for item in sequence:
            self.transitions[(prev, item)] += 1
            self.counts[prev] += 1
            prev = item
        self.transitions[(prev, "<END>")] += 1
        self.counts[prev] += 1

    def transition_prob(self, prev: str, item: str) -> float:
        count = self.transitions.get((prev, item), 0)
        total = self.counts.get(prev, 0)
        if total == 0:
            return 0.0
        return count / total


class SequenceAnomalyDetector:
    """Scores sequences based on deviation from trained transitions."""

    def __init__(self, model: MarkovModel) -> None:
        self.model = model

    def score(self, sequence: Iterable[str]) -> float:
        """Return anomaly score in [0,1]; higher means more anomalous."""
        prev = "<START>"
        log_prob = 0.0
        n = 0
        for item in sequence:
            p = self.model.transition_prob(prev, item)
            log_prob += -math.log(p + 1e-8)
            prev = item
            n += 1
        p = self.model.transition_prob(prev, "<END>")
        log_prob += -math.log(p + 1e-8)
        n += 1
        avg_neg_log = log_prob / max(1, n)
        # Convert to 0-1 range using simple logistic function
        score = 1 - math.exp(-avg_neg_log)
        return max(0.0, min(1.0, score))


def train_markov_model(sequences: Dict[str, List[str]]) -> MarkovModel:
    model = MarkovModel()
    for seq in sequences.values():
        model.update(seq)
    return model
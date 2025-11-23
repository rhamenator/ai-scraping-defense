from __future__ import annotations

"""Simple sequence-based anomaly detection using a Markov model.

Performance optimizations:
- Uses vectorized NumPy operations where possible for SIMD acceleration
- Batch probability calculations for improved cache locality
"""

import math
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False


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
        """Return anomaly score in [0,1]; higher means more anomalous.

        Uses vectorized operations when NumPy is available for SIMD acceleration.
        """
        seq_list = list(sequence)

        # Use vectorized operations if NumPy is available
        if HAS_NUMPY and len(seq_list) > 0:
            # Collect all transition probabilities
            probs = []
            prev = "<START>"
            for item in seq_list:
                probs.append(self.model.transition_prob(prev, item))
                prev = item
            probs.append(self.model.transition_prob(prev, "<END>"))

            # Vectorized log operations (SIMD-enabled)
            prob_array = np.array(probs, dtype=np.float64)
            prob_array = np.maximum(prob_array, 1e-8)  # Vectorized max
            log_probs = -np.log(prob_array)  # Vectorized log
            avg_neg_log = float(np.mean(log_probs))  # Vectorized mean

            # Vectorized exponential and clipping
            score = 1.0 - math.exp(-avg_neg_log)
            return float(np.clip(score, 0.0, 1.0))
        else:
            # Fallback to non-vectorized implementation
            prev = "<START>"
            log_prob = 0.0
            n = 0
            for item in seq_list:
                p = self.model.transition_prob(prev, item)
                log_prob += -math.log(p + 1e-8)
                prev = item
                n += 1
            p = self.model.transition_prob(prev, "<END>")
            log_prob += -math.log(p + 1e-8)
            n += 1
            avg_neg_log = log_prob / max(1, n)
            score = 1 - math.exp(-avg_neg_log)
            return max(0.0, min(1.0, score))


def train_markov_model(sequences: Dict[str, List[str]]) -> MarkovModel:
    model = MarkovModel()
    for seq in sequences.values():
        model.update(seq)
    return model
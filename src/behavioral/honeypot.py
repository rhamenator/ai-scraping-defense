from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Dict, List

try:
    from xgboost import XGBClassifier  # type: ignore
except Exception:  # pragma: no cover - xgboost optional
    XGBClassifier = None

from sklearn.ensemble import RandomForestClassifier

from src.shared.redis_client import get_redis_connection


class SessionTracker:
    """Log request sequences for behavioral analysis."""

    def __init__(self, redis_db: int = 3) -> None:
        self.redis = get_redis_connection(db_number=redis_db)
        self.fallback: Dict[str, List[str]] = defaultdict(list)

    def log_request(self, ip: str, path: str, timestamp: float | None = None) -> None:
        timestamp = timestamp or datetime.datetime.now(datetime.UTC).timestamp()
        entry = f"{timestamp}:{path}"
        if self.redis:
            self.redis.rpush(f"session:{ip}", entry)
        else:
            self.fallback[ip].append(entry)

    def get_sequence(self, ip: str) -> List[str]:
        if self.redis:
            entries = self.redis.lrange(f"session:{ip}", 0, -1)
        else:
            entries = self.fallback[ip]
        return [
            (e.decode() if isinstance(e, bytes) else e).split(":", 1)[1]
            for e in entries
        ]


def _seq_features(seq: List[str]) -> List[float]:
    return [len(seq), len(set(seq))]


def train_behavior_model(sequences: Dict[str, List[str]], labels: Dict[str, int]):
    X: List[List[float]] = []
    y: List[int] = []
    for ip, seq in sequences.items():
        if ip in labels:
            X.append(_seq_features(seq))
            y.append(labels[ip])
    if not X:
        return None
    if XGBClassifier is None:
        model = RandomForestClassifier(n_estimators=10)
    else:
        model = XGBClassifier(n_estimators=10, eval_metric="logloss")
    model.fit(X, y)
    return model

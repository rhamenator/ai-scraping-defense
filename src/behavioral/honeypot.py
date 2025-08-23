from __future__ import annotations

import datetime
from collections import OrderedDict
from typing import Dict, List

try:
    from xgboost import XGBClassifier  # type: ignore
except Exception:  # pragma: no cover - xgboost optional
    XGBClassifier = None

from sklearn.ensemble import RandomForestClassifier

from src.shared.redis_client import get_redis_connection


class SessionTracker:
    """Log request sequences for behavioral analysis."""

    def __init__(
        self,
        redis_db: int = 3,
        *,
        max_fallback_entries: int = 1000,
        cleanup_interval: float = 60.0,
    ) -> None:
        self.redis = get_redis_connection(db_number=redis_db)
        self.fallback: "OrderedDict[str, List[str]]" = OrderedDict()
        self.max_fallback_entries = max_fallback_entries
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = datetime.datetime.now(datetime.UTC)
        self._fallback_counter = 0
        self._cleanup_every = 100

    def log_request(self, ip: str, path: str, timestamp: float | None = None) -> None:
        timestamp = timestamp or datetime.datetime.now(datetime.UTC).timestamp()
        entry = f"{timestamp}:{path}"
        if self.redis:
            self.redis.rpush(f"session:{ip}", entry)
        else:
            if ip in self.fallback:
                self.fallback[ip].append(entry)
            else:
                self.fallback[ip] = [entry]
            self.fallback.move_to_end(ip)
            self._fallback_counter += 1
            if self._fallback_counter >= self._cleanup_every:
                now = datetime.datetime.now(datetime.UTC)
                if (now - self._last_cleanup).total_seconds() >= self.cleanup_interval:
                    self._evict_excess()
                    self._last_cleanup = now
                self._fallback_counter = 0

    def get_sequence(self, ip: str) -> List[str]:
        if self.redis:
            entries = self.redis.lrange(f"session:{ip}", 0, -1)
        else:
            entries = self.fallback.get(ip, [])
            if ip in self.fallback:
                self.fallback.move_to_end(ip)
        return [
            (e.decode() if isinstance(e, bytes) else e).split(":", 1)[1]
            for e in entries
        ]

    def _evict_excess(self) -> None:
        while len(self.fallback) > self.max_fallback_entries:
            self.fallback.popitem(last=False)


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

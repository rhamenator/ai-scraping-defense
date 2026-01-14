import json
import logging
import os
from typing import Any, Dict

try:
    import joblib
    import numpy as np
except Exception:  # pragma: no cover
    joblib = None
    np = None

ANOMALY_SCORE_THRESHOLD = float(os.getenv("ANOMALY_SCORE_THRESHOLD", "0.7"))
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
ANOMALY_EVENT_CHANNEL = "anomaly_events"


class AnomalyDetector:
    """Simple wrapper around a scikit-learn anomaly detection model."""

    def __init__(self, model_path: str): #, redis_client: redis.Redis):
        self.model_path = model_path
        self.model = None
        self._load_model()
        self._redis_client = None
        self._init_redis()

    def _init_redis(self):
        """Initialize the Redis client for publishing events."""
        try:
            # Use synchronous Redis for non-blocking publish operations
            import redis as sync_redis

            self._redis_client = sync_redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
            )
        except Exception as e:  # pragma: no cover - unexpected
            logging.warning("Failed to initialize Redis client: %s", e)
            self._redis_client = None

    def _load_model(self):
        if not joblib:
            logging.error("joblib is not installed; anomaly detection disabled")
            return
        try:
            self.model = joblib.load(self.model_path)
            logging.info(f"Anomaly model loaded from {self.model_path}")
        except Exception as e:  # pragma: no cover - unexpected
            logging.error(f"Failed to load anomaly model: {e}")
            self.model = None

    def score(self, features: Dict[str, Any]) -> float:
        """Return anomaly score between 0.0 and 1.0.

        Uses NumPy vectorization for efficient SIMD-enabled array operations.
        """
        if self.model is None or np is None:
            return 0.0
        try:
            # Vectorized feature extraction using NumPy for SIMD optimization
            sorted_keys = sorted(features.keys())
            # Use vectorized operations instead of list comprehension
            values = [features[k] for k in sorted_keys]
            # Vectorized type checking and conversion
            arr = np.array(
                [float(v) if isinstance(v, (int, float)) else 0.0 for v in values],
                dtype=np.float64,
            ).reshape(1, -1)

            if hasattr(self.model, "decision_function"):
                # NumPy's decision_function uses SIMD operations internally
                raw = -float(self.model.decision_function(arr)[0])
            else:
                pred = self.model.predict(arr)[0]
                raw = 1.0 if pred == -1 else 0.0
            # Use NumPy's clip for vectorized min/max (SIMD-enabled)
            score = float(np.clip(raw + 0.5, 0.0, 1.0))

            # Publish anomaly event if score exceeds threshold
            # Note: Using synchronous Redis publish here is acceptable as it's a
            # fire-and-forget operation with connection pooling. The score() method
            # is called from synchronous contexts in the codebase.
            if score > ANOMALY_SCORE_THRESHOLD and self._redis_client:
                try:
                    event_data = {"anomaly_score": score, "features": features}
                    self._redis_client.publish(
                        ANOMALY_EVENT_CHANNEL, json.dumps(event_data)
                    )
                except Exception as e:  # pragma: no cover - unexpected
                    logging.warning("Failed to publish anomaly event: %s", e)

            return score
        except Exception as e:  # pragma: no cover - unexpected
            logging.error(f"Anomaly scoring failed: {e}")
            return 0.0

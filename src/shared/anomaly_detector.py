import logging
from typing import Dict, Any, List

try:
    import joblib
    import numpy as np
except Exception:  # pragma: no cover
    joblib = None
    np = None


class AnomalyDetector:
    """Simple wrapper around a scikit-learn anomaly detection model."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self._load_model()

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
        """Return anomaly score between 0.0 and 1.0."""
        if self.model is None or np is None:
            return 0.0
        try:
            row: List[float] = []
            for k in sorted(features.keys()):
                v = features[k]
                row.append(float(v) if isinstance(v, (int, float)) else 0.0)
            arr = np.array(row, dtype=float).reshape(1, -1)
            if hasattr(self.model, "decision_function"):
                raw = -float(self.model.decision_function(arr)[0])
            else:
                pred = self.model.predict(arr)[0]
                raw = 1.0 if pred == -1 else 0.0
            score = max(0.0, min(1.0, raw + 0.5))
            return score
        except Exception as e:  # pragma: no cover - unexpected
            logging.error(f"Anomaly scoring failed: {e}")
            return 0.0


import gc
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from src.shared.anomaly_detector import AnomalyDetector


class TestAnomalyDetector(unittest.TestCase):
    @patch("src.shared.anomaly_detector.load_redis_runtime_settings")
    @patch("redis.Redis")
    def test_init_redis_uses_shared_secret_loader(
        self, mock_redis_cls, mock_load_settings
    ):
        mock_load_settings.return_value = ("redis.internal", 6380, 7, "secret")
        model_path = tempfile.NamedTemporaryFile(delete=False, suffix=".joblib").name
        try:
            with patch.object(AnomalyDetector, "_load_model"), patch.object(
                AnomalyDetector, "_redis_client", create=True, new=None
            ):
                detector = AnomalyDetector(model_path)
        finally:
            if os.path.exists(model_path):
                os.unlink(model_path)

        mock_redis_cls.assert_called_once_with(
            host="redis.internal",
            port=6380,
            db=7,
            password="secret",
            decode_responses=True,
        )
        self.assertIsNotNone(detector)

    def test_scores_outlier_higher(self):
        rng = np.random.RandomState(42)
        data = rng.normal(0, 1, size=(100, 2))
        model = IsolationForest(random_state=42)
        model.fit(data)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".joblib")
        tmp_path = tmp.name
        tmp.close()
        joblib.dump(model, tmp_path)
        detector = AnomalyDetector(tmp_path)
        normal = {"f1": 0.0, "f2": 0.0}
        outlier = {"f1": 5.0, "f2": 5.0}
        score_norm = detector.score(normal)
        score_out = detector.score(outlier)
        del detector
        gc.collect()
        os.unlink(tmp_path)
        self.assertLess(score_norm, score_out)


if __name__ == "__main__":
    unittest.main()

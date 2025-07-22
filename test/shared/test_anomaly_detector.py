import unittest
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib
import os
import tempfile

from src.shared.anomaly_detector import AnomalyDetector


class TestAnomalyDetector(unittest.TestCase):
    def test_scores_outlier_higher(self):
        rng = np.random.RandomState(42)
        data = rng.normal(0, 1, size=(100, 2))
        model = IsolationForest(random_state=42)
        model.fit(data)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.joblib')
        joblib.dump(model, tmp.name)
        detector = AnomalyDetector(tmp.name)
        normal = {'f1': 0.0, 'f2': 0.0}
        outlier = {'f1': 5.0, 'f2': 5.0}
        score_norm = detector.score(normal)
        score_out = detector.score(outlier)
        os.unlink(tmp.name)
        self.assertLess(score_norm, score_out)


if __name__ == '__main__':
    unittest.main()

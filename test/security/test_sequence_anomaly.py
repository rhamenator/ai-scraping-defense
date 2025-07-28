import unittest

from src.security.sequence_anomaly import MarkovModel, SequenceAnomalyDetector, train_markov_model


class TestSequenceAnomalyDetector(unittest.TestCase):
    def test_sequence_scoring(self):
        sequences = {
            "ip1": ["/a", "/b", "/c"],
            "ip2": ["/a", "/b", "/d"],
        }
        model = train_markov_model(sequences)
        detector = SequenceAnomalyDetector(model)
        normal_score = detector.score(["/a", "/b", "/c"])
        anomalous_score = detector.score(["/x", "/y", "/z"])
        self.assertLess(normal_score, anomalous_score)


if __name__ == "__main__":
    unittest.main()

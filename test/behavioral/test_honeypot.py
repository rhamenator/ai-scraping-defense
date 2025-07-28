import unittest

from src.behavioral import SessionTracker, train_behavior_model


class TestBehavioralHoneypot(unittest.TestCase):
    def test_tracking_and_model(self):
        tracker = SessionTracker(redis_db=99)  # likely missing -> fallback
        tracker.log_request("1.1.1.1", "/a")
        tracker.log_request("1.1.1.1", "/b")
        seq = tracker.get_sequence("1.1.1.1")
        self.assertEqual(seq, ["/a", "/b"])
        sequences = {"1.1.1.1": seq, "2.2.2.2": ["/x", "/y", "/z"]}
        labels = {"1.1.1.1": 1, "2.2.2.2": 0}
        model = train_behavior_model(sequences, labels)
        self.assertIsNotNone(model)


if __name__ == "__main__":
    unittest.main()

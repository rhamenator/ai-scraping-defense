import unittest

from src.behavioral import SessionTracker, train_behavior_model


class DummyRedis:
    def __init__(self) -> None:
        self.store = {}

    def rpush(self, key: str, value: str) -> None:
        self.store.setdefault(key, []).append(value.encode())

    def lrange(self, key: str, start: int, end: int):
        return self.store.get(key, [])


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

    def test_tracking_with_redis_bytes(self):
        tracker = SessionTracker(redis_db=99)
        tracker.redis = DummyRedis()
        tracker.log_request("1.1.1.1", "/a")
        tracker.log_request("1.1.1.1", "/b")
        seq = tracker.get_sequence("1.1.1.1")
        self.assertEqual(seq, ["/a", "/b"])


if __name__ == "__main__":
    unittest.main()

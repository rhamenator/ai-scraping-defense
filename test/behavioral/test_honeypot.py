import unittest

from src.behavioral import SessionTracker, train_behavior_model


class DummyRedis:
    def __init__(self) -> None:
        self.store = {}

    def rpush(self, key: str, value: str) -> None:
        # Mimic Redis by storing the pre-formatted entry as bytes
        self.store.setdefault(key, []).append(value.encode())

    def lrange(self, key: str, start: int, end: int):
        return self.store.get(key, [])[start : end + 1 if end != -1 else None]


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

    def test_fallback_eviction(self):
        tracker = SessionTracker(
            redis_db=99, max_fallback_entries=2, cleanup_interval=0
        )
        tracker._cleanup_every = 1
        tracker.log_request("1.1.1.1", "/a")
        tracker.log_request("2.2.2.2", "/b")
        tracker.log_request("3.3.3.3", "/c")
        self.assertNotIn("1.1.1.1", tracker.fallback)
        tracker.log_request("2.2.2.2", "/d")
        tracker.log_request("4.4.4.4", "/e")
        self.assertNotIn("3.3.3.3", tracker.fallback)
        self.assertIn("2.2.2.2", tracker.fallback)
        self.assertIn("4.4.4.4", tracker.fallback)

    def test_batched_cleanup(self):
        tracker = SessionTracker(redis_db=99, cleanup_interval=0)
        tracker._cleanup_every = 2
        first_cleanup = tracker._last_cleanup
        tracker.log_request("1.1.1.1", "/a")
        self.assertEqual(tracker._fallback_counter, 1)
        self.assertEqual(tracker._last_cleanup, first_cleanup)
        tracker.log_request("2.2.2.2", "/b")
        self.assertEqual(tracker._fallback_counter, 0)
        self.assertNotEqual(tracker._last_cleanup, first_cleanup)


if __name__ == "__main__":
    unittest.main()

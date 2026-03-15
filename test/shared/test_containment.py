import json
import unittest
from unittest.mock import MagicMock, patch

from src.shared import containment


class TestContainmentHelpers(unittest.TestCase):
    def test_apply_ip_throttle_persists_metadata(self):
        redis_mock = MagicMock()
        with patch.object(containment, "get_redis_connection", return_value=redis_mock):
            result = containment.apply_ip_throttle(
                "8.8.8.8",
                reason="heuristic throttle",
                score=0.87,
                source="heuristic_score",
                ttl_seconds=120,
                rate_limit_per_minute=5,
                extra_details={"path": "/login"},
            )

        self.assertTrue(result)
        redis_mock.setex.assert_called_once()
        key, ttl_seconds, payload_json = redis_mock.setex.call_args.args
        self.assertEqual(key, "default:throttle:ip:8.8.8.8")
        self.assertEqual(ttl_seconds, 120)
        payload = json.loads(payload_json)
        self.assertEqual(payload["source"], "heuristic_score")
        self.assertEqual(payload["rate_limit_per_minute"], 5)
        self.assertEqual(payload["details"]["path"], "/login")

    def test_get_ip_throttle_returns_metadata_with_ttl(self):
        redis_mock = MagicMock()
        redis_mock.get.return_value = json.dumps({"reason": "threshold hit"})
        redis_mock.ttl.return_value = 45
        with patch.object(containment, "get_redis_connection", return_value=redis_mock):
            result = containment.get_ip_throttle("9.9.9.9")

        self.assertEqual(result["reason"], "threshold hit")
        self.assertEqual(result["ttl_seconds"], 45)

    def test_apply_ip_throttle_rejects_invalid_ip(self):
        with patch.object(containment, "get_redis_connection") as mock_redis:
            result = containment.apply_ip_throttle(
                "not-an-ip",
                reason="invalid",
                score=0.9,
                source="heuristic_score",
            )

        self.assertFalse(result)
        mock_redis.assert_not_called()

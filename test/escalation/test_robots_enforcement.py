"""Exercise HTTP -> real scoring/policy -> real containment -> recorded decision."""

import os
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from src.escalation import escalation_engine as ee


class TestRobotsEnforcement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(
            patch.dict(os.environ, {"ESCALATION_API_KEY": "testkey"})
        )
        self.original_paths = ee.disallowed_paths
        if hasattr(ee, "robots_groups"):
            self.addCleanup(setattr, ee, "robots_groups", ee.robots_groups)
        self.addCleanup(setattr, ee, "disallowed_paths", self.original_paths)
        ee.load_robots_txt(Path(__file__).resolve().parents[2] / "config/robots.txt")
        for name, value in {
            "MODEL_LOADED": False,
            "anomaly_detector": None,
            "PLUGINS": [],
            "ENABLE_IP_REPUTATION": False,
            "ENABLE_LOCAL_LLM_CLASSIFICATION": False,
            "ENABLE_EXTERNAL_API_CLASSIFICATION": False,
        }.items():
            self.stack.enter_context(patch.object(ee, name, value))
        self.stack.enter_context(
            patch.object(
                ee,
                "get_realtime_frequency_features",
                return_value={"count": 1, "time_since": 100},
            )
        )
        self.stack.enter_context(patch.object(ee, "track_fingerprint", return_value=0))
        self.stack.enter_context(patch.object(ee, "get_country_code", return_value=""))
        self.block = self.stack.enter_context(
            patch.object(ee, "add_ip_to_blocklist", return_value=True)
        )
        self.record = self.stack.enter_context(patch.object(ee, "record_decision"))
        self.webhook = self.stack.enter_context(
            patch.object(ee, "forward_to_webhook", new_callable=AsyncMock)
        )
        self.stack.enter_context(patch.object(ee, "publish_operational_event"))
        self.stack.enter_context(
            patch.object(ee, "record_and_alert_attack", new_callable=AsyncMock)
        )

    def metadata(self, ua, path):
        return {
            "timestamp": "2026-11-20T00:00:00Z",
            "ip": "192.0.2.10",
            "source": "robots-regression",
            "user_agent": ua,
            "path": path,
            "method": "GET",
            "headers": {"Accept-Language": "en-US"},
        }

    def test_robots_add_exactly_point_six_for_every_ua(self):
        for ua in ["Firefox", "Googlebot/2.1", "Bingbot/2.0"]:
            allowed = ee.run_heuristic_and_model_analysis(
                ee.RequestMetadata(**self.metadata(ua, "/pricing"))
            )
            for path in ["/admin/", "/api/metrics", "/%61dmin/"]:
                blocked = ee.run_heuristic_and_model_analysis(
                    ee.RequestMetadata(**self.metadata(ua, path))
                )
                self.assertAlmostEqual(blocked - allowed, 0.6)

    def test_benign_claim_cannot_cancel_bad_ua_score(self):
        with patch.object(ee, "KNOWN_BAD_UAS", ["curl"]):
            metadata = ee.RequestMetadata(
                **self.metadata("curl Googlebot/2.1", "/pricing")
            )
            self.assertAlmostEqual(ee.run_heuristic_and_model_analysis(metadata), 0.7)

    async def test_http_robots_violation_blocks_without_classifier_and_records_action(
        self,
    ):
        transport = httpx.ASGITransport(app=ee.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            for ua in ["Firefox", "Googlebot/2.1", "Bingbot/2.0"]:
                for path in ["/admin/", "/api/metrics", "/%61dmin/"]:
                    with self.subTest(ua=ua, path=path):
                        self.block.reset_mock()
                        self.record.reset_mock()
                        # A robot violation must be handled before any model scoring.
                        with patch.object(
                            ee,
                            "run_heuristic_and_model_analysis",
                            side_effect=AssertionError("classifier reached"),
                        ):
                            response = await client.post(
                                "/escalate",
                                json=self.metadata(ua, path),
                                headers={"X-API-Key": "testkey"},
                            )
                        self.assertEqual(response.status_code, 200, response.text)
                        result = response.json()
                        self.assertEqual(
                            result["action"], "containment_block_robots_violation"
                        )
                        self.assertTrue(result["is_bot_decision"])
                        self.assertGreaterEqual(
                            result["score"], ee.ESCALATION_BLOCK_THRESHOLD
                        )
                        self.block.assert_called_once()
                        self.record.assert_called_once()
                        self.assertEqual(
                            self.record.call_args.args[4], result["action"]
                        )
                        self.assertEqual(self.block.call_args.args[2]["path"], path)
            for ua in ["Firefox", "Googlebot/2.1", "Bingbot/2.0"]:
                self.block.reset_mock()
                response = await client.post(
                    "/escalate",
                    json=self.metadata(ua, "/pricing"),
                    headers={"X-API-Key": "testkey"},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["score"], 0.0)
                self.assertFalse(response.json()["is_bot_decision"])
                self.block.assert_not_called()

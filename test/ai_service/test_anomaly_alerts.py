import unittest
from unittest.mock import AsyncMock, patch

from src.ai_service import alerts


class TestAnomalyAlerts(unittest.IsolatedAsyncioTestCase):
    async def test_anomaly_below_threshold_no_actions(self):
        config = {
            "actions": {"alert", "blocklist"},
            "alert_threshold": 0.9,
            "block_threshold": 0.95,
            "escalate_threshold": 0.97,
        }
        with patch("src.ai_service.alerts._load_anomaly_config", return_value=config):
            with patch(
                "src.ai_service.alerts.send_alert", new=AsyncMock()
            ) as send_alert:
                with patch("src.ai_service.blocklist.add_ip_to_blocklist") as add_block:
                    with patch(
                        "src.ai_service.alerts.publish_operational_event"
                    ) as publish_event:
                        await alerts.handle_anomaly_event(
                            {"anomaly_score": 0.5, "features": {"ip": "1.1.1.1"}}
                        )
        send_alert.assert_not_called()
        add_block.assert_not_called()
        publish_event.assert_not_called()

    async def test_anomaly_alert_triggers(self):
        config = {
            "actions": {"alert"},
            "alert_threshold": 0.9,
            "block_threshold": 0.95,
            "escalate_threshold": 0.97,
        }
        with patch("src.ai_service.alerts._load_anomaly_config", return_value=config):
            with patch(
                "src.ai_service.alerts.send_alert", new=AsyncMock()
            ) as send_alert:
                with patch(
                    "src.ai_service.alerts.publish_operational_event"
                ) as publish_event:
                    await alerts.handle_anomaly_event(
                        {"anomaly_score": 0.95, "features": {"ip": "2.2.2.2"}}
                    )
        send_alert.assert_awaited_once()
        event = send_alert.call_args[0][0]
        self.assertEqual(event.details["ip"], "2.2.2.2")
        self.assertIn("Anomaly Score", event.reason)
        publish_event.assert_called_once()

    async def test_anomaly_blocklist_triggers(self):
        config = {
            "actions": {"alert", "blocklist"},
            "alert_threshold": 0.9,
            "block_threshold": 0.92,
            "escalate_threshold": 0.97,
        }
        with patch("src.ai_service.alerts._load_anomaly_config", return_value=config):
            with patch(
                "src.ai_service.alerts.send_alert", new=AsyncMock()
            ) as send_alert:
                with patch(
                    "src.ai_service.blocklist.add_ip_to_blocklist", return_value=True
                ) as add_block:
                    with patch(
                        "src.ai_service.alerts.publish_operational_event"
                    ) as publish_event:
                        await alerts.handle_anomaly_event(
                            {"anomaly_score": 0.95, "features": {"ip": "3.3.3.3"}}
                        )
        send_alert.assert_awaited_once()
        add_block.assert_called_once()
        self.assertIn("anomaly_blocklisted", publish_event.call_args_list[-1][0][0])


if __name__ == "__main__":
    unittest.main()

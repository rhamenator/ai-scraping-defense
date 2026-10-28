import os
import unittest
from unittest.mock import AsyncMock, patch

from src.shared.attack_incident import record_and_alert_attack


class TestAttackIncident(unittest.IsolatedAsyncioTestCase):
    async def test_attack_alert_includes_manual_cloudflare_and_failover_choices(self):
        settings = {
            "ALERT_METHOD": "webhook",
            "ENABLE_GLOBAL_CDN": "true",
            "CLOUD_CDN_PROVIDER": "cloudflare",
            "ATTACK_INCIDENT_MIN_EVENTS": "3",
            "ATTACK_INCIDENT_MIN_UNIQUE_IPS": "2",
            "ATTACK_INCIDENT_WINDOW_SECONDS": "60",
            "ATTACK_INCIDENT_PRIMARY_HEALTH_URL": "http://primary.test/health",
            "ATTACK_INCIDENT_BACKUP_HEALTH_URL": "http://backup.test/health",
        }
        with (
            patch.dict(os.environ, settings),
            patch("src.shared.attack_incident._record_signal", return_value=(3, 2)),
            patch("src.shared.attack_incident._claim_alert", return_value=True),
            patch(
                "src.shared.attack_incident._origin_health",
                new_callable=AsyncMock,
                side_effect=["unhealthy", "healthy"],
            ),
            patch("src.shared.attack_incident.publish_operational_event"),
            patch("src.ai_service.alerts.send_alert", new_callable=AsyncMock) as send,
        ):
            await record_and_alert_attack("198.51.100.8", 0.96, "tarpit_api")

        send.assert_awaited_once()
        event = send.call_args.args[0]
        self.assertEqual(event.event_type, "attack_incident")
        self.assertEqual(
            event.details["recommended_actions"],
            [
                "review_cloudflare_under_attack_mode",
                "review_failover_to_healthy_backup",
            ],
        )
        self.assertTrue(event.details["operator_action_required"])

    async def test_no_failover_advice_when_primary_is_healthy(self):
        settings = {
            "ALERT_METHOD": "webhook",
            "ENABLE_GLOBAL_CDN": "true",
            "ATTACK_INCIDENT_MIN_EVENTS": "3",
            "ATTACK_INCIDENT_MIN_UNIQUE_IPS": "2",
        }
        with (
            patch.dict(os.environ, settings),
            patch("src.shared.attack_incident._record_signal", return_value=(3, 2)),
            patch("src.shared.attack_incident._claim_alert", return_value=True),
            patch(
                "src.shared.attack_incident._origin_health",
                new_callable=AsyncMock,
                side_effect=["healthy", "healthy"],
            ),
            patch("src.shared.attack_incident.publish_operational_event"),
            patch("src.ai_service.alerts.send_alert", new_callable=AsyncMock) as send,
        ):
            await record_and_alert_attack("198.51.100.8", 0.96, "tarpit_api")

        self.assertEqual(
            send.call_args.args[0].details["recommended_actions"],
            ["review_cloudflare_under_attack_mode"],
        )

    async def test_threshold_and_cooldown_prevent_duplicate_alerts(self):
        settings = {
            "ALERT_METHOD": "webhook",
            "ATTACK_INCIDENT_MIN_EVENTS": "3",
            "ATTACK_INCIDENT_MIN_UNIQUE_IPS": "2",
        }
        with (
            patch.dict(os.environ, settings),
            patch(
                "src.shared.attack_incident._record_signal",
                side_effect=[(2, 2), (3, 2), (4, 2)],
            ),
            patch("src.shared.attack_incident._claim_alert", side_effect=[True, False]),
            patch(
                "src.shared.attack_incident._origin_health",
                new_callable=AsyncMock,
                return_value="unconfigured",
            ),
            patch("src.shared.attack_incident.publish_operational_event"),
            patch("src.ai_service.alerts.send_alert", new_callable=AsyncMock) as send,
        ):
            for _ in range(3):
                await record_and_alert_attack("198.51.100.8", 0.96, "tarpit_api")

        send.assert_awaited_once()

    async def test_no_channel_skips_attack_tracking(self):
        with (
            patch.dict(os.environ, {"ALERT_METHOD": "none"}),
            patch("src.shared.attack_incident._record_signal") as record,
        ):
            await record_and_alert_attack("198.51.100.8", 0.96, "tarpit_api")
        record.assert_not_called()

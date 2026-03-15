import importlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch


class TestSecurityEvents(unittest.TestCase):
    def test_record_and_export_redacts_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            os.environ,
            {"SECURITY_EVENTS_DB_PATH": os.path.join(tmpdir, "security_events.db")},
            clear=False,
        ):
            from src.shared import security_events

            module = importlib.reload(security_events)
            module.record_security_event(
                "alert_delivery",
                actor="system",
                action="delivered",
                source="http_alert",
                payload={
                    "ip": "192.168.1.10",
                    "path": "/admin",
                    "api_key": "super-secret",
                    "nested": {"token": "abc"},
                },
                created_at="2026-03-15T13:30:00+00:00",
            )

            events = module.load_security_events(limit=10)
            count, jsonl = module.export_security_events(limit=10)

        self.assertEqual(count, 1)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event_type"], "alert_delivery")
        self.assertEqual(event["ip"], "[REDACTED_IP]")
        self.assertEqual(event["path"], "/admin")
        self.assertEqual(event["payload"]["ip"], "[REDACTED_IP]")
        self.assertEqual(event["payload"]["api_key"], "<redacted>")
        self.assertEqual(event["payload"]["nested"]["token"], "<redacted>")

        exported = json.loads(jsonl.strip())
        self.assertEqual(exported["payload"]["api_key"], "<redacted>")

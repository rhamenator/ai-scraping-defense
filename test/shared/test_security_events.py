import importlib
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


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

    def test_backend_selection_rejects_unknown_backend(self):
        from src.shared import security_events

        with patch.dict(os.environ, {"AUDIT_STORAGE_BACKEND": "unknown"}):
            with self.assertRaisesRegex(ValueError, "sqlite, postgres"):
                security_events._create_store()

    def test_postgres_backend_uses_dedicated_connection_settings(self):
        from src.shared.security_events import PostgresSecurityEventStore

        environment = {
            "SECURITY_EVENTS_PG_HOST": "audit-db",
            "SECURITY_EVENTS_PG_PORT": "5544",
            "SECURITY_EVENTS_PG_DBNAME": "audit",
            "SECURITY_EVENTS_PG_USER": "auditor",
            "SECURITY_EVENTS_PG_PASSWORD": "test-only",
        }
        with patch.dict(os.environ, environment, clear=False):
            store = PostgresSecurityEventStore()

        self.assertEqual(store.connect_kwargs["host"], "audit-db")
        self.assertEqual(store.connect_kwargs["port"], 5544)
        self.assertEqual(store.connect_kwargs["dbname"], "audit")
        self.assertEqual(store.connect_kwargs["user"], "auditor")
        self.assertEqual(store.connect_kwargs["password"], "test-only")

    def test_explicit_postgres_backend_is_validated_during_creation(self):
        from src.shared import security_events

        store = MagicMock(backend_name="postgres")
        with (
            patch.dict(os.environ, {"AUDIT_STORAGE_BACKEND": "postgres"}),
            patch.object(
                security_events,
                "PostgresSecurityEventStore",
                return_value=store,
            ),
        ):
            self.assertIs(security_events._create_store(), store)

        store.validate.assert_called_once_with()

    def test_export_limit_is_bounded(self):
        from src.shared import security_events

        with self.assertRaisesRegex(ValueError, "between 1"):
            security_events.load_security_events(limit=0)

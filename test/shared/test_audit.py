# test/shared/test_audit.py
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


def _close_audit_handlers(audit_module) -> None:
    for handler in list(audit_module.logger.handlers):
        audit_module.logger.removeHandler(handler)
        handler.flush()
        handler.close()


class TestAuditLogging(unittest.TestCase):
    def tearDown(self):
        # Clean up logger handlers if audit module was imported
        if hasattr(self, "audit"):
            _close_audit_handlers(self.audit)

    def test_log_event_writes_expected_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "audit.log")
            with patch.dict(os.environ, {"AUDIT_LOG_FILE": log_file}):
                from src.shared import audit

                self.audit = audit
                _close_audit_handlers(audit)
                importlib.reload(audit)
                audit.log_event("user", "action", {"foo": "bar"})
            with open(log_file, encoding="utf-8") as f:
                line = f.read().strip()
            _close_audit_handlers(audit)
        self.assertIn('user\taction\t{"foo": "bar"}', line)

    def test_log_event_masks_sensitive_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "audit.log")
            with patch.dict(os.environ, {"AUDIT_LOG_FILE": log_file}):
                from src.shared import audit

                self.audit = audit
                _close_audit_handlers(audit)
                importlib.reload(audit)
                audit.log_event(
                    "user",
                    "action",
                    {"ip": "192.168.0.1", "api_key": "ABC123", "password": "secret"},
                )
            with open(log_file, encoding="utf-8") as f:
                line = f.read()
            _close_audit_handlers(audit)
        assert "192.168.0.1" not in line
        assert "ABC123" not in line
        assert "secret" not in line
        assert '"ip": "[REDACTED_IP]"' in line
        assert '"api_key": "<redacted>"' in line
        assert '"password": "<redacted>"' in line

    def test_log_event_persists_security_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "audit.log")
            with patch.dict(os.environ, {"AUDIT_LOG_FILE": log_file}):
                from src.shared import audit

                self.audit = audit
                _close_audit_handlers(audit)
                importlib.reload(audit)
                with patch.object(audit, "record_security_event") as mock_record_event:
                    audit.log_event("user", "action", {"path": "/admin"})
                _close_audit_handlers(audit)

        mock_record_event.assert_called_once()
        self.assertEqual(mock_record_event.call_args.kwargs["action"], "action")

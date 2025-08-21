# test/shared/test_audit.py
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


class TestAuditLogging(unittest.TestCase):
    def tearDown(self):
        # Clean up logger handlers if audit module was imported
        if hasattr(self, "audit"):
            for h in list(self.audit.logger.handlers):
                self.audit.logger.removeHandler(h)
                h.close()

    def test_log_event_writes_expected_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "audit.log")
            with patch.dict(os.environ, {"AUDIT_LOG_FILE": log_file}):
                from src.shared import audit

                self.audit = audit
                for h in list(audit.logger.handlers):
                    audit.logger.removeHandler(h)
                importlib.reload(audit)
                audit.log_event("user", "action", {"foo": "bar"})
            with open(log_file) as f:
                line = f.read().strip()
        self.assertIn('user\taction\t{"foo": "bar"}', line)

    def test_log_event_masks_sensitive_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "audit.log")
            with patch.dict(os.environ, {"AUDIT_LOG_FILE": log_file}):
                from src.shared import audit

                self.audit = audit
                for h in list(audit.logger.handlers):
                    audit.logger.removeHandler(h)
                importlib.reload(audit)
                audit.log_event(
                    "user",
                    "action",
                    {"ip": "192.168.0.1", "api_key": "ABC123", "password": "secret"},
                )
            with open(log_file) as f:
                line = f.read()
        assert "192.168.0.1" not in line
        assert "ABC123" not in line
        assert "secret" not in line
        assert '"ip": "[REDACTED_IP]"' in line
        assert '"api_key": "<redacted>"' in line
        assert '"password": "<redacted>"' in line

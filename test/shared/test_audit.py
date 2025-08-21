# test/shared/test_audit.py
import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


class TestAuditLogging(unittest.TestCase):
    def test_log_event_writes_expected_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "audit.log")
            with patch.dict(os.environ, {"AUDIT_LOG_FILE": log_file}):
                from src.shared import audit

                for h in list(audit.logger.handlers):
                    audit.logger.removeHandler(h)
                    h.close()
                importlib.reload(audit)
                audit.log_event("user", "action", {"foo": "bar"})
            with open(log_file) as f:
                line = f.read().strip()
        self.assertIn('user\taction\t{"foo": "bar"}', line)

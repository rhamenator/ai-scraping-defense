import os
import unittest
from unittest.mock import patch

from src.util import tls_manager


class TestTLSManager(unittest.TestCase):
    def test_disabled_tls_returns_false(self):
        with patch.dict(os.environ, {"ENABLE_MANAGED_TLS": "false"}, clear=False):
            self.assertFalse(tls_manager.ensure_certificate("example.com"))

    def test_invalid_domain_returns_false(self):
        with patch.dict(os.environ, {"ENABLE_MANAGED_TLS": "true"}, clear=False):
            self.assertFalse(tls_manager.ensure_certificate("not a domain"))

    def test_certbot_requires_email(self):
        with patch.dict(
            os.environ,
            {"ENABLE_MANAGED_TLS": "true", "TLS_PROVIDER": "certbot"},
            clear=False,
        ), patch("src.util.tls_manager.shutil.which", return_value="/usr/bin/certbot"):
            self.assertFalse(tls_manager.ensure_certificate("example.com"))

    def test_certbot_command_executes(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_MANAGED_TLS": "true",
                "TLS_PROVIDER": "certbot",
                "TLS_EMAIL": "ops@example.com",
                "TLS_WEBROOT": "/var/www/html",
            },
            clear=False,
        ), patch("src.util.tls_manager.shutil.which", return_value="/usr/bin/certbot"), patch(
            "src.util.tls_manager.subprocess.run"
        ) as mock_run:
            mock_run.return_value.stdout = "ok"
            self.assertTrue(tls_manager.ensure_certificate("example.com"))
            mock_run.assert_called_once()
            command = mock_run.call_args.args[0]
            self.assertIn("/usr/bin/certbot", command)
            self.assertIn("--webroot", command)


if __name__ == "__main__":
    unittest.main()

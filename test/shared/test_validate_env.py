import tempfile
import unittest
from pathlib import Path

from scripts import validate_env


class TestValidateEnvMonitoringPorts(unittest.TestCase):
    def test_missing_monitoring_ports(self):
        content = """MODEL_URI=sklearn:///model
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
REAL_BACKEND_HOST=http://localhost
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(any("PROMETHEUS_PORT" in e for e in errors))
            self.assertTrue(any("GRAFANA_PORT" in e for e in errors))

    def test_invalid_monitoring_ports(self):
        content = """MODEL_URI=sklearn:///model
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMETHEUS_PORT=abc
GRAFANA_PORT=99999
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
REAL_BACKEND_HOST=http://localhost
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(any("PROMETHEUS_PORT" in e for e in errors))
            self.assertTrue(any("GRAFANA_PORT" in e for e in errors))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from scripts import validate_env


class TestValidateEnv(unittest.TestCase):
    def test_valid_env(self):
        content = """MODEL_URI=sklearn:///model
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
REAL_BACKEND_HOSTS=http://localhost
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertEqual(errors, [])

    def test_missing_required(self):
        content = "MODEL_URI=sklearn:///model"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(any("NGINX_HTTP_PORT" in e for e in errors))
            self.assertTrue(any("PROMPT_ROUTER_PORT" in e for e in errors))
            self.assertTrue(any("PROMETHEUS_PORT" in e for e in errors))
            self.assertTrue(any("GRAFANA_PORT" in e for e in errors))

    def test_model_specific_key(self):
        content = """MODEL_URI=openai://gpt-4
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
REAL_BACKEND_HOSTS=http://localhost
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(any("OPENAI_API_KEY" in e for e in errors))

    def test_global_cdn_requires_cloudflare_credentials(self):
        content = """MODEL_URI=sklearn:///model
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
REAL_BACKEND_HOSTS=http://localhost
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
ENABLE_GLOBAL_CDN=true
CLOUD_CDN_PROVIDER=cloudflare
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(any("CLOUD_CDN_API_TOKEN" in e for e in errors))
            self.assertTrue(any("CLOUD_CDN_ZONE_ID" in e for e in errors))

    def test_global_cdn_allows_token_file_and_zone(self):
        content = """MODEL_URI=sklearn:///model
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
REAL_BACKEND_HOSTS=http://localhost
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
ENABLE_GLOBAL_CDN=true
CLOUD_CDN_PROVIDER=cloudflare
CLOUD_CDN_API_TOKEN_FILE=/run/secrets/cdn_token
CLOUD_CDN_ZONE_ID=zone-id
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertEqual(errors, [])

    def test_require_cloudflare_requires_global_cdn(self):
        content = """MODEL_URI=sklearn:///model
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
REAL_BACKEND_HOSTS=http://localhost
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
REQUIRE_CLOUDFLARE_ACCOUNT=true
CLOUD_CDN_PROVIDER=cloudflare
CLOUD_CDN_API_TOKEN=test-token
CLOUD_CDN_ZONE_ID=zone-id
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(any("ENABLE_GLOBAL_CDN must be true" in e for e in errors))


if __name__ == "__main__":
    unittest.main()

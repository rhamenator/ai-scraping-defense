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
            self.assertTrue(
                any("SECURITY_CDN_TRUSTED_PROXY_CIDRS" in e for e in errors)
            )

    def test_require_cloudflare_requires_lockdown_or_tunnel(self):
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
REQUIRE_CLOUDFLARE_ACCOUNT=true
CLOUD_CDN_PROVIDER=cloudflare
CLOUD_CDN_API_TOKEN=test-token
CLOUD_CDN_ZONE_ID=zone-id
SECURITY_CDN_TRUSTED_PROXY_CIDRS=173.245.48.0/20
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(
                any("SECURITY_CDN_ORIGIN_LOCKDOWN=true" in e for e in errors)
            )

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
SECURITY_CDN_TRUSTED_PROXY_CIDRS=173.245.48.0/20,103.21.244.0/22
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertEqual(errors, [])

    def test_require_cloudflare_accepts_named_tunnel_without_lockdown(self):
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
REQUIRE_CLOUDFLARE_ACCOUNT=true
CLOUD_CDN_PROVIDER=cloudflare
CLOUD_CDN_API_TOKEN=test-token
CLOUD_CDN_ZONE_ID=zone-id
SECURITY_CDN_TRUSTED_PROXY_CIDRS=173.245.48.0/20
CLOUDFLARE_TUNNEL_TOKEN=tunnel-token
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
SECURITY_CDN_TRUSTED_PROXY_CIDRS=173.245.48.0/20
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(any("ENABLE_GLOBAL_CDN must be true" in e for e in errors))

    def test_origin_lockdown_requires_trusted_proxy_cidrs(self):
        content = """MODEL_URI=sklearn:///model
NGINX_HTTP_PORT=8080
NGINX_HTTPS_PORT=8443
ADMIN_UI_PORT=5002
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
REAL_BACKEND_HOSTS=http://localhost
PROMPT_ROUTER_PORT=8009
PROMPT_ROUTER_HOST=router
SECURITY_CDN_ORIGIN_LOCKDOWN=true
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(content)
            env = validate_env.parse_env(path)
            errors = validate_env.validate_env(env)
            self.assertTrue(
                any(
                    "SECURITY_CDN_TRUSTED_PROXY_CIDRS is required when SECURITY_CDN_ORIGIN_LOCKDOWN=true"
                    in e
                    for e in errors
                )
            )


if __name__ == "__main__":
    unittest.main()

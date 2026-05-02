import unittest

from src.shared.service_identity import (
    InternalAuthMode,
    build_cloud_proxy_headers,
    load_internal_auth_mode,
)


class TestServiceIdentity(unittest.TestCase):
    def test_load_internal_auth_mode_defaults_to_shared_key(self):
        mode = load_internal_auth_mode({})
        self.assertEqual(mode, InternalAuthMode.SHARED_KEY)

    def test_load_internal_auth_mode_rejects_unknown_value(self):
        with self.assertRaises(ValueError):
            load_internal_auth_mode({"INTERNAL_AUTH_MODE": "mtls"})

    def test_build_cloud_proxy_headers_requires_proxy_key(self):
        with self.assertRaises(RuntimeError):
            build_cloud_proxy_headers({"INTERNAL_AUTH_MODE": "shared_key"})

    def test_build_cloud_proxy_headers_returns_proxy_key(self):
        headers = build_cloud_proxy_headers(
            {
                "INTERNAL_AUTH_MODE": "shared_key",
                "PROXY_KEY": "proxy-secret",
            }
        )
        self.assertEqual(headers["X-Proxy-Key"], "proxy-secret")

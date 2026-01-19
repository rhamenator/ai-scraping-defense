"""Tests for JWT authorization helpers."""

import importlib
import os
import time
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request


def _build_request(token: str) -> Request:
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    return Request(scope)


class TestAuthz(unittest.TestCase):
    """Validate JWT auth behavior and error handling."""

    def _reload_authz(self, env: dict) -> object:
        import src.shared.authz as authz

        with patch.dict(os.environ, env, clear=True):
            return importlib.reload(authz)

    def test_invalid_token_detail_is_generic(self):
        """Ensure invalid tokens do not leak details."""
        try:
            import jwt as pyjwt
        except Exception:
            self.skipTest("PyJWT not installed")

        env = {
            "AUTH_JWT_SECRET": "valid-secret",
            "AUTH_JWT_ALGORITHMS": "HS256",
        }
        authz = self._reload_authz(env)
        now = int(time.time())
        token = pyjwt.encode(
            {"exp": now + 60, "iat": now},
            "wrong-secret",
            algorithm="HS256",
        )

        request = _build_request(token)
        with self.assertRaises(HTTPException) as ctx:
            authz.verify_jwt_from_request(request)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid token")

    def test_unsupported_jwt_algorithm_configuration(self):
        """Ensure unsupported algorithm config is rejected."""
        try:
            import jwt as pyjwt
        except Exception:
            self.skipTest("PyJWT not installed")

        env = {
            "AUTH_JWT_SECRET": "valid-secret",
            "AUTH_JWT_ALGORITHMS": "none",
        }
        authz = self._reload_authz(env)
        now = int(time.time())
        token = pyjwt.encode(
            {"exp": now + 60, "iat": now},
            "valid-secret",
            algorithm="HS256",
        )

        request = _build_request(token)
        with self.assertRaises(HTTPException) as ctx:
            authz.verify_jwt_from_request(request)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "JWT algorithms not configured")


if __name__ == "__main__":
    unittest.main()

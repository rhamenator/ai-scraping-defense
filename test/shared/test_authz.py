"""Tests for JWT authorization helpers."""

import importlib
import os
import tempfile
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

    def test_jwt_secret_file_is_supported(self):
        """Verify AUTH_JWT_SECRET_FILE is used when AUTH_JWT_SECRET is not set."""
        try:
            import jwt as pyjwt
        except Exception:
            self.skipTest("PyJWT not installed")

        now = int(time.time())
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("file-secret-value")
            secret_path = handle.name
        try:
            env = {
                "AUTH_JWT_SECRET_FILE": secret_path,
                "AUTH_JWT_ALGORITHMS": "HS256",
            }
            authz = self._reload_authz(env)
            token = pyjwt.encode(
                {"exp": now + 60, "iat": now, "roles": ["admin"]},
                "file-secret-value",
                algorithm="HS256",
            )

            request = _build_request(token)
            claims = authz.verify_jwt_from_request(request, required_roles=["admin"])
            self.assertEqual(claims.get("roles"), ["admin"])
        finally:
            try:
                os.unlink(secret_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

import pyotp
from fastapi import Depends
from fastapi.testclient import TestClient

from src.admin_ui import auth, sso
from src.shared.middleware import create_app
from src.shared.request_identity import RequestIdentity


class TestAdminUiSso(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

        @self.app.get("/whoami")
        def whoami(user: str = Depends(auth.require_auth)):
            return {"user": user}

        self.client = TestClient(self.app)

    @staticmethod
    def _totp_headers(secret: str) -> dict[str, str]:
        return {"X-2FA-Code": pyotp.TOTP(secret).now()}

    def test_oidc_sso_allows_access(self):
        totp_secret = pyotp.random_base32()
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_SSO_ENABLED": "true",
                "ADMIN_UI_SSO_MODE": "oidc",
                "ADMIN_UI_OIDC_JWT_SECRET": "secret",
                "ADMIN_UI_OIDC_ALGORITHMS": "HS256",
                "ADMIN_UI_OIDC_REQUIRED_ROLE": "admin",
                "ADMIN_UI_2FA_SECRET": totp_secret,
            },
            clear=False,
        ):
            with patch("src.admin_ui.auth.get_redis_connection", return_value=None):
                with patch("src.admin_ui.sso.jwt.decode") as decode:
                    decode.return_value = {
                        "preferred_username": "sso-user",
                        "roles": ["admin"],
                    }
                    resp = self.client.get(
                        "/whoami",
                        headers={
                            "Authorization": "Bearer token",
                            **self._totp_headers(totp_secret),
                        },
                    )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"], "sso-user")

    def test_saml_sso_allows_access(self):
        totp_secret = pyotp.random_base32()
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_SSO_ENABLED": "true",
                "ADMIN_UI_SSO_MODE": "saml",
                "ADMIN_UI_SAML_REQUIRED_GROUP": "admins",
                "ADMIN_UI_2FA_SECRET": totp_secret,
            },
            clear=False,
        ):
            with patch("src.admin_ui.auth.get_redis_connection", return_value=None):
                trusted = RequestIdentity(
                    client_ip="198.51.100.10",
                    peer_ip="127.0.0.1",
                    via_trusted_proxy=True,
                    via_trusted_cdn=False,
                )
                with patch(
                    "src.admin_ui.sso.resolve_request_identity",
                    return_value=trusted,
                ):
                    resp = self.client.get(
                        "/whoami",
                        headers={
                            "X-SSO-User": "saml-user",
                            "X-SSO-Groups": "admins, ops",
                            **self._totp_headers(totp_secret),
                        },
                    )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"], "saml-user")

    def test_saml_sso_rejects_headers_from_untrusted_peer(self):
        with patch.dict(
            os.environ,
            {"ADMIN_UI_SSO_ENABLED": "true", "ADMIN_UI_SSO_MODE": "saml"},
            clear=False,
        ):
            with patch("src.admin_ui.auth.get_redis_connection", return_value=None):
                response = self.client.get(
                    "/whoami", headers={"X-SSO-User": "forged-admin"}
                )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Untrusted SAML assertion source")

    def test_oidc_sso_requires_mfa_by_default(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_SSO_ENABLED": "true",
                "ADMIN_UI_SSO_MODE": "oidc",
                "ADMIN_UI_OIDC_JWT_SECRET": "secret",
                "ADMIN_UI_OIDC_ALGORITHMS": "HS256",
                "ADMIN_UI_OIDC_REQUIRED_ROLE": "admin",
            },
            clear=False,
        ):
            os.environ.pop("ADMIN_UI_2FA_SECRET", None)
            os.environ.pop("ADMIN_UI_2FA_SECRET_FILE", None)
            os.environ.pop("ADMIN_UI_SSO_MFA_REQUIRED", None)
            with patch("src.admin_ui.auth.get_redis_connection", return_value=None):
                with patch("src.admin_ui.sso.jwt.decode") as decode:
                    decode.return_value = {
                        "preferred_username": "sso-user",
                        "roles": ["admin"],
                    }
                    resp = self.client.get(
                        "/whoami", headers={"Authorization": "Bearer token"}
                    )

        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "MFA required")

    def test_oidc_sso_can_explicitly_disable_mfa_requirement(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_SSO_ENABLED": "true",
                "ADMIN_UI_SSO_MODE": "oidc",
                "ADMIN_UI_OIDC_JWT_SECRET": "secret",
                "ADMIN_UI_OIDC_ALGORITHMS": "HS256",
                "ADMIN_UI_OIDC_REQUIRED_ROLE": "admin",
                "ADMIN_UI_REQUIRE_MFA": "false",
            },
            clear=False,
        ):
            os.environ.pop("ADMIN_UI_2FA_SECRET", None)
            os.environ.pop("ADMIN_UI_2FA_SECRET_FILE", None)
            os.environ.pop("ADMIN_UI_SSO_MFA_REQUIRED", None)
            with patch("src.admin_ui.auth.get_redis_connection", return_value=None):
                with patch("src.admin_ui.sso.jwt.decode") as decode:
                    decode.return_value = {
                        "preferred_username": "sso-user",
                        "roles": ["admin"],
                    }
                    resp = self.client.get(
                        "/whoami", headers={"Authorization": "Bearer token"}
                    )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"], "sso-user")


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from fastapi import Depends
from fastapi.testclient import TestClient

from src.admin_ui import auth, sso
from src.shared.middleware import create_app


class TestAdminUiSso(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

        @self.app.get("/whoami")
        def whoami(user: str = Depends(auth.require_auth)):
            return {"user": user}

        self.client = TestClient(self.app)

    def test_oidc_sso_allows_access(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_SSO_ENABLED": "true",
                "ADMIN_UI_SSO_MODE": "oidc",
                "ADMIN_UI_OIDC_JWT_SECRET": "secret",
                "ADMIN_UI_OIDC_ALGORITHMS": "HS256",
                "ADMIN_UI_OIDC_REQUIRED_ROLE": "admin",
                "ADMIN_UI_2FA_SECRET": "JBSWY3DPEHPK3PXP",
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
                        "/whoami", headers={"Authorization": "Bearer token"}
                    )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"], "sso-user")

    def test_saml_sso_allows_access(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_UI_SSO_ENABLED": "true",
                "ADMIN_UI_SSO_MODE": "saml",
                "ADMIN_UI_SAML_REQUIRED_GROUP": "admins",
                "ADMIN_UI_2FA_SECRET": "JBSWY3DPEHPK3PXP",
            },
            clear=False,
        ):
            with patch("src.admin_ui.auth.get_redis_connection", return_value=None):
                resp = self.client.get(
                    "/whoami",
                    headers={
                        "X-SSO-User": "saml-user",
                        "X-SSO-Groups": "admins, ops",
                    },
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user"], "saml-user")


if __name__ == "__main__":
    unittest.main()

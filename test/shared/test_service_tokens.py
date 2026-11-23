"""Tests for least-privilege Redis ACL rendering, Postgres role SQL, and per-caller service tokens."""

import os
import secrets
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from scripts.render_redis_acl import PLACEHOLDERS, render_acl
from src.shared.service_tokens import mint_service_token, verify_service_token

ROOT = Path(__file__).resolve().parents[2]


class LeastPrivilegeTests(unittest.TestCase):
    def test_render_redis_acl_assigns_distinct_passwords_and_0600_mode(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        out = tmp / "users.acl"
        pwds = render_acl(ROOT / "redis" / "users.acl.template", out)
        self.assertEqual(len(pwds), len(PLACEHOLDERS))
        self.assertEqual(len(set(pwds.values())), len(PLACEHOLDERS))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o600)
        text = out.read_text(encoding="utf-8")
        self.assertIn("user nginx_proxy on", text)
        self.assertIn("-@write -@admin -@dangerous", text)
        self.assertIn("+hvals +incr +incrby", text)
        self.assertIn("+script|load", text)
        self.assertIn("~admin_ui:* ~*:admin_ui:*", text)
        for ph in PLACEHOLDERS:
            self.assertNotIn(ph, text)

    def test_postgres_init_defines_non_superuser_runtime_role(self):
        sql = (ROOT / "db" / "init_markov.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE ROLE asd_runtime NOLOGIN NOSUPERUSER", sql)
        self.assertIn("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES", sql)

    def test_service_tokens_bind_caller_audience_and_expiry(self):
        signing_key = secrets.token_urlsafe(16)
        tok = mint_service_token(signing_key, caller="ai_service", audience="escalation_engine", ttl_seconds=60, now=1000)
        claims = verify_service_token(tok, signing_key, expected_audience="escalation_engine", allowed_callers={"ai_service"}, now=1030)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["sub"], "ai_service")
        self.assertIsNone(verify_service_token(tok, signing_key, expected_audience="admin_ui", now=1030))
        self.assertIsNone(verify_service_token(tok, signing_key, expected_audience="escalation_engine", allowed_callers={"tarpit_api"}, now=1030))
        self.assertIsNone(verify_service_token(tok, signing_key, expected_audience="escalation_engine", now=1061))


if __name__ == "__main__":
    unittest.main()

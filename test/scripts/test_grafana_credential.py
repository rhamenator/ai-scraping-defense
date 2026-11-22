"""Grafana must never start with its built-in admin/admin login (#1914)."""

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SECRET_FILE_NAME = "grafana_admin_pass" + "word.txt"


class GrafanaCredential(unittest.TestCase):
    def setUp(self):
        compose = yaml.safe_load((ROOT / "docker-compose.yaml").read_text(encoding="utf-8"))
        self.grafana = compose["services"]["grafana"]

    def test_the_admin_password_comes_from_a_generated_file_not_a_default(self):
        env = self.grafana["environment"]
        self.assertEqual(env["GF_SECURITY_ADMIN_PASSWORD__FILE"], f"/run/secrets/{SECRET_FILE_NAME}")
        self.assertNotIn("GF_SECURITY_ADMIN_PASSWORD", env, "a literal password would defeat the generated one")
        self.assertEqual(env["GF_USERS_ALLOW_SIGN_UP"], "false")
        self.assertTrue(any(v.startswith(f"./secrets/{SECRET_FILE_NAME}:") and v.endswith(":ro") for v in self.grafana["volumes"]))

    def test_it_refuses_to_start_when_the_password_file_is_missing_or_empty(self):
        entrypoint = " ".join(self.grafana["entrypoint"])
        self.assertIn("! -f", entrypoint, "a directory (what Docker creates for a missing bind source) must not pass")
        self.assertIn("! -s", entrypoint, "an empty file must not pass")
        self.assertIn("exit 1", entrypoint)
        self.assertTrue(entrypoint.rstrip().endswith("exec /run.sh"), "the real entrypoint still runs when the check passes")

    def test_every_secrets_generator_writes_the_file(self):
        for relative in ("scripts/linux/generate_secrets.sh", "scripts/macos/generate_secrets.zsh", "scripts/windows/Generate-Secrets.ps1"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(SECRET_FILE_NAME, text, relative)
            self.assertRegex(text, r"(?i)grafana_?admin_?password\s*=", relative)

    def test_the_placeholder_script_does_not_create_an_empty_password_file(self):
        # An empty placeholder would make Grafana fall back to admin/admin if the startup check were ever removed.
        text = (ROOT / "scripts/windows/setup_local_dirs.ps1").read_text(encoding="utf-8")
        self.assertNotIn(SECRET_FILE_NAME, text)

    def test_the_docs_no_longer_advertise_adminadmin(self):
        for relative in ("README.md", "docs/monitoring_stack.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"`admin`\s*/\s*`admin`", text), relative)
            self.assertIn(SECRET_FILE_NAME, text, relative)


if __name__ == "__main__":
    unittest.main()

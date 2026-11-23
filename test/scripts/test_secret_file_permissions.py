"""Generated credentials must be owner-only from the first write and never printed by default (#1912)."""

import os
import re
import secrets
import shutil
import stat
import subprocess  # nosec B404 - runs the repository's own setup script in a temp tree
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import interactive_setup  # noqa: E402


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@unittest.skipIf(os.name == "nt", "POSIX permission bits")
class PythonSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        previous = os.umask(0o022)  # a typical permissive umask, the case that used to leak
        self.addCleanup(os.umask, previous)

    def test_private_text_is_created_owner_only(self):
        target = self.tmp / "private.txt"
        interactive_setup.write_private_text(target, "SECRET=value\n")
        self.assertEqual(mode(target), 0o600)
        self.assertEqual(target.read_text(encoding="utf-8"), "SECRET=value\n")

    def test_an_existing_world_readable_file_is_tightened(self):
        target = self.tmp / "existing.env"
        target.write_text("old")
        target.chmod(0o644)
        interactive_setup.write_private_text(target, "new")
        self.assertEqual(mode(target), 0o600)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_env_updates_and_progress_state_are_owner_only(self):
        env = self.tmp / ".env"
        interactive_setup.update_env_file(env, {"ADMIN_UI_PASSWORD_HASH": secrets.token_hex(8)})
        state = self.tmp / ".setup_state.json"
        interactive_setup.save_setup_state(state, {"A"})
        self.assertEqual(mode(env), 0o600)
        self.assertEqual(mode(state), 0o600)

    def test_the_secrets_database_is_owner_only_before_any_secret_is_stored(self):
        with patch("builtins.input", return_value="y"):
            interactive_setup.store_secrets(self.tmp, {"POSTGRES_PASSWORD": secrets.token_hex(8)})
        self.assertEqual(mode(self.tmp / "secrets" / "local_secrets.db"), 0o600)

    def test_create_private_file_tightens_an_existing_database(self):
        target = self.tmp / "db"
        target.write_bytes(b"")
        target.chmod(0o666)
        interactive_setup.create_private_file(target)
        self.assertEqual(mode(target), 0o600)


@unittest.skipIf(os.name == "nt" or shutil.which("bash") is None or shutil.which("openssl") is None, "needs bash and openssl")
class LinuxScriptTests(unittest.TestCase):
    """Run the real script in a temp tree, with a permissive umask and a stub htpasswd."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "scripts" / "linux").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "linux" / "generate_secrets.sh", self.tmp / "scripts" / "linux")
        (self.tmp / "nginx").mkdir()
        shutil.copy(ROOT / "sample.env", self.tmp / "sample.env")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "htpasswd"
        stub.write_text('#!/bin/sh\necho "$4:\\$2y\\$12\\$stubstubstubstubstubstuOstubstubstubstubstubstubstubstubstu"\n')
        stub.chmod(0o755)

    def run_script(self, *args):
        script = self.tmp / "scripts" / "linux" / "generate_secrets.sh"
        env = {**os.environ, "PATH": f"{self.tmp / 'bin'}:{os.environ['PATH']}"}
        # A static command string; the script path and arguments are passed positionally, never interpolated.
        return subprocess.run(  # nosec B603 B607
            ["bash", "-c", 'umask 022; exec bash "$0" "$@"', str(script), *args],
            cwd=self.tmp, env=env, capture_output=True, text=True, timeout=120, check=False,
        )

    def test_every_secret_file_is_owner_only_except_the_htpasswd_hash(self):
        result = self.run_script("--update-env")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mode(self.tmp / "kubernetes" / "secrets.yaml"), 0o600)
        self.assertEqual(mode(self.tmp / ".env"), 0o600)
        # nginx workers read the htpasswd file as another user; it holds a bcrypt hash, not the password
        self.assertEqual(mode(self.tmp / "nginx" / ".htpasswd"), 0o644)
        # The containers read staged copies (the secrets_init service), so the host files and directory stay private (#1912).
        self.assertEqual(mode(self.tmp / "secrets"), 0o700)
        self.assertEqual(mode(self.tmp / "secrets" / "pg_password.txt"), 0o600)
        self.assertEqual(mode(self.tmp / "secrets" / "redis_password.txt"), 0o600)

    def test_generated_values_are_not_printed(self):
        result = self.run_script("--update-env")
        env_text = (self.tmp / ".env").read_text(encoding="utf-8")
        for key in ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "AUTH_JWT_SECRET"):
            match = re.search(rf"^{key}=(\S+)$", env_text, re.M)
            self.assertIsNotNone(match, key)
            self.assertNotIn(match.group(1).strip("'\""), result.stdout + result.stderr, key)


class ScriptSourceGuards(unittest.TestCase):
    def test_both_scripts_set_a_restrictive_umask_before_writing_anything(self):
        for relative in ("scripts/linux/generate_secrets.sh", "scripts/macos/generate_secrets.zsh"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("umask 077", text, relative)
            self.assertLess(text.index("umask 077"), text.index("mkdir -p"), relative)

    def test_the_macos_script_prints_credentials_only_on_request(self):
        text = (ROOT / "scripts/macos/generate_secrets.zsh").read_text(encoding="utf-8")
        self.assertIn("--print-secrets", text)
        self.assertIn('if [ "$print_secrets" = true ]; then', text)
        guarded = text.split('if [ "$print_secrets" = true ]; then', 1)[1].split("\nelse\n", 1)[0]
        self.assertIn('echo "  Password: $NGINX_PASSWORD"', guarded)
        outside = text.replace(guarded, "")
        printing = [line for line in outside.splitlines() if re.match(r"\s*echo\b", line) and " > " not in line]  # not file writes
        for secret in ("NGINX_PASSWORD", "POSTGRES_PASSWORD", "REDIS_PASSWORD", "SYSTEM_SEED", "API_KEY"):
            offenders = [line for line in printing if f"${secret}" in line or f"${{{secret}}}" in line]
            self.assertEqual(offenders, [], f"{secret} is echoed outside the --print-secrets branch")

    def test_the_python_setup_never_writes_secret_files_with_write_text(self):
        source = (ROOT / "scripts" / "interactive_setup.py").read_text(encoding="utf-8")
        self.assertNotIn("env_file.write_text(", source)
        self.assertNotIn("path.write_text(", source)



class ComposeStagesSecrets(unittest.TestCase):
    """The compose file must not bind-mount the private host directory into the runtime containers (#1912)."""

    def setUp(self):
        import yaml

        self.compose = yaml.safe_load((ROOT / "docker-compose.yaml").read_text(encoding="utf-8"))

    def test_no_runtime_service_mounts_the_host_secrets_directory(self):
        for name, service in self.compose["services"].items():
            for volume in service.get("volumes", []):
                if name == "secrets_init":
                    continue
                self.assertFalse(str(volume).startswith("./secrets:"), f"{name} mounts ./secrets directly")

    def test_every_service_that_reads_secrets_waits_for_the_staging_job(self):
        readers = [n for n, s in self.compose["services"].items() if any(str(v).startswith("runtime_secrets:") for v in s.get("volumes", []))]
        self.assertIn("postgres", readers)
        self.assertIn("redis", readers)
        for name in readers:
            if name == "secrets_init":
                continue
            condition = self.compose["services"][name]["depends_on"]["secrets_init"]["condition"]
            self.assertEqual(condition, "service_completed_successfully", name)

    def test_the_staging_job_is_minimal(self):
        job = self.compose["services"]["secrets_init"]
        self.assertEqual(job["network_mode"], "none")
        self.assertEqual(job["cap_drop"], ["ALL"])
        self.assertEqual(sorted(job["cap_add"]), ["CHOWN", "DAC_OVERRIDE", "FOWNER"])
        self.assertTrue(job["read_only"])
        self.assertIn("./secrets:/staging/source:ro", job["volumes"])


if __name__ == "__main__":
    unittest.main()

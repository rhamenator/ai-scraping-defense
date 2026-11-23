"""Tests for encrypted secrets bundle (scripts/secrets_bundle.py)."""

import json
import os
import secrets
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from cryptography.exceptions import InvalidTag

from scripts import secrets_bundle


class SecretsBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.secrets_dir = self.tmp / "secrets"
        self.secrets_dir.mkdir(mode=0o700)
        self.bundle = self.secrets_dir / "secrets.enc"
        (self.secrets_dir / "pg_password.txt").write_text("pg-secret-val", encoding="utf-8")
        (self.secrets_dir / "redis_password.txt").write_text("redis-secret-val", encoding="utf-8")

    def test_seal_shred_and_unseal_round_trip(self):
        passphrase = secrets.token_urlsafe(16)
        sealed = secrets_bundle.seal_secrets(self.secrets_dir, self.bundle, passphrase, shred_plaintext=True)
        self.assertEqual(sealed, ["pg_password.txt", "redis_password.txt"])
        self.assertFalse((self.secrets_dir / "pg_password.txt").exists())
        self.assertFalse((self.secrets_dir / "redis_password.txt").exists())
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(self.bundle).st_mode), 0o600)

        out_dir = self.tmp / "tmpfs_target"
        unsealed = secrets_bundle.unseal_secrets(self.bundle, out_dir, passphrase)
        self.assertEqual(unsealed, ["pg_password.txt", "redis_password.txt"])
        self.assertEqual((out_dir / "pg_password.txt").read_text(encoding="utf-8"), "pg-secret-val")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(out_dir).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(out_dir / "pg_password.txt").st_mode), 0o600)

    def test_wrong_passphrase_or_tampered_bundle_fails(self):
        passphrase = secrets.token_urlsafe(16)
        secrets_bundle.seal_secrets(self.secrets_dir, self.bundle, passphrase, shred_plaintext=False)

        with self.assertRaises(InvalidTag):
            secrets_bundle.unseal_secrets(self.bundle, self.tmp / "out", "wrong-passphrase")

        data = json.loads(self.bundle.read_text(encoding="utf-8"))
        data["ciphertext"] = "AAAA" + data["ciphertext"][4:]
        self.bundle.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises((InvalidTag, ValueError)):
            secrets_bundle.unseal_secrets(self.bundle, self.tmp / "out2", passphrase)


if __name__ == "__main__":
    unittest.main()

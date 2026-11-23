#!/usr/bin/env python3
"""Seal and unseal persistent host secret files into an AES-256-GCM encrypted bundle.

Allows operators to keep persistent secrets encrypted at rest in ``secrets/secrets.enc``
and unseal them into a ``tmpfs`` mount (or ``0600`` staging directory) only at startup.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

BUNDLE_VERSION = 1
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
AAD = b"asd-secrets-bundle-v1"


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_BYTES, n=2**15, r=8, p=1)
    return kdf.derive(passphrase.encode("utf-8"))


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.chmod(path, 0o600)
        os.write(fd, data)
    finally:
        os.close(fd)


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)  # nosec B103 nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions - owner-only 0700


def seal_secrets(secrets_dir: Path, bundle_path: Path, passphrase: str, *, shred_plaintext: bool = False) -> list[str]:
    """Encrypt all ``*.txt`` files in ``secrets_dir`` into ``bundle_path`` (mode 0600)."""
    if not passphrase:
        raise ValueError("Passphrase must not be empty")
    entries: dict[str, str] = {}
    for item in sorted(secrets_dir.glob("*.txt")):
        if item.is_file():
            entries[item.name] = item.read_text(encoding="utf-8")
    if not entries:
        raise ValueError(f"No *.txt secret files found in {secrets_dir}")

    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    key = _derive_key(passphrase, salt)
    plaintext = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, AAD)

    envelope = {
        "version": BUNDLE_VERSION,
        "kdf": "scrypt",
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    _ensure_private_dir(bundle_path.parent)
    _write_private(bundle_path, json.dumps(envelope, indent=2).encode("utf-8"))

    if shred_plaintext:
        for name in entries:
            target = secrets_dir / name
            if target.exists():
                target.unlink()
    return sorted(entries)


def unseal_secrets(bundle_path: Path, target_dir: Path, passphrase: str) -> list[str]:
    """Decrypt ``bundle_path`` and write each secret file into ``target_dir`` (mode 0600)."""
    envelope = json.loads(bundle_path.read_text(encoding="utf-8"))
    if envelope.get("version") != BUNDLE_VERSION:
        raise ValueError("Unsupported secrets bundle version")
    salt = base64.b64decode(envelope["salt"])
    nonce = base64.b64decode(envelope["nonce"])
    ciphertext = base64.b64decode(envelope["ciphertext"])
    key = _derive_key(passphrase, salt)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD)
    entries = json.loads(plaintext.decode("utf-8"))

    _ensure_private_dir(target_dir)
    written: list[str] = []
    for name, value in entries.items():
        if "/" in name or "\\" in name or not name.endswith(".txt"):
            raise ValueError(f"Invalid secret filename in bundle: {name}")
        _write_private(target_dir / name, str(value).encode("utf-8"))
        written.append(name)
    return sorted(written)


def _read_passphrase(key_file: str | None) -> str:
    if key_file:
        return Path(key_file).read_text(encoding="utf-8").rstrip("\r\n")
    return getpass.getpass("Secrets bundle passphrase: ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage encrypted secrets bundle (secrets.enc).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd_name in ("seal", "unseal"):
        p = sub.add_parser(cmd_name)
        p.add_argument("--secrets-dir", type=Path, default=Path("secrets"))
        p.add_argument("--bundle", type=Path, default=Path("secrets/secrets.enc"))
        p.add_argument("--key-file", default=os.getenv("ASD_SECRETS_KEY_FILE"))
        if cmd_name == "seal":
            p.add_argument("--shred-plaintext", action="store_true")
    args = parser.parse_args(argv)
    passphrase = _read_passphrase(args.key_file)
    if args.cmd == "seal":
        names = seal_secrets(args.secrets_dir, args.bundle, passphrase, shred_plaintext=args.shred_plaintext)
        print(f"Sealed {len(names)} secret(s).")
        return 0
    names = unseal_secrets(args.bundle, args.secrets_dir, passphrase)
    print(f"Unsealed {len(names)} secret(s).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

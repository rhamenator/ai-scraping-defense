#!/usr/bin/env python3
"""Generate a TOTP secret and QR code for the Admin UI."""
import sys
from pathlib import Path

import pyotp
import qrcode


def main() -> None:
    secret = pyotp.random_base32()
    issuer = "AI Scraping Defense"
    uri = pyotp.TOTP(secret).provisioning_uri(
        name="admin@example.com", issuer_name=issuer
    )
    img = qrcode.make(uri)
    out_file = Path("admin-2fa.png")
    img.save(out_file)
    print(f"TOTP secret: {secret}")
    print(f"QR code written to {out_file.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - simple script
        print(f"Error generating TOTP secret: {exc}", file=sys.stderr)
        sys.exit(1)

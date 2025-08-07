#!/usr/bin/env python3
"""Generate a TOTP secret and QR code for the Admin UI."""
import argparse
import sys
from pathlib import Path
import os

import pyotp
import qrcode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a TOTP secret and QR code for the Admin UI."
    )
    parser.add_argument(
        "--show-secret",
        action="store_true",
        help="Print the TOTP secret to stdout (use with caution).",
    )
    args = parser.parse_args()

    secret = pyotp.random_base32()
    issuer = "AI Scraping Defense"
    uri = pyotp.TOTP(secret).provisioning_uri(
        name="admin@example.com", issuer_name=issuer
    )
    img = qrcode.make(uri)
    out_file = Path("admin-2fa.png")
    img.save(out_file)
    if args.show_secret:
        confirm = input(
            "Are you sure you want to display the TOTP secret? "
            "Type 'YES' to confirm: "
        )
        if confirm == "YES":
            secret_file = Path("admin-2fa.secret")
            with open(secret_file, "w") as f:
                f.write(secret)
            os.chmod(secret_file, 0o600)
            print(f"TOTP secret written to {secret_file.resolve()} (permissions: 600)")
        else:
            print("TOTP secret not displayed.")
    else:
        print("TOTP secret not displayed.")
    print(f"QR code written to {out_file.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - simple script
        print(f"Error generating TOTP secret: {exc}", file=sys.stderr)
        sys.exit(1)

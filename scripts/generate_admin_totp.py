#!/usr/bin/env python3
"""Generate a TOTP secret and QR code for the Admin UI."""
import argparse
import os
import sys
from pathlib import Path

import pyotp
import qrcode


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a TOTP secret and QR code for the Admin UI."
    )
    parser.add_argument(
        "--show-secret",
        action="store_true",
        help="Print the TOTP secret to stdout (not written to disk).",
    )
    parser.add_argument(
        "--admin-email",
        type=str,
        default=None,
        help="Admin email/username for TOTP provisioning (can also set ADMIN_EMAIL env var).",
    )
    args = parser.parse_args()

    admin_email = (
        args.admin_email or os.environ.get("ADMIN_EMAIL") or "admin@example.com"
    )

    secret = pyotp.random_base32()
    issuer = "AI Scraping Defense"
    uri = pyotp.TOTP(secret).provisioning_uri(name=admin_email, issuer_name=issuer)
    img = qrcode.make(uri)
    out_file = Path("admin-2fa.png")
    img.save(out_file)
    if args.show_secret:
        confirm = input(  # nosec B322 - interactive confirmation
            "Are you sure you want to display the TOTP secret? "
            "Type 'YES' to confirm: "
        )
        if confirm == "YES":
            print("TOTP secret (store securely; not written to disk):")
            # codeql[py/clear-text-logging-sensitive-data]: explicit user request.
            print(secret)
        else:
            print("TOTP secret not displayed.")
    else:
        print("TOTP secret not displayed.")

    print(f"QR code written to {out_file.resolve()}")
    print("Note: The QR code contains the secret. Store the file securely.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - simple script
        print(f"Error generating TOTP secret: {exc}", file=sys.stderr)
        sys.exit(1)

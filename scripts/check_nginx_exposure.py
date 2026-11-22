"""Reject vulnerable OpenResty features until a patched NGINX core is shipped."""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DISALLOWED = re.compile(
    r"(?:^|\s)(?:http2\s+on|http3\b|quic\b|mirror\b|ssi\b|mail\s*\{)"
    r"|^\s*listen\b[^;]*\bhttp2\b"
    r"|^\s*ssl_protocols\b[^;]*\bTLSv1\.3\b",
    re.IGNORECASE,
)


def main() -> int:
    violations = []
    for path in sorted((*ROOT.glob("nginx/**/*.conf"), *ROOT.glob("nginx/*.sh"))):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            active = line.split("#", 1)[0]
            if DISALLOWED.search(active):
                violations.append(f"{path.relative_to(ROOT)}:{number}")
    if violations:
        print("Unsafe OpenResty feature in: " + ", ".join(violations), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

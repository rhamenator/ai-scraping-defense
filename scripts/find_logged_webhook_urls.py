#!/usr/bin/env python3
"""Find webhook URLs that earlier releases may have written to logs (#1906), without printing them.

Slack, Teams and Discord webhook URLs carry their credential in the path. Releases before the redaction fix logged the
configured URL and HTTP error text that repeated it. This scans log files (and anything else you point it at) for those
URLs and for the exact webhook URLs configured in the environment or a .env file, and reports where, by file and line,
with a short fingerprint so repeats are recognisable. It never prints a URL. Nothing is rotated or changed.

    python3 scripts/find_logged_webhook_urls.py /var/log/ai-scraping-defense logs/ ~/old-bug-report.txt
    python3 scripts/find_logged_webhook_urls.py --env-file .env logs/

Exit status: 0 nothing found, 1 something found (rotate those webhooks if the files left your control), 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

KNOWN_PATTERNS = {
    "slack": re.compile(r"https://hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9/_\-]+"),
    "discord": re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_\-]+"),
    "teams": re.compile(r"https://[A-Za-z0-9.\-]*(?:webhook\.office|outlook\.office(?:365)?)\.com/[A-Za-z0-9/_@.\-]*webhook[A-Za-z0-9/_@.\-]*"),
}
# Any variable that holds a webhook URL (ALERT_SLACK_WEBHOOK_URL, ALERT_GENERIC_WEBHOOK_URL, ESCALATION_WEBHOOK_URL,
# WEBHOOK_URL, ...), or names a file that does (the same name plus _FILE, the usual secret-file convention).
CONFIGURED_KEYS = re.compile(r"^[A-Z0-9_]*WEBHOOK_URL$")
CONFIGURED_FILE_KEYS = re.compile(r"^[A-Z0-9_]*WEBHOOK_URL_FILE$")
MAX_FILE_BYTES = 200 * 1024 * 1024  # skip anything larger than this rather than reading it all


def fingerprint(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]


def _is_configured_url(key: str, value: str) -> bool:
    return bool(CONFIGURED_KEYS.match(key.strip())) and value.startswith("http")


def _url_from_file(key: str, value: str) -> str | None:
    """The URL stored in the file a *_WEBHOOK_URL_FILE variable points at, if it can be read."""
    if not CONFIGURED_FILE_KEYS.match(key.strip()) or not value:
        return None
    try:
        text = Path(value).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text if text.startswith("http") else None


def _pairs_from_env_file(env_file: Path | None):
    if not env_file or not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        key, _, value = line.partition("=")
        yield key.strip(), value.strip().strip("'\"")


def configured_urls(env_file: Path | None, environ: dict[str, str]) -> tuple[set[str], int]:
    """The webhook URLs configured in the environment and the .env file, and how many variables were recognised."""
    urls: set[str] = set()
    recognised = 0
    for key, value in [*environ.items(), *_pairs_from_env_file(env_file)]:
        found = value if _is_configured_url(key, value) else _url_from_file(key, value)
        if CONFIGURED_KEYS.match(key.strip()) or CONFIGURED_FILE_KEYS.match(key.strip()):
            recognised += 1
        if found:
            urls.add(found)
    return urls, recognised


def iter_files(paths: list[Path]):
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and not child.is_symlink():
                    yield child
        elif path.is_file():
            yield path


def _line_findings(line: str, number: int, configured: set[str]) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for kind, pattern in KNOWN_PATTERNS.items():
        for match in pattern.finditer(line):
            seen.add(match.group(0))
            findings.append((number, kind, fingerprint(match.group(0))))
    findings.extend((number, "configured", fingerprint(url)) for url in configured if url in line and url not in seen)
    return findings


def scan_file(path: Path, configured: set[str]) -> list[tuple[int, str, str]]:
    """(line number, kind, fingerprint) for every webhook URL on every line; the URL itself is never returned."""
    findings: list[tuple[int, str, str]] = []
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return findings
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                findings.extend(_line_findings(line, number, configured))
    except OSError:
        pass
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="+", type=Path, help="log files or directories to scan")
    parser.add_argument("--env-file", type=Path, help="a .env file whose webhook URLs should also be searched for")
    arguments = parser.parse_args(argv)
    configured, recognised = configured_urls(arguments.env_file, dict(os.environ))
    total = 0
    files = 0
    for path in iter_files(arguments.paths):
        findings = scan_file(path, configured)
        files += 1
        for number, kind, print_id in findings:
            total += 1
            print(f"{path}:{number}: {kind} webhook URL (id={print_id})")
    print(f"Scanned {files} file(s); {total} webhook URL occurrence(s) found.", file=sys.stderr)
    print(
        f"Checked for: Slack, Teams and Discord URL shapes, and {len(configured)} configured URL(s) from "
        f"{recognised} recognised variable(s) (names ending in WEBHOOK_URL or WEBHOOK_URL_FILE). A webhook of another "
        "kind, held in a variable with a different name, is not looked for; add it to your .env or pass it explicitly.",
        file=sys.stderr,
    )
    if total:
        print(
            "If these files left your control (log shipping, bug reports, CI artifacts, shared drives), regenerate the\n"
            "webhook in Slack, Teams or Discord and update the secret. Occurrences with the same id are the same URL.",
            file=sys.stderr,
        )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())

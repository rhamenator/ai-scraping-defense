"""Bounded, integrity-checked downloads and rule validation for the WAF rules fetcher (#1907)."""

import hashlib
import hmac
import logging
import re
from typing import Optional

import requests

from src.shared.ssrf_protection import SSRFProtectionError, validate_url

logger = logging.getLogger(__name__)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 64 * 1024


class RulesDownloadError(Exception):
    """The download or its contents were refused; nothing was installed."""


def check_source(url: str, allowed_domains: Optional[list[str]]) -> None:
    """HTTPS only, public addresses only, and the exact host allowlist when one is configured."""
    try:
        validate_url(
            url,
            allowed_domains=allowed_domains if allowed_domains else None,
            require_https=True,
            block_private_ips=True,
            resolve_dns=True,
        )
    except SSRFProtectionError as exc:
        raise RulesDownloadError(f"source refused: {exc}") from exc


def _open_stream(url: str, timeout: float):
    try:
        return requests.get(url, timeout=timeout, allow_redirects=False, stream=True)
    except requests.exceptions.RequestException as exc:
        raise RulesDownloadError(f"download failed: {exc}") from exc


def _check_response(response, max_bytes: int) -> None:
    """Refuse redirects, error statuses and bodies that declare themselves too large."""
    status = getattr(response, "status_code", 200)
    if isinstance(status, int) and 300 <= status < 400:
        raise RulesDownloadError(
            f"redirects are not followed (HTTP {status}); use the final download URL"
        )
    try:
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RulesDownloadError(f"download failed: {exc}") from exc
    declared = getattr(response, "headers", {}).get("Content-Length")
    if declared and str(declared).isdigit() and int(declared) > max_bytes:
        raise RulesDownloadError(f"download is {declared} bytes, over the {max_bytes} byte limit")


def _read_limited(response, max_bytes: int) -> bytes:
    data = bytearray()
    for chunk in response.iter_content(chunk_size=_CHUNK):
        data.extend(chunk)
        if len(data) > max_bytes:
            raise RulesDownloadError(f"download exceeded the {max_bytes} byte limit")
    return bytes(data)


def download_bounded(url: str, *, timeout: float, max_bytes: int) -> bytes:
    """Fetch ``url`` without following redirects and without reading more than ``max_bytes``."""
    response = _open_stream(url, timeout)
    try:
        _check_response(response, max_bytes)
        return _read_limited(response, max_bytes)
    except requests.exceptions.RequestException as exc:
        raise RulesDownloadError(f"download failed: {exc}") from exc
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def verify_digest(data: bytes, expected: str, *, require: bool, what: str) -> None:
    """Check ``data`` against a pinned SHA-256; refuse a malformed pin, and an absent one when ``require`` is set."""
    expected = (expected or "").strip().lower()
    if not expected:
        if require:
            raise RulesDownloadError(f"{what}: no SHA-256 digest is configured and RULES_REQUIRE_DIGEST is true")
        logger.warning("%s is not pinned to a SHA-256 digest; set it to accept only the reviewed download.", what)
        return
    if not _SHA256_HEX.match(expected):
        raise RulesDownloadError(f"{what}: the configured digest is not 64 hexadecimal characters")
    actual = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise RulesDownloadError(f"{what}: SHA-256 mismatch (expected {expected[:12]}..., got {actual[:12]}...)")


# Directives that run code, read other files, fetch more rules or redirect where the engine writes. Rules fetched from
# the network may not use them; an operator who needs one edits the rules by hand.
_FORBIDDEN_DIRECTIVES = {
    "include", "includeoptional", "secrulescript", "secremoterules", "secremoterulesfailaction",
    "secauditlog", "secauditlogstoragedir", "secdebuglog", "secdatadir", "sectmpdir", "secuploaddir",
    "secuploadkeepfiles", "secconnengine", "secrulereload",
}
_FORBIDDEN_FRAGMENTS = ("@inspectfile", "exec:")


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Join backslash-continued lines; each item is (first line number, joined text)."""
    lines: list[tuple[int, str]] = []
    buffer, start = "", 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not buffer:
            start = number
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        lines.append((start, (buffer + line).strip()))
        buffer = ""
    if buffer:
        lines.append((start, buffer.strip()))
    return lines


def _line_problems(number: int, line: str) -> tuple[list[str], bool]:
    """Problems with one logical line, and whether it is a ModSecurity directive."""
    name = line.split(None, 1)[0].lower()
    problems: list[str] = []
    is_directive = False
    if name in _FORBIDDEN_DIRECTIVES:
        problems.append(f"line {number}: directive {name!r} is not allowed in downloaded rules")
    elif name.startswith("sec"):
        is_directive = True
    else:
        problems.append(f"line {number}: not a ModSecurity directive")
    lowered = line.lower()
    problems += [
        f"line {number}: {fragment!r} is not allowed in downloaded rules"
        for fragment in _FORBIDDEN_FRAGMENTS
        if fragment in lowered
    ]
    return problems, is_directive


def validate_rules_text(text: str) -> list[str]:
    """Return the problems found in a ModSecurity rules file; an empty list means it may be installed."""
    if "\x00" in text:
        return ["contains a NUL byte"]
    problems: list[str] = []
    directives = 0
    for number, line in _logical_lines(text):
        if not line or line.startswith("#"):
            continue
        found, is_directive = _line_problems(number, line)
        problems += found
        directives += is_directive
        if len(problems) >= 10:
            return problems[:10] + ["further problems not listed"]
    if not problems and directives == 0:
        problems.append("no rules found")
    return problems

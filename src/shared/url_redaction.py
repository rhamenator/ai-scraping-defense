"""Keep credential-bearing URLs out of logs (#1906).

Webhook URLs commonly carry their secret in the path or query (Slack, Teams, Discord) or as user info. These helpers log
only the origin plus a short stable fingerprint, and scrub URLs that appear inside messages and exception text, which
is where libraries such as httpx put them (``Client error '404' for url 'https://...'``).
"""

import hashlib
import logging
import re
from urllib.parse import urlsplit

# Match as much as could belong to the URL (brackets and parentheses are valid inside one: IPv6 hosts, query values);
# over-matching is safe because the whole match is replaced, so sentence punctuation is trimmed afterwards.
_URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?"
_BRACKETS = {")": "(", "]": "[", "}": "{"}


def _origin(parts) -> str:
    host = parts.hostname or ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}" if parts.scheme and host else "<invalid-url>"


def safe_endpoint_for_logs(url: str) -> str:
    """A non-sensitive identifier for an endpoint: its origin and a short fingerprint of the full URL."""
    try:
        origin = _origin(urlsplit(url))
    except ValueError:
        origin = "<invalid-url>"
    fingerprint = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{origin} (id={fingerprint})"


def _carries_secret_material(parts) -> bool:
    return bool(
        parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
    )


def _split_trailing(candidate: str) -> tuple[str, str]:
    """Split sentence punctuation, and unbalanced closing brackets, off the end of a URL candidate."""
    trailing = ""
    while candidate:
        last = candidate[-1]
        if last in _TRAILING_PUNCTUATION:
            pass
        elif last in _BRACKETS and candidate.count(last) > candidate.count(_BRACKETS[last]):
            pass
        else:
            break
        trailing = last + trailing
        candidate = candidate[:-1]
    return candidate, trailing


def redact_urls(text: str) -> str:
    """Replace every URL in ``text`` that has user info, a path, a query or a fragment with its safe form.

    A bare origin (scheme, host, port) is not secret and is left alone, which keeps ordinary diagnostics readable.
    """
    if not text or "://" not in text:
        return text

    def replace(match: re.Match) -> str:
        url, trailing = _split_trailing(match.group(0))
        try:
            parts = urlsplit(url)
            secret = _carries_secret_material(parts)
        except ValueError:
            return "<invalid-url>" + trailing
        return (safe_endpoint_for_logs(url) if secret else url) + trailing

    return _URL_PATTERN.sub(replace, text)


class UrlRedactionFilter(logging.Filter):
    """Defense in depth: scrub URLs from a record's message and exception text, whatever code produced them."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            # A malformed format string: keep the text and arguments, scrubbed, instead of failing downstream.
            message = f"{record.msg} {record.args!r}"
        record.msg = redact_urls(message)
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_urls(record.exc_text)
        return True


def install_url_redaction(logger: logging.Logger) -> None:
    """Attach the filter once to ``logger``."""
    if not any(isinstance(item, UrlRedactionFilter) for item in logger.filters):
        logger.addFilter(UrlRedactionFilter())

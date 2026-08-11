#!/usr/bin/env python3
"""Extract IP addresses for known AI crawlers from Caddy JSON access logs."""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from collections import Counter
from pathlib import Path
from typing import IO, Any, Iterable

AI_CRAWLER_TOKENS = (
    "amazonbot",
    "anthropic-ai",
    "applebot-extended",
    "bytespider",
    "chatgpt-user",
    "claude-searchbot",
    "claude-user",
    "claudebot",
    "cohere-ai",
    "diffbot",
    "facebookbot",
    "google-extended",
    "googleother",
    "gptbot",
    "imagesiftbot",
    "meta-externalagent",
    "meta-externalfetcher",
    "oai-searchbot",
    "omgili",
    "perplexity-user",
    "perplexitybot",
    "petalbot",
    "timpibot",
    "youbot",
)


def _first_header(headers: dict[str, Any], name: str) -> str:
    for key, value in headers.items():
        if key.lower() != name.lower():
            continue
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return str(value)
    return ""


def _normalize_ip(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1 : candidate.index("]")]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _request_data(record: dict[str, Any]) -> tuple[str | None, str]:
    request = record.get("request")
    if not isinstance(request, dict):
        request = {}
    headers = request.get("headers")
    if not isinstance(headers, dict):
        headers = {}
    user_agent = _first_header(headers, "User-Agent")
    if not user_agent:
        user_agent = str(record.get("user_agent") or "")
    client_ip = _normalize_ip(request.get("client_ip"))
    if client_ip is None:
        client_ip = _normalize_ip(request.get("remote_ip"))
    if client_ip is None:
        client_ip = _normalize_ip(record.get("remote_ip"))
    return client_ip, user_agent


def is_ai_crawler(user_agent: str) -> bool:
    """Return whether a User-Agent identifies a known AI crawler."""
    lowered = user_agent.casefold()
    return any(token in lowered for token in AI_CRAWLER_TOKENS)


def extract_counts(lines: Iterable[str], source: str = "<stdin>") -> Counter[str]:
    """Parse newline-delimited Caddy JSON records and count matching IPs."""
    matches: Counter[str] = Counter()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"{source}:{line_number}: invalid JSON: {exc.msg}", file=sys.stderr)
            continue
        if not isinstance(record, dict):
            continue
        client_ip, user_agent = _request_data(record)
        if client_ip is not None and is_ai_crawler(user_agent):
            matches[client_ip] += 1
    return matches


def _open_input(path: str) -> tuple[IO[str], str]:
    if path == "-":
        return sys.stdin, "<stdin>"
    source = Path(path)
    return source.open(encoding="utf-8"), str(source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract unique AI crawler IPs from a Caddy JSON access log."
    )
    parser.add_argument("log", nargs="?", default="-", help="log path, or - for stdin")
    parser.add_argument(
        "--counts", action="store_true", help="append the matching request count"
    )
    args = parser.parse_args(argv)

    stream, source = _open_input(args.log)
    try:
        counts = extract_counts(stream, source)
    finally:
        if stream is not sys.stdin:
            stream.close()

    for address in sorted(counts, key=ipaddress.ip_address):
        suffix = f"\t{counts[address]}" if args.counts else ""
        print(f"{address}{suffix}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

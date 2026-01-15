#!/usr/bin/env python3
"""Lightweight dependency integrity checks for CI."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_TXT = PROJECT_ROOT / "requirements.txt"
REQUIREMENTS_LOCK = PROJECT_ROOT / "requirements.lock"


def _fail(message: str) -> int:
    print(f"[dependency-verify] ERROR: {message}", file=sys.stderr)
    return 1


def _warn(message: str) -> None:
    print(f"[dependency-verify] WARNING: {message}", file=sys.stderr)


def _read_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _parse_requirement_names(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        if line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(match.group(1).lower().replace("-", "_"))
    return names


def _parse_lock_names(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        if line.startswith("#") or line.startswith(" "):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)==", line)
        if match:
            names.add(match.group(1).lower().replace("-", "_"))
    return names


def _check_insecure_indexes(lines: list[str], filename: str) -> None:
    for line in lines:
        if line.startswith("--index-url") and "http://" in line:
            _warn(f"{filename} uses insecure index URL: {line}")
        if line.startswith("--extra-index-url") and "http://" in line:
            _warn(f"{filename} uses insecure extra index URL: {line}")
        if line.startswith("--trusted-host"):
            _warn(f"{filename} uses trusted-host override: {line}")


def main() -> int:
    if not REQUIREMENTS_TXT.exists():
        return _fail("requirements.txt is missing")
    if not REQUIREMENTS_LOCK.exists():
        return _fail("requirements.lock is missing")

    req_lines = _read_lines(REQUIREMENTS_TXT)
    lock_lines = _read_lines(REQUIREMENTS_LOCK)

    _check_insecure_indexes(req_lines, "requirements.txt")
    _check_insecure_indexes(lock_lines, "requirements.lock")

    req_names = _parse_requirement_names(req_lines)
    lock_names = _parse_lock_names(lock_lines)

    missing = req_names - lock_names
    if missing:
        _warn(
            "requirements.lock is missing pinned versions for: "
            + ", ".join(sorted(missing))
        )

    print(
        f"[dependency-verify] requirements.txt entries: {len(req_names)}; "
        f"requirements.lock entries: {len(lock_names)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

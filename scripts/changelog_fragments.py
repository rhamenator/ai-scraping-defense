#!/usr/bin/env python3
"""Check and assemble changelog fragments from ``changelog.d/`` into ``CHANGELOG.md``.

See ``changelog.d/README.md``. Fragments are named ``<id>.<category>.md``; ``assemble`` appends each under the
matching ``### <Category>`` heading of ``## [Unreleased]`` in file-name order.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ("security", "added", "changed", "fixed", "deprecated", "removed")
_NAME = re.compile(r"^([A-Za-z0-9_-]+)\.(" + "|".join(CATEGORIES) + r")\.md$")
_UNRELEASED = "## [Unreleased]"


def fragment_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.md") if p.name.lower() != "readme.md")


def problems(directory: Path) -> list[str]:
    found: list[str] = []
    for path in fragment_files(directory):
        if not _NAME.match(path.name):
            found.append(f"{path.name}: name must be <id>.<category>.md with category one of {', '.join(CATEGORIES)}")
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            found.append(f"{path.name}: empty")
        elif text.startswith("#"):
            found.append(f"{path.name}: write the entry text, not a heading")
    return found


def entry(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    return text if text.startswith("* ") else "* " + text


def _section_bounds(lines: list[str]) -> tuple[int, int]:
    start = next((i for i, line in enumerate(lines) if line.strip() == _UNRELEASED), None)
    if start is None:
        raise SystemExit(f"CHANGELOG.md has no '{_UNRELEASED}' section")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def _find(lines: list[str], start: int, end: int, predicate) -> "int | None":
    return next((i for i in range(start, end) if predicate(lines[i])), None)


def _insert(lines: list[str], category: str, text: str) -> list[str]:
    start, end = _section_bounds(lines)
    heading = f"### {category.capitalize()}"
    at = _find(lines, start, end, lambda line: line.strip() == heading)
    if at is None:
        block = ["", heading, "", text]
        return lines[:end] + block + ([""] if end < len(lines) else []) + lines[end:]
    insert_at = _find(lines, at + 1, end, lambda line: line.startswith("### ")) or end
    while insert_at > at + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    return lines[:insert_at] + ["", text] + lines[insert_at:]


def assemble(directory: Path, changelog: Path, keep: bool = False) -> int:
    bad = problems(directory)
    if bad:
        raise SystemExit("fragments are not valid:\n  " + "\n  ".join(bad))
    files = fragment_files(directory)
    lines = changelog.read_text(encoding="utf-8").split("\n")
    for path in files:
        category = _NAME.match(path.name).group(2)
        lines = _insert(lines, category, entry(path))
    changelog.write_text("\n".join(lines), encoding="utf-8")
    if not keep:
        for path in files:
            path.unlink()
    return len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "assemble"))
    parser.add_argument("--keep", action="store_true", help="assemble but leave the fragment files in place")
    parser.add_argument("--dir", type=Path, default=ROOT / "changelog.d")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    args = parser.parse_args(argv)
    if args.command == "check":
        bad = problems(args.dir)
        for line in bad:
            print(line)
        print(f"{len(fragment_files(args.dir))} fragment(s), {len(bad)} problem(s)")
        return 1 if bad else 0
    print(f"assembled {assemble(args.dir, args.changelog, args.keep)} fragment(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
from pathlib import Path


START_MARKER = "<!-- release-bundles:start -->"
END_MARKER = "<!-- release-bundles:end -->"


def merge_notes(existing: str, fragment: str) -> str:
    fragment = fragment.strip()
    existing = existing.strip()

    if START_MARKER in existing and END_MARKER in existing:
        start = existing.index(START_MARKER)
        end = existing.index(END_MARKER) + len(END_MARKER)
        prefix = existing[:start].rstrip()
        suffix = existing[end:].lstrip()
        parts = [part for part in (prefix, fragment, suffix) if part]
        return "\n\n".join(parts) + "\n"

    if existing:
        return f"{existing}\n\n{fragment}\n"

    return f"{fragment}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("existing_path")
    parser.add_argument("fragment_path")
    parser.add_argument("output_path")
    args = parser.parse_args()

    existing_path = Path(args.existing_path)
    fragment_path = Path(args.fragment_path)
    output_path = Path(args.output_path)

    existing = existing_path.read_text(encoding="utf-8") if existing_path.exists() else ""
    fragment = fragment_path.read_text(encoding="utf-8")
    output = merge_notes(existing, fragment)
    output_path.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
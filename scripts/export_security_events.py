#!/usr/bin/env python3
"""Export durable security events as JSONL."""

from __future__ import annotations

import argparse
import sys

from src.shared.security_events import export_security_events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--event-type")
    args = parser.parse_args(argv)

    count, jsonl = export_security_events(
        output_path=args.output,
        limit=args.limit,
        event_type=args.event_type,
    )
    if args.output:
        print(f"Exported {count} security events to {args.output}")
    else:
        sys.stdout.write(jsonl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

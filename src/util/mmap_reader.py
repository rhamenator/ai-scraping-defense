"""Utilities for reading large files efficiently."""

from __future__ import annotations

import mmap
import os
from pathlib import Path
from typing import Iterator


def iter_text_lines(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    errors: str = "ignore",
    min_size_bytes: int = 1024 * 1024,
) -> Iterator[str]:
    """Yield lines from a file, using mmap for large files when possible."""
    file_path = Path(path)
    with file_path.open("r", encoding=encoding, errors=errors) as handle:
        try:
            size = os.fstat(handle.fileno()).st_size
        except OSError:
            size = 0

        if size < min_size_bytes:
            for line in handle:
                yield line.rstrip("\r\n")
            return

        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            while True:
                raw = mm.readline()
                if not raw:
                    break
                yield raw.decode(encoding, errors).rstrip("\r\n")

import os
import tempfile

from src.util.mmap_reader import iter_text_lines


def test_iter_text_lines_with_mmap():
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as tmp:
        tmp.write("alpha\nbeta\n")
        path = tmp.name

    try:
        lines = list(iter_text_lines(path, min_size_bytes=0))
        assert lines == ["alpha", "beta"]
    finally:
        os.unlink(path)

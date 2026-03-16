import json
import re
import unittest
from pathlib import Path

PROBLEM_FILE_MAP = Path(__file__).resolve().parents[2] / "problem_file_map.json"
STALE_BATCH_FILE_PATTERN = re.compile(
    r"(^|docs/)[a-z_]+_problems_batch\d+\.json(?: \(Proposed\))?$"
)


class TestProblemFileMapMetadata(unittest.TestCase):
    def test_problem_file_map_does_not_reference_stale_batch_inventories(self):
        data = json.loads(PROBLEM_FILE_MAP.read_text())
        stale_references = []

        for title, metadata in data.items():
            for field, value in metadata.items():
                if not isinstance(value, list):
                    continue
                for entry in value:
                    if isinstance(entry, str) and STALE_BATCH_FILE_PATTERN.match(entry):
                        stale_references.append((title, field, entry))

        self.assertEqual(stale_references, [])


if __name__ == "__main__":
    unittest.main()

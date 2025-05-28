# test\tarpit\rotating_archive.test.py
import unittest
from unittest.mock import patch, MagicMock
from tarpit import rotating_archive
import os
import tempfile

class TestRotatingArchive(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.archive_path = os.path.join(self.temp_dir.name, "archives")
        os.makedirs(self.archive_path, exist_ok=True)
        # Create mock archives
        for i in range(3):
            with open(os.path.join(self.archive_path, f"archive_{i}.zip"), 'w') as f:
                f.write("fake archive")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_next_archive_rotates_correctly(self):
        rotating_archive.init(self.archive_path)
        first = rotating_archive.get_next_archive()
        second = rotating_archive.get_next_archive()
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.basename(first).startswith("archive_"))

    def test_rotation_loops_after_end(self):
        rotating_archive.init(self.archive_path)
        paths = [rotating_archive.get_next_archive() for _ in range(5)]
        self.assertTrue(all(os.path.exists(p) for p in paths))

    def test_no_archives_returns_none(self):
        empty_path = os.path.join(self.temp_dir.name, "empty")
        os.makedirs(empty_path, exist_ok=True)
        rotating_archive.init(empty_path)
        self.assertIsNone(rotating_archive.get_next_archive())

if __name__ == '__main__':
    unittest.main()

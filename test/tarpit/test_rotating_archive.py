# test/tarpit/rotating_archive.test.py
import unittest
from unittest.mock import patch, MagicMock
import os
import time
import tempfile
import shutil
from src.tarpit import rotating_archive
import importlib

class TestRotatingArchiveComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory for testing archive rotation."""
        self.test_dir = tempfile.mkdtemp()
        
        # Patch the module's constants to use our temporary directory and settings
        self.patches = {
            'ARCHIVE_DIR': patch('src.tarpit.rotating_archive.ARCHIVE_DIR', self.test_dir),
            'ARCHIVE_PATTERN': patch('src.tarpit.rotating_archive.ARCHIVE_PATTERN', os.path.join(self.test_dir, "assets_*.zip")),
            'MAX_ARCHIVES_TO_KEEP': patch('src.tarpit.rotating_archive.MAX_ARCHIVES_TO_KEEP', 3),
            'create_fake_js_zip': patch('src.tarpit.rotating_archive.create_fake_js_zip')
        }
        self.mocks = {name: patcher.start() for name, patcher in self.patches.items()}
        
        # Configure the mock for create_fake_js_zip
        self.new_archive_path = os.path.join(self.test_dir, f"assets_{int(time.time())}.zip")
        self.mocks['create_fake_js_zip'].return_value = self.new_archive_path

    def tearDown(self):
        """Clean up the temporary directory and stop patches."""
        shutil.rmtree(self.test_dir)
        for patcher in self.patches.values():
            patcher.stop()

    def _create_dummy_files(self, count, start_time_offset):
        """Helper to create dummy archive files with staggered modification times."""
        for i in range(count):
            mtime = time.time() - start_time_offset + (i * 100)
            path = os.path.join(self.test_dir, f"assets_{i}.zip")
            with open(path, "w") as f:
                f.write("dummy content")
            os.utime(path, (mtime, mtime))

    def test_rotate_archives_deletes_oldest_files(self):
        """Test that old archives are correctly identified and deleted."""
        # Create 5 files, where we should keep 3, so 2 should be deleted.
        self._create_dummy_files(count=5, start_time_offset=1000)
        
        rotating_archive.rotate_archives()

        # Check that a new archive was created
        self.mocks['create_fake_js_zip'].assert_called_once_with(output_dir=self.test_dir)
        
        # After rotation, we should have MAX_ARCHIVES_TO_KEEP files.
        # The rotation logic runs *after* a new file is created, so it prunes
        # the list down to the max number.
        remaining_files = sorted(os.listdir(self.test_dir))
        
        # The logic keeps the newest files. In our setup, files 0 and 1 are the oldest.
        self.assertNotIn("assets_0.zip", remaining_files)
        self.assertNotIn("assets_1.zip", remaining_files)
        self.assertIn("assets_2.zip", remaining_files)
        self.assertIn("assets_3.zip", remaining_files)
        self.assertIn("assets_4.zip", remaining_files)
        self.assertEqual(len(remaining_files), 3)

    def test_rotate_archives_not_enough_files(self):
        """Test that no files are deleted if the count is less than MAX_ARCHIVES_TO_KEEP."""
        # Create 2 files, which is less than the max of 3
        self._create_dummy_files(count=2, start_time_offset=500)
        
        with patch('os.remove') as mock_remove:
            rotating_archive.rotate_archives()
            mock_remove.assert_not_called()

        remaining_files = sorted(os.listdir(self.test_dir))
        # After creating one new file, there will be 3 total, which is the limit.
        self.assertEqual(len(remaining_files), 2) # os.remove is mocked so nothing is deleted from our setup

    def test_rotate_archives_handles_creation_failure(self):
        """Test that rotation doesn't delete files if new archive creation fails."""
        self.mocks['create_fake_js_zip'].return_value = None # Simulate creation failure
        self._create_dummy_files(count=5, start_time_offset=1000)

        with patch('os.remove') as mock_remove:
            rotating_archive.rotate_archives()
            mock_remove.assert_not_called()

    @patch('glob.glob', return_value=[])
    def test_rotate_archives_no_existing_files(self, mock_glob):
        """Test that rotation runs cleanly when the archive directory is empty."""
        rotating_archive.rotate_archives()
        self.mocks['create_fake_js_zip'].assert_called_once()
        self.assertFalse(os.listdir(self.test_dir)) # Nothing actually gets created because of the mock

    @patch('os.remove', side_effect=OSError("Permission denied"))
    @patch('src.tarpit.rotating_archive.logger.error')
    def test_rotate_archives_handles_deletion_error(self, mock_logger_error, mock_os_remove):
        """Test that an error during file deletion is logged and handled."""
        self._create_dummy_files(count=5, start_time_offset=1000)
        
        rotating_archive.rotate_archives()
        
        # It will try to delete 2 files, so we expect 2 error logs.
        self.assertEqual(mock_logger_error.call_count, 2)
        self.assertIn("Failed to delete old archive", mock_logger_error.call_args_list[0][0][0])

if __name__ == '__main__':
    unittest.main()

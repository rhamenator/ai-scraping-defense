# test/tarpit/rotating_archive.test.py
import unittest
from unittest.mock import patch, MagicMock, call
import os
import time 
import tempfile
import importlib 

# Import the module to test
# This assumes that 'tarpit' is a package and 'js_zip_generator' is in the same package
# or that PYTHONPATH is set up correctly.
from tarpit import rotating_archive

class TestRotatingArchive(unittest.TestCase):

    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir_path = self.temp_dir_obj.name

        # Patch constants in the rotating_archive module for test isolation
        # These patches will affect the module instance used by the tests.
        self.archive_dir_patcher = patch.object(rotating_archive, 'ARCHIVE_DIR', self.temp_dir_path)
        self.archive_pattern_patcher = patch.object(rotating_archive, 'ARCHIVE_PATTERN', os.path.join(self.temp_dir_path, "assets_*.zip"))
        self.max_archives_patcher = patch.object(rotating_archive, 'MAX_ARCHIVES_TO_KEEP', 3)
        
        self.mock_archive_dir = self.archive_dir_patcher.start()
        self.mock_archive_pattern = self.archive_pattern_patcher.start()
        self.mock_max_archives = self.max_archives_patcher.start()
        
        self.addCleanup(self.archive_dir_patcher.stop)
        self.addCleanup(self.archive_pattern_patcher.stop)
        self.addCleanup(self.max_archives_patcher.stop)

        # Mock external dependencies
        self.create_fake_zip_patcher = patch('tarpit.rotating_archive.create_fake_js_zip')
        self.mock_create_fake_zip = self.create_fake_zip_patcher.start()
        self.addCleanup(self.create_fake_zip_patcher.stop)

        self.glob_patcher = patch('glob.glob')
        self.mock_glob = self.glob_patcher.start()
        self.addCleanup(self.glob_patcher.stop)

        self.getmtime_patcher = patch('os.path.getmtime')
        self.mock_getmtime = self.getmtime_patcher.start()
        self.addCleanup(self.getmtime_patcher.stop)

        self.remove_patcher = patch('os.remove')
        self.mock_remove = self.remove_patcher.start()
        self.addCleanup(self.remove_patcher.stop)

        self.print_patcher = patch('builtins.print')
        self.mock_print = self.print_patcher.start()
        self.addCleanup(self.print_patcher.stop)
        
        # Default successful archive creation
        self.mock_create_fake_zip.return_value = os.path.join(self.temp_dir_path, f"assets_new_{time.time()}.zip")


    def tearDown(self):
        self.temp_dir_obj.cleanup()
        # Patches are stopped by addCleanup

    def _setup_mock_archives(self, filenames_mtimes):
        """Helper to set up mock return values for glob and getmtime."""
        self.mock_glob.return_value = [os.path.join(self.temp_dir_path, fn) for fn, mt in filenames_mtimes]
        
        def getmtime_side_effect(path):
            filename_only = os.path.basename(path)
            for fn, mt in filenames_mtimes:
                if fn == filename_only:
                    return mt
            # Handle the newly created file by create_fake_js_zip if its mtime is queried
            if path == self.mock_create_fake_zip.return_value:
                return time.time() # Assume it's the newest
            return 0 # Default for unexpected paths
        self.mock_getmtime.side_effect = getmtime_side_effect


    def test_rotate_archives_generates_new_no_delete_needed(self):
        # MAX_ARCHIVES_TO_KEEP is 3. Simulate 2 existing archives.
        self._setup_mock_archives([
            ("assets_1.zip", time.time() - 200),
            ("assets_2.zip", time.time() - 100)
        ])
        new_archive_path = os.path.join(self.temp_dir_path, "assets_new.zip")
        self.mock_create_fake_zip.return_value = new_archive_path

        rotating_archive.rotate_archives()

        self.mock_create_fake_zip.assert_called_once_with(output_dir=self.temp_dir_path)
        self.mock_glob.assert_called_once_with(os.path.join(self.temp_dir_path, "assets_*.zip"))
        self.mock_remove.assert_not_called()
        self.mock_print.assert_any_call("Found 3 archives. No old archives to delete.") # 2 existing + 1 new

    def test_rotate_archives_deletes_oldest_archives(self):
        # MAX_ARCHIVES_TO_KEEP is 3. Simulate 4 existing archives.
        # After new one, 5 total. Should delete 2 oldest.
        mtime_now = time.time()
        # Files sorted by name, but getmtime will determine actual age
        # assets_oldest.zip should be deleted
        # assets_older.zip should be deleted
        # assets_kept1.zip, assets_kept2.zip, new_one.zip should be kept
        self._setup_mock_archives([
            ("assets_kept2.zip", mtime_now - 100),
            ("assets_oldest.zip", mtime_now - 400), # Oldest
            ("assets_kept1.zip", mtime_now - 200),
            ("assets_older.zip", mtime_now - 300)  # Second oldest
        ])
        new_archive_path = os.path.join(self.temp_dir_path, "assets_new.zip")
        self.mock_create_fake_zip.return_value = new_archive_path
        # Ensure the new archive is seen as the newest by getmtime mock
        self.mock_getmtime.side_effect = lambda path: {
            os.path.join(self.temp_dir_path, "assets_kept2.zip"): mtime_now - 100,
            os.path.join(self.temp_dir_path, "assets_oldest.zip"): mtime_now - 400,
            os.path.join(self.temp_dir_path, "assets_kept1.zip"): mtime_now - 200,
            os.path.join(self.temp_dir_path, "assets_older.zip"): mtime_now - 300,
            new_archive_path: mtime_now # Newest
        }.get(path, 0)


        rotating_archive.rotate_archives()

        self.mock_create_fake_zip.assert_called_once_with(output_dir=self.temp_dir_path)
        self.assertEqual(self.mock_remove.call_count, 2)
        self.mock_remove.assert_any_call(os.path.join(self.temp_dir_path, "assets_oldest.zip"))
        self.mock_remove.assert_any_call(os.path.join(self.temp_dir_path, "assets_older.zip"))
        self.mock_print.assert_any_call("Found 5 archives. Keeping 3, deleting 2.")


    def test_rotate_archives_generation_fails_skips_cleanup(self):
        self.mock_create_fake_zip.return_value = None # Simulate generation failure
        
        rotating_archive.rotate_archives()

        self.mock_create_fake_zip.assert_called_once_with(output_dir=self.temp_dir_path)
        self.mock_glob.assert_not_called()
        self.mock_remove.assert_not_called()
        self.mock_print.assert_any_call("Archive generation failed. Skipping cleanup.")

    def test_rotate_archives_glob_error(self):
        self.mock_glob.side_effect = Exception("Globbing error")
        # create_fake_js_zip should still be called
        new_archive_path = os.path.join(self.temp_dir_path, "assets_new.zip")
        self.mock_create_fake_zip.return_value = new_archive_path

        rotating_archive.rotate_archives()

        self.mock_create_fake_zip.assert_called_once()
        self.mock_glob.assert_called_once()
        self.mock_remove.assert_not_called()
        self.mock_print.assert_any_call(f"ERROR: Failed to list existing archives in {self.temp_dir_path}: Globbing error")

    def test_rotate_archives_remove_error(self):
        self._setup_mock_archives([
            ("assets_1.zip", time.time() - 400), # To be deleted
            ("assets_2.zip", time.time() - 300), # To be deleted
            ("assets_3.zip", time.time() - 200),
            ("assets_4.zip", time.time() - 100)
        ])
        new_archive_path = os.path.join(self.temp_dir_path, "assets_new.zip")
        self.mock_create_fake_zip.return_value = new_archive_path
        self.mock_getmtime.side_effect = lambda path: { # Ensure new file is newest
            os.path.join(self.temp_dir_path, "assets_1.zip"): time.time() - 400,
            os.path.join(self.temp_dir_path, "assets_2.zip"): time.time() - 300,
            os.path.join(self.temp_dir_path, "assets_3.zip"): time.time() - 200,
            os.path.join(self.temp_dir_path, "assets_4.zip"): time.time() - 100,
            new_archive_path: time.time()
        }.get(path, 0)

        self.mock_remove.side_effect = [OSError("Permission denied on first file"), None] # First remove fails

        rotating_archive.rotate_archives()

        self.assertEqual(self.mock_remove.call_count, 2) # Attempted to delete two
        self.mock_print.assert_any_call(f"ERROR: Failed to delete old archive {os.path.join(self.temp_dir_path, 'assets_1.zip')}: Permission denied on first file")
        self.mock_print.assert_any_call(f"  Deleted old archive: {os.path.join(self.temp_dir_path, 'assets_2.zip')}")

    # Test __main__ block
    @patch.object(rotating_archive.schedule, 'every')
    @patch.object(rotating_archive.schedule, 'run_pending')
    @patch.object(rotating_archive.time, 'sleep')
    @patch.object(rotating_archive, 'rotate_archives') # Mock the core function
    @patch.object(rotating_archive.sys, 'exit') # To prevent exit if js_zip_generator import fails in real scenario
    def test_main_block_setup_and_initial_run(self, mock_sys_exit, mock_rotate_archives_func, 
                                              mock_time_sleep, mock_run_pending, mock_schedule_every):
        mock_minutes_obj = MagicMock()
        mock_every_obj = MagicMock()
        mock_every_obj.minutes.return_value = mock_minutes_obj
        mock_schedule_every.return_value = mock_every_obj

        # Simulate the loop breaking after a few iterations for the test
        mock_time_sleep.side_effect = [None, KeyboardInterrupt] # First sleep ok, second breaks

        # To test the __main__ block, we need to execute it.
        # Reloading the module is one way if __name__ is appropriately handled.
        # Here, we'll check if the setup calls are made as expected.
        
        # The main logic is guarded by `if __name__ == "__main__"`.
        # We can patch `__name__` for the `rotating_archive` module during the test.
        
        with patch.object(rotating_archive, '__name__', '__main__'):
            try:
                # Reloading the module will execute its top-level code, including the __main__ block.
                # Ensure that the create_fake_js_zip is mocked (done in setUp)
                # because its import failure in the SUT causes sys.exit(1).
                importlib.reload(rotating_archive)
            except KeyboardInterrupt:
                pass # Expected to break the loop

        # Check that rotate_archives was called initially
        mock_rotate_archives_func.assert_any_call() # Called at least once for initial run
        
        # Check that scheduling was set up
        mock_schedule_every.assert_called_once_with(rotating_archive.GENERATION_INTERVAL_MINUTES)
        mock_minutes_obj.do.assert_called_once_with(rotating_archive.rotate_archives) # Check it was scheduled with the (mocked) function

        # Check that the loop ran at least once
        self.assertGreaterEqual(mock_run_pending.call_count, 1)
        self.assertGreaterEqual(mock_time_sleep.call_count, 1)
        mock_sys_exit.assert_not_called() # Ensure sys.exit from import guard wasn't hit during test


if __name__ == '__main__':
    unittest.main()

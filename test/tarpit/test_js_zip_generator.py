# test/tarpit/js_zip_generator.test.py
import unittest
from unittest.mock import patch
import os
import zipfile
import tempfile
import shutil
import random
import logging

from src.tarpit import js_zip_generator


class TestJsZipGeneratorComprehensive(unittest.TestCase):

    def setUp(self):
        """Create a temporary directory for generated ZIP files."""
        self.test_dir = tempfile.mkdtemp()
        # Logging will be captured with assertLogs when needed

    def tearDown(self):
        """Remove the temporary directory and re-enable logging."""
        shutil.rmtree(self.test_dir)

    def test_generate_realistic_filename(self):
        """Test that the generated filename is plausible and varied."""
        random.seed(1)
        filename1 = js_zip_generator.generate_realistic_filename()
        filename2 = js_zip_generator.generate_realistic_filename()

        self.assertNotEqual(filename1, filename2)
        self.assertTrue(filename1.endswith(".js"))
        self.assertTrue(
            any(prefix in filename1 for prefix in js_zip_generator.FILENAME_PREFIXES)
        )

    def test_create_fake_js_zip_success(self):
        """Test successful creation of a ZIP file with multiple JS files."""
        num_files = 15
        zip_path = js_zip_generator.create_fake_js_zip(
            output_dir=self.test_dir, num_files=num_files
        )

        self.assertIsNotNone(zip_path)
        if zip_path is None:
            self.fail("Expected zip_path to be a valid path, but it was None.")
        else:
            self.assertTrue(zip_path.endswith(".zip"))
            self.assertTrue(os.path.exists(zip_path))

        # Verify the contents of the created zip file
        with zipfile.ZipFile(zip_path, "r") as zf:
            self.assertEqual(len(zf.namelist()), num_files)
            # Check the content of one of the files
            first_filename = zf.namelist()[0]
            file_content = zf.read(first_filename).decode("utf-8")
            self.assertTrue(file_content.startswith("// Fake module:"))
            self.assertIn("function", file_content)
            self.assertGreater(len(file_content), 200)

    def test_create_fake_js_zip_zero_files(self):
        """Test that a ZIP file can be created with zero files inside."""
        zip_path = js_zip_generator.create_fake_js_zip(
            output_dir=self.test_dir, num_files=0
        )
        self.assertIsNotNone(zip_path)
        # Type checker now knows zip_path cannot be None here, resolving the error.
        if zip_path is None:
            self.fail("Expected zip_path to be a valid path, but it was None.")
        else:
            with zipfile.ZipFile(zip_path, "r") as zf:
                self.assertEqual(len(zf.namelist()), 0)

    def test_create_fake_js_zip_recursive(self):
        """Ensure nested archives are created when recursive_depth > 0."""
        zip_path = js_zip_generator.create_fake_js_zip(
            output_dir=self.test_dir, num_files=3, recursive_depth=1
        )
        self.assertIsNotNone(zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            self.assertTrue(any(name.endswith('.zip') for name in names))

    @patch("zipfile.ZipFile", side_effect=IOError("Disk full or permissions error"))
    def test_create_fake_js_zip_handles_zip_exception(self, mock_zipfile):
        """Test that exceptions during ZIP file creation are handled gracefully."""
        # Use the string name of the logger to capture logs
        with self.assertLogs("src.tarpit.js_zip_generator", level="ERROR") as cm:
            zip_path = js_zip_generator.create_fake_js_zip(output_dir=self.test_dir)
            self.assertIsNone(zip_path)
            self.assertIn("Failed to create zip file", cm.output[0])

    @patch("os.makedirs", side_effect=OSError("Permission denied"))
    def test_create_fake_js_zip_handles_dir_creation_error(self, mock_makedirs):
        """Test that an error creating the output directory is handled."""
        non_existent_dir = os.path.join(self.test_dir, "subdir", "subsubdir")
        # Use the string name of the logger to capture logs
        with self.assertLogs("src.tarpit.js_zip_generator", level="ERROR") as cm:
            zip_path = js_zip_generator.create_fake_js_zip(output_dir=non_existent_dir)
            self.assertIsNone(zip_path)
            self.assertIn("Failed to create output directory", cm.output[0])


if __name__ == "__main__":
    unittest.main()

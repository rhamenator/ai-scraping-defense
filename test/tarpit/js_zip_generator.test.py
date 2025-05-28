# test/tarpit/js_zip_generator.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, call, ANY # Ensure ANY is imported
import os
import random
import string
import datetime
import zipfile
import tempfile
import importlib

# Import the module to test
from tarpit import js_zip_generator

class TestJsZipGeneratorHelpers(unittest.TestCase):

    def test_generate_random_string(self):
        s10 = js_zip_generator.generate_random_string(10)
        self.assertEqual(len(s10), 10)
        self.assertTrue(all(c in string.printable for c in s10))

        s0 = js_zip_generator.generate_random_string(0)
        self.assertEqual(s0, "")

        s10_again = js_zip_generator.generate_random_string(10)
        # This can occasionally fail due to randomness, but highly unlikely for short strings.
        # For more robust test, seed random or check properties other than exact inequality.
        if s10 == s10_again: 
            print(f"Warning: generate_random_string produced identical strings: '{s10}'")
        self.assertNotEqual(s10, s10_again, "Random strings should generally differ (probabilistic)")


    @patch('random.choice')
    @patch('random.choices')
    def test_generate_realistic_filename(self, mock_choices, mock_choice):
        mock_choice.side_effect = lambda x: x[0] 
        mock_choices.side_effect = lambda population, k: list(population[:k]) 

        filename = js_zip_generator.generate_realistic_filename()
        
        expected_prefix = js_zip_generator.FILENAME_PREFIXES[0]
        expected_suffix = js_zip_generator.FILENAME_SUFFIXES[0]
        # Correctly simulate the choices for the hash part
        expected_hash_population = string.ascii_lowercase + string.digits
        expected_hash_chars = list(expected_hash_population[:8]) # as per mock_choices side_effect
        
        self.assertTrue(filename.startswith(expected_prefix))
        self.assertIn(expected_suffix, filename)
        self.assertIn("".join(expected_hash_chars), filename)
        self.assertTrue(filename.endswith(js_zip_generator.FILENAME_EXT))

class TestCreateFakeJsZip(unittest.TestCase):

    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.test_output_dir = self.temp_dir_obj.name

        self.default_archive_dir_patcher = patch.object(js_zip_generator, 'DEFAULT_ARCHIVE_DIR', self.test_output_dir)
        self.num_fake_files_patcher = patch.object(js_zip_generator, 'NUM_FAKE_FILES', 2) 
        self.min_size_patcher = patch.object(js_zip_generator, 'MIN_FILE_SIZE_KB', 1)
        self.max_size_patcher = patch.object(js_zip_generator, 'MAX_FILE_SIZE_KB', 2)

        self.mock_default_archive_dir = self.default_archive_dir_patcher.start()
        self.mock_num_fake_files = self.num_fake_files_patcher.start()
        self.mock_min_size = self.min_size_patcher.start()
        self.mock_max_size = self.max_size_patcher.start()

        self.addCleanup(self.default_archive_dir_patcher.stop)
        self.addCleanup(self.num_fake_files_patcher.stop)
        self.addCleanup(self.min_size_patcher.stop)
        self.addCleanup(self.max_size_patcher.stop)

        self.makedirs_patcher = patch('os.makedirs')
        self.mock_makedirs = self.makedirs_patcher.start()
        self.addCleanup(self.makedirs_patcher.stop)

        self.zipfile_patcher = patch('zipfile.ZipFile')
        self.MockZipFile = self.zipfile_patcher.start() 
        self.mock_zip_instance = MagicMock(spec=zipfile.ZipFile)
        self.MockZipFile.return_value.__enter__.return_value = self.mock_zip_instance 
        self.addCleanup(self.zipfile_patcher.stop)
        
        self.print_patcher = patch('builtins.print')
        self.mock_print = self.print_patcher.start()
        self.addCleanup(self.print_patcher.stop)


    def tearDown(self):
        self.temp_dir_obj.cleanup()

    @patch('random.randint', side_effect=lambda a,b: a) 
    @patch('tarpit.js_zip_generator.generate_realistic_filename', return_value="fake_test_file.js")
    @patch('tarpit.js_zip_generator.generate_random_string', return_value="random_content")
    def test_create_fake_js_zip_success(self, mock_gen_string, mock_gen_filename, mock_randint):
        num_files_for_test = 2 
        # Call with a specific num_files, NUM_FAKE_FILES patch in setUp might not affect default arg this way
        result_zip_path = js_zip_generator.create_fake_js_zip(output_dir=self.test_output_dir, num_files=num_files_for_test)

        self.mock_makedirs.assert_called_once_with(self.test_output_dir, exist_ok=True)
        
        self.assertIsNotNone(result_zip_path, "ZIP path should not be None on success.")
        
        # Explicit check for Pylance before using result_zip_path with os.path functions
        if result_zip_path is not None:
            self.assertEqual(os.path.dirname(result_zip_path), self.test_output_dir)
            self.assertTrue(os.path.basename(result_zip_path).startswith("assets_"))
            self.assertTrue(os.path.basename(result_zip_path).endswith(".zip"))
            self.MockZipFile.assert_called_once_with(result_zip_path, 'w', zipfile.ZIP_DEFLATED)
        else:
            self.fail("result_zip_path was None unexpectedly.")


        self.assertEqual(self.mock_zip_instance.writestr.call_count, num_files_for_test)

        first_call_args = self.mock_zip_instance.writestr.call_args_list[0].args
        self.assertEqual(first_call_args[0], "fake_test_file.js") 
        self.assertIn("// Fake module: fake_test_file.js", first_call_args[1]) 
        self.assertIn("var ", first_call_args[1])
        self.assertIn("function ", first_call_args[1])
        self.assertIn("/* random_content */", first_call_args[1]) 
        
        self.mock_print.assert_any_call(f"Creating fake JS archive: {result_zip_path}")
        self.mock_print.assert_any_call(f"Successfully created {result_zip_path} with {num_files_for_test} fake files.")

    @patch('zipfile.ZipFile', side_effect=Exception("ZIP Error"))
    @patch('os.path.exists')
    @patch('os.remove')
    def test_create_fake_js_zip_zip_creation_fails(self, mock_os_remove, mock_os_exists, mock_zipfile_error):
        mock_os_exists.return_value = True 
        
        result_zip_path = js_zip_generator.create_fake_js_zip(output_dir=self.test_output_dir)

        self.assertIsNone(result_zip_path)
        # Use ANY from unittest.mock for the initial print call's argument
        self.mock_print.assert_any_call(ANY) 
        error_print_found = any("ERROR: Failed to create ZIP file" in str(c[0]) for c in self.mock_print.call_args_list)
        self.assertTrue(error_print_found)
        
        mock_os_exists.assert_called() 
        mock_os_remove.assert_called() 

    @patch('zipfile.ZipFile') 
    @patch('tarpit.js_zip_generator.generate_realistic_filename', side_effect=Exception("Filename gen error"))
    @patch('os.path.exists')
    @patch('os.remove')
    def test_create_fake_js_zip_internal_helper_fails(self, mock_os_remove, mock_os_exists, mock_gen_filename_error, MockZipFileHelper):
        mock_zip_instance_helper = MagicMock()
        MockZipFileHelper.return_value.__enter__.return_value = mock_zip_instance_helper
        mock_os_exists.return_value = True 

        result_zip_path = js_zip_generator.create_fake_js_zip(output_dir=self.test_output_dir, num_files=1)
        
        self.assertIsNone(result_zip_path)
        error_print_found = any("ERROR: Failed to create ZIP file" in str(c[0]) for c in self.mock_print.call_args_list)
        self.assertTrue(error_print_found)
        mock_os_exists.assert_called()
        mock_os_remove.assert_called()


class TestMainExecutionBlock(unittest.TestCase):

    @patch('tarpit.js_zip_generator.create_fake_js_zip')
    @patch('builtins.print')
    def test_main_block_success(self, mock_print, mock_create_zip):
        mock_create_zip.return_value = "/fake/dir/assets_test.zip"
        
        with patch.object(js_zip_generator, '__name__', '__main__'):
            importlib.reload(js_zip_generator)
            
        mock_create_zip.assert_called_once()
        mock_print.assert_any_call("Test archive created at: /fake/dir/assets_test.zip")

    @patch('tarpit.js_zip_generator.create_fake_js_zip')
    @patch('builtins.print')
    def test_main_block_creation_fails(self, mock_print, mock_create_zip):
        mock_create_zip.return_value = None 
        
        with patch.object(js_zip_generator, '__name__', '__main__'):
            importlib.reload(js_zip_generator)
            
        mock_create_zip.assert_called_once()
        mock_print.assert_any_call("Test archive creation failed.")


if __name__ == '__main__':
    unittest.main()

# test\tarpit\js_zip_generator.test.py
import unittest
from tarpit import js_zip_generator
import os
import zipfile

class TestJSZipGenerator(unittest.TestCase):

    def setUp(self):
        self.test_output = "test_output.zip"

    def tearDown(self):
        if os.path.exists(self.test_output):
            os.remove(self.test_output)

    def test_generate_zip_file_created(self):
        js_zip_generator.generate_zip(self.test_output)
        self.assertTrue(os.path.exists(self.test_output))
        self.assertTrue(zipfile.is_zipfile(self.test_output))

    def test_zip_contains_javascript_files(self):
        js_zip_generator.generate_zip(self.test_output)
        with zipfile.ZipFile(self.test_output, 'r') as zipf:
            contents = zipf.namelist()
            js_files = [f for f in contents if f.endswith(".js")]
            self.assertGreater(len(js_files), 0)

    def test_zip_file_is_not_empty(self):
        js_zip_generator.generate_zip(self.test_output)
        size = os.path.getsize(self.test_output)
        self.assertGreater(size, 100)  # some threshold

if __name__ == '__main__':
    unittest.main()

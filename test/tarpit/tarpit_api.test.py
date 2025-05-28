# test\tarpit\tarpit_api.test.py
import unittest
from unittest.mock import patch
from tarpit.tarpit_api import app

class TestTarpitAPI(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)

    @patch("tarpit.tarpit_api.archive_loader.get_next_archive")
    def test_archive_download(self, mock_get_next):
        mock_get_next.return_value = "fake.zip"
        with patch("builtins.open", unittest.mock.mock_open(read_data=b"data")) as mock_file:
            response = self.client.get("/download")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"data")

    def test_404_for_unknown_route(self):
        response = self.client.get("/nope")
        self.assertEqual(response.status_code, 404)

    @patch("tarpit.tarpit_api.flagger.flag")
    def test_flag_endpoint(self, mock_flag):
        response = self.client.post("/flag", json={"ip": "1.2.3.4"})
        self.assertEqual(response.status_code, 200)
        mock_flag.assert_called_with("1.2.3.4")

if __name__ == '__main__':
    unittest.main()

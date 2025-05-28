# test\util\corpus_wikipedia_updater.test.py
import unittest
from unittest.mock import patch, mock_open
from util import corpus_wikipedia_updater as updater

class TestCorpusWikipediaUpdater(unittest.TestCase):

    @patch("util.corpus_wikipedia_updater.requests.get")
    def test_fetch_article_success(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html><body><p>Sample Wikipedia content.</p></body></html>"
        content = updater.fetch_article("Test_Page")
        self.assertIn("Sample Wikipedia content.", content)

    @patch("util.corpus_wikipedia_updater.requests.get")
    def test_fetch_article_failure(self, mock_get):
        mock_get.return_value.status_code = 404
        with self.assertRaises(ValueError):
            updater.fetch_article("Nonexistent_Page")

    @patch("builtins.open", new_callable=mock_open)
    def test_store_article(self, mock_file):
        updater.store_article("Title", "Some text.", "/fake/path")
        mock_file.assert_called_with("/fake/path/Title.txt", "w", encoding="utf-8")
        handle = mock_file()
        handle.write.assert_called_once_with("Some text.")

if __name__ == '__main__':
    unittest.main()

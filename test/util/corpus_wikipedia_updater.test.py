# test/util/corpus_wikipedia_updater.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import tempfile
import shutil

from util import corpus_wikipedia_updater

class MockWikiPage:
    """A mock object for a wikipediaapi page."""
    def __init__(self, title, text, exists=True, ns=0, categories=None):
        self.title = title
        self.text = text
        self.summary = text[:50] # Abridged version
        self._exists = exists
        self.ns = ns # 0 for articles
        self.categories = categories if categories is not None else {"Category:Living people": MagicMock()}
    
    def exists(self):
        return self._exists

class TestWikipediaCorpusUpdaterComprehensive(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.corpus_file = os.path.join(self.test_dir, "corpus.txt")
        
        self.patches = {
            'requests.Session': patch('util.corpus_wikipedia_updater.requests.Session'),
            'wikipediaapi.Wikipedia': patch('util.corpus_wikipedia_updater.wikipediaapi.Wikipedia'),
            'time.sleep': patch('time.sleep', return_value=None),
            'CORPUS_OUTPUT_FILE': patch('util.corpus_wikipedia_updater.CORPUS_OUTPUT_FILE', self.corpus_file)
        }
        self.mocks = {name: patcher.start() for name, patcher in self.patches.items()}

        # Configure mocks
        self.mock_wiki_api = self.mocks['wikipediaapi.Wikipedia'].return_value
        self.mock_session = self.mocks['requests.Session'].return_value
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)
        for patcher in self.patches.values():
            patcher.stop()

    def test_clean_text(self):
        """Test the text cleaning function with various edge cases."""
        raw_text = "== Section ==\n'''Bold''' text with a <!-- comment --> and a <ref>citation</ref>. It also has {{template|param}} and [[File:image.jpg|thumb|caption]]. Finally, a list:\n* Item 1\n* Item 2"
        expected = "Bold text with a  and a . It also has  and . Finally, a list: Item 1 Item 2"
        self.assertEqual(corpus_wikipedia_updater.clean_text(raw_text), expected)
        # Test with only whitespace and newlines
        self.assertEqual(corpus_wikipedia_updater.clean_text(" \n \n "), "")

    def test_fetch_random_wikipedia_articles_api_success(self):
        """Test successful fetching of multiple valid articles."""
        # Simulate the API returning a list of random titles
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {"random": [{"title": "Page One"}, {"title": "Page Two"}]}
        }
        self.mock_session.get.return_value = mock_response

        # Simulate the page objects returned for these titles
        self.mock_wiki_api.page.side_effect = [
            MockWikiPage("Page One", "Content for page one."),
            MockWikiPage("Page Two", "Content for page two.")
        ]
        
        articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(num_articles=2)
        
        self.assertEqual(len(articles), 2)
        self.assertIn("Content for page one.", articles)
        self.assertIn("Content for page two.", articles)

    def test_fetch_skips_non_articles_and_disallowed_categories(self):
        """Test that the fetcher correctly skips non-articles and pages in disallowed categories."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "query": {"random": [{"title": "Living Person"}, {"title": "Talk Page"}, {"title": "Good Article"}]}
        }
        self.mock_session.get.return_value = mock_response

        self.mock_wiki_api.page.side_effect = [
            MockWikiPage("Living Person", "This person is alive.", categories={"Category:Living people": MagicMock()}),
            MockWikiPage("Talk Page", "Discussion here.", ns=1), # ns=1 is a talk page
            MockWikiPage("Good Article", "This is a good article.", categories={"Category:Science": MagicMock()})
        ]

        articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(num_articles=3)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0], "This is a good article.")
        
    @patch('util.corpus_wikipedia_updater.logger.error')
    def test_fetch_api_request_fails(self, mock_logger_error):
        """Test handling of a network error when fetching random pages."""
        self.mock_session.get.side_effect = Exception("Network timeout")
        articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(num_articles=5)
        self.assertEqual(articles, [])
        mock_logger_error.assert_called_once()
        self.assertIn("Failed to fetch random pages", mock_logger_error.call_args[0][0])

    def test_update_corpus_file(self):
        """Test writing fetched content to the corpus file."""
        articles = ["New article content.", "Another line of text."]
        corpus_wikipedia_updater.update_corpus_file(articles)
        
        with open(self.corpus_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn("New article content.\n", content)
        self.assertIn("Another line of text.\n", content)

    @patch('util.corpus_wikipedia_updater.logger.error')
    def test_update_corpus_file_write_error(self, mock_logger_error):
        """Test that an error during file writing is caught and logged."""
        with patch('builtins.open', mock_open()) as mocked_file:
            mocked_file.side_effect = IOError("Disk full")
            corpus_wikipedia_updater.update_corpus_file(["some content"])
            mock_logger_error.assert_called_once()
            self.assertIn("Failed to write to corpus file", mock_logger_error.call_args[0][0])

if __name__ == '__main__':
    unittest.main()

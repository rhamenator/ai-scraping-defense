# test/util/corpus_wikipedia_updater.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.util import corpus_wikipedia_updater
# Import the actual exceptions from the library for mocking
from wikipedia.exceptions import DisambiguationError, PageError

class TestWikipediaCorpusUpdater(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.corpus_file = os.path.join(self.test_dir, "corpus.txt")
        
        # Patch the wikipedia library and the output file path
        self.patches = {
            'wikipedia': patch('src.util.corpus_wikipedia_updater.wikipedia'),
            'CORPUS_OUTPUT_FILE': patch('src.util.corpus_wikipedia_updater.CORPUS_OUTPUT_FILE', self.corpus_file)
        }
        self.mocks = {name: patcher.start() for name, patcher in self.patches.items()}

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        for patcher in self.patches.values():
            patcher.stop()

    def test_clean_text(self):
        """Test the text cleaning function with various markup."""
        raw_text = "== History ==\n'''AI''' is a field of computer science. <ref>A citation.</ref> It is cool.\n* Point 1\n* [[File:Test.png|thumb]]"
        expected = "AI is a field of computer science.  It is cool. Point 1"
        self.assertEqual(corpus_wikipedia_updater.clean_text(raw_text), expected)

    def test_fetch_random_wikipedia_articles_success(self):
        """Test the successful fetching and processing of a valid article."""
        mock_wiki = self.mocks['wikipedia']
        
        # Simulate the 'wikipedia.random()' call
        mock_wiki.random.return_value = "Artificial Intelligence"
        
        # Create a mock page object with the expected attributes
        mock_page = MagicMock()
        mock_page.title = "Artificial Intelligence"
        mock_page.content = "This is the full, long content of the AI article which is definitely more than 500 characters long to pass the length check. " * 10
        mock_page.categories = ["Computer science", "Cybernetics"]
        
        # Make 'wikipedia.page()' return our mock page
        mock_wiki.page.return_value = mock_page
        
        articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles(num_articles=1)
        
        self.assertEqual(len(articles), 1)
        self.assertIn("This is the full, long content", articles[0])
        mock_wiki.random.assert_called_once_with(pages=1)
        mock_wiki.page.assert_called_once_with("Artificial Intelligence", auto_suggest=False, redirect=True)

    def test_fetch_skips_disambiguation_pages(self):
        """Test that DisambiguationError is caught and the page is skipped."""
        mock_wiki = self.mocks['wikipedia']
        mock_wiki.random.side_effect = ["Disambiguation Page", "Good Page"]
        
        # First call to page() will raise an error, second will succeed
        mock_good_page = MagicMock(content="Good content " * 100, categories=["Technology"])
        mock_wiki.page.side_effect = [DisambiguationError(title="Disambiguation Page", may_refer_to=[]), mock_good_page]

        with self.assertLogs('src.util.corpus_wikipedia_updater', level='WARNING') as cm:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles(num_articles=1)
            self.assertIn("Skipping 'Disambiguation Page'", cm.output[0])

        self.assertEqual(len(articles), 1)
        self.assertIn("Good content", articles[0])

    def test_fetch_skips_disallowed_categories(self):
        """Test that articles in disallowed categories are skipped."""
        mock_wiki = self.mocks['wikipedia']
        mock_wiki.random.return_value = "John Doe"
        
        mock_page = MagicMock()
        mock_page.title = "John Doe"
        mock_page.content = "Content about a person " * 50
        mock_page.categories = ["Living people", "Scientists"] # "Living people" is disallowed
        
        mock_wiki.page.return_value = mock_page
        
        with self.assertLogs('src.util.corpus_wikipedia_updater', level='DEBUG') as cm:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles(num_articles=1)
            # This should try again since the first was skipped, so we mock a second good return
            mock_wiki.random.return_value = "Good Article"
            mock_page.categories = ["Good Category"]
            articles.extend(corpus_wikipedia_updater.fetch_random_wikipedia_articles(num_articles=1))
            self.assertTrue(any("Skipping 'John Doe' due to disallowed category" in m for m in cm.output))
        
    def test_update_corpus_file(self):
        """Test that new articles are correctly appended to the corpus file."""
        articles = ["First article.", "Second article."]
        
        # Use mock_open to simulate file I/O
        with patch("builtins.open", mock_open()) as mocked_file:
            corpus_wikipedia_updater.update_corpus_file(articles)
            
            # Verify the file was opened in append mode
            mocked_file.assert_called_once_with(self.corpus_file, 'a', encoding='utf-8')
            
            # Verify the content was written
            handle = mocked_file()
            handle.write.assert_any_call("First article.\n")
            handle.write.assert_any_call("Second article.\n")

if __name__ == '__main__':
    unittest.main()

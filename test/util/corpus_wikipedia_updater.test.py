# test_corpus_wikipedia_updater.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, call, ANY
import os
import logging
import sys
import re # Import re for the tests

# Calculate the project root directory from the test file's location
# Assuming __file__ is PROJECT_ROOT/test/util/test_corpus_wikipedia_updater.py
# SCRIPT_DIR is PROJECT_ROOT/test/util
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# TEST_UTIL_DIR is PROJECT_ROOT/test/util (same as SCRIPT_DIR, more descriptive name)
# TEST_DIR is PROJECT_ROOT/test
TEST_DIR = os.path.dirname(SCRIPT_DIR)
# PROJECT_ROOT_DIR is PROJECT_ROOT
PROJECT_ROOT_DIR = os.path.dirname(TEST_DIR)

# Add PROJECT_ROOT_DIR to sys.path to allow imports from 'util'
sys.path.insert(0, PROJECT_ROOT_DIR)

# Now we can import from the 'util' package
from util import corpus_wikipedia_updater

# To ensure we can reload the module with patched env vars, we might need this
import importlib

# Define a dummy response class for requests.get
class MockResponse:
    def __init__(self, content, status_code, url, headers=None, text=None):
        self.content = content
        self.status_code = status_code
        self.url = url
        self.headers = headers if headers is not None else {}
        self.text = text if text is not None else content.decode('utf-8') if isinstance(content, bytes) else content


    def raise_for_status(self):
        if self.status_code >= 400:
            # Access requests via the imported module
            raise corpus_wikipedia_updater.requests.exceptions.HTTPError(
                f"Error {self.status_code}", response=self  # type: ignore[arg-type]
            )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

# Define a dummy page class for wikipediaapi
class MockWikiPage:
    def __init__(self, title, text_content, exists=True, is_category=False, is_disambig=False):
        self.title = title
        self.text = text_content
        self._exists = exists
        self.is_categorypage = is_category
        self.is_disambigpage = is_disambig

    def exists(self):
        return self._exists

# Define a dummy BeautifulSoup tag
class MockBeautifulSoupTag:
    def __init__(self, text="", name="div", attrs=None, children=None):
        self.name = name
        self._text = text
        self.attrs = attrs if attrs else {}
        self.children = children if children else []

    def get_text(self, separator=" ", strip=True):
        text_content = self._text
        if strip:
            text_content = text_content.strip()
        return text_content
    
    def find_all(self, name=None, class_=None, **kwargs): # Adjusted to match usage
        # Simplified find_all, would need more complex logic for real scenarios
        # Simulate finding unwanted tags for decomposition
        if name in ['table', 'div', 'span', 'style', 'script'] or (name == 'sup' and class_ == 'reference'):
             return [MockBeautifulSoupTag(text=" unwanted ", name=name if isinstance(name, str) else "div")]
        # Simulate finding content tags for text extraction
        if isinstance(name, list) and 'p' in name: # For ['p', 'li', 'h2', 'h3', 'h4']
             return self.children # Return pre-set children like p_tag, li_tag
        return []


    def find(self, name=None, id=None, class_=None): # Adjusted to match usage
        if name == 'h1' and id == 'firstHeading':
            return MockBeautifulSoupTag(text="Mock Page Title")
        if name == 'div' and class_ == 'mw-parser-output':
            # Return a tag that can have children or specific text for testing
            p_tag = MockBeautifulSoupTag(text="This is a paragraph.", name='p')
            li_tag = MockBeautifulSoupTag(text="This is a list item.", name='li')
            # This instance will be returned by soup.find(...)
            content_div_instance = MockBeautifulSoupTag(text="Overall content div text", children=[p_tag, li_tag])
            # Configure its find_all directly if needed, or rely on general MockBeautifulSoupTag.find_all
            return content_div_instance
        return None

    def decompose(self):
        self._text = "" # Simulate decomposition
        self.children = []

    @property
    def text(self): # Make text a property for bs4
        return self.get_text()


class TestCorpusWikipediaUpdaterConfig(unittest.TestCase):
    """Tests for configuration loading."""

    @patch.dict(os.environ, {
        "WIKIPEDIA_CORPUS_FILE": "/test/corpus.txt",
        "WIKIPEDIA_NUM_ARTICLES": "10",
        "WIKIPEDIA_LANGUAGE": "fr",
    })
    @patch('os.getpid', return_value=12345) # Mock getpid for consistent user agent
    def test_environment_variables_loaded(self, mock_getpid):
        """Test that environment variables are correctly loaded."""
        # We need to reload the corpus_wikipedia_updater module for it to pick up the new env vars
        importlib.reload(corpus_wikipedia_updater)
        self.assertEqual(corpus_wikipedia_updater.CORPUS_OUTPUT_FILE, "/test/corpus.txt")
        self.assertEqual(corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH, 10)
        self.assertEqual(corpus_wikipedia_updater.WIKI_LANGUAGE, "fr")
        expected_user_agent = "CorpusUpdater/1.1 (AI-Scraping-Defense; +https://github.com/your-repo/ai-scraping-defense; process/12345)"
        self.assertEqual(corpus_wikipedia_updater.REQUESTS_USER_AGENT, expected_user_agent)
        
        # Clean up: Stop patches specific to this test method.
        patch.stopall() 

        # Reload the module with a known default state for subsequent tests.
        # This helps in isolating tests if they don't manage their own environment patching and reloading.
        default_env_vars = {
            "WIKIPEDIA_CORPUS_FILE": "/corpus_data/wikipedia_corpus.txt",
            "WIKIPEDIA_NUM_ARTICLES": "5",
            "WIKIPEDIA_LANGUAGE": "en",
        }
        # Use 'clear=True' to ensure only these environment variables are set during the reload,
        # simulating a fresh environment for the module's default configuration.
        with patch.dict(os.environ, default_env_vars, clear=True):
            importlib.reload(corpus_wikipedia_updater)


class TestCleanText(unittest.TestCase):
    """Tests for the clean_text function."""

    def test_empty_string(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text(""), "")

    def test_non_string_input(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text(None), "") # type: ignore
        self.assertEqual(corpus_wikipedia_updater.clean_text(123), "") # type: ignore

    def test_multiple_newlines(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("a\n\n\nb\n\n\n\nc"), "a\n\nb\n\nc")

    def test_strip_whitespace(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("  hello world  "), "hello world")

    def test_remove_simple_templates(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text {{template}} more text"), "Text  more text")
        self.assertEqual(corpus_wikipedia_updater.clean_text("{{template1}} Text {{template2}}"), " Text ")

    def test_remove_ref_tags(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text<ref name='foo'>citation</ref> more text"), "Text more text")
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text<ref/> more text"), "Text more text")
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text<ref name=\"bar\" /> more text"), "Text more text")

    def test_remove_html_tags(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text <b>bold</b> and <i>italic</i>"), "Text bold and italic")

    def test_remove_category_links(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text [[Category:Science]]"), "Text ")
        self.assertEqual(corpus_wikipedia_updater.clean_text("[[Category:History]] Text"), " Text")

    def test_remove_file_image_links(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text [[File:Example.jpg|thumb|description]] more"), "Text  more")
        self.assertEqual(corpus_wikipedia_updater.clean_text("Text [[Image:Example.png]]"), "Text ")

    def test_remove_bold_italic_markup(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("'''Bold''' and ''italic'' text"), "Bold and italic text")

    def test_remove_section_titles(self):
        self.assertEqual(corpus_wikipedia_updater.clean_text("== Title ==\nContent"), "Content")
        self.assertEqual(corpus_wikipedia_updater.clean_text("Content\n=== SubTitle ===\nMore"), "Content\nMore")
        self.assertEqual(corpus_wikipedia_updater.clean_text("== Title == \nContent"), "Content") # With space

    def test_combined_cleaning(self):
        raw = "  Start\n\n\n{{Infobox person\n| name = Test\n}}\n'''Hello''' ''world''!\n<ref>A citation</ref>\n== Section ==\nThis is [[File:Test.png]] a test.\n[[Category:Tests]]  "
        expected = "Start\n\nHello world!\nThis is  a test."
        self.assertEqual(corpus_wikipedia_updater.clean_text(raw), expected)

    def test_no_change_needed(self):
        text = "This is a perfectly clean sentence."
        self.assertEqual(corpus_wikipedia_updater.clean_text(text), text)


class TestFetchRandomWikipediaAPI(unittest.TestCase):
    """Tests for fetch_random_wikipedia_articles_api."""

    def setUp(self):
        # Patch external dependencies
        self.requests_session_patcher = patch('util.corpus_wikipedia_updater.requests.Session') # Path to requests within the module
        self.mock_session_constructor = self.requests_session_patcher.start()
        self.mock_session = MagicMock()
        self.mock_session_constructor.return_value = self.mock_session

        # Patch the module-level 'wiki_wiki' object's 'page' method
        self.wikipediaapi_patcher = patch('util.corpus_wikipedia_updater.wiki_wiki.page')
        self.mock_wiki_page_call = self.wikipediaapi_patcher.start()

        self.time_sleep_patcher = patch('time.sleep', return_value=None) # Speed up tests
        self.mock_time_sleep = self.time_sleep_patcher.start()
        
        # Default mock responses
        self.mock_session.get.return_value = MockResponse(b"redirected content", 200, "https://en.wikipedia.org/wiki/Test_Page_1")
        self.mock_wiki_page_call.return_value = MockWikiPage("Test_Page_1", "Raw content for Test Page 1")

    def tearDown(self):
        patch.stopall() # Stop all patches started during the test method

    def test_fetch_zero_articles(self):
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log: # Target the correct logger
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(0)
            self.assertEqual(len(articles), 0)
            self.assertIn("Number of articles to fetch is zero or negative. Skipping API fetch.", log.output[0])

    def test_fetch_negative_articles(self):
         with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(-1)
            self.assertEqual(len(articles), 0)
            self.assertIn("Number of articles to fetch is zero or negative. Skipping API fetch.", log.output[0])

    def test_successful_fetch_one_article(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Sample_Article")
        self.mock_wiki_page_call.return_value = MockWikiPage("Sample_Article", "This is sample content.")
        
        articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
        
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0], "This is sample content.")
        self.mock_session.get.assert_called_once_with(
            f"https://{corpus_wikipedia_updater.WIKI_LANGUAGE}.wikipedia.org/wiki/Special:Random",
            allow_redirects=True, timeout=15
        )
        self.mock_wiki_page_call.assert_called_once_with("Sample_Article")
        self.mock_time_sleep.assert_called_once()

    def test_successful_fetch_multiple_articles(self):
        mock_redirect_responses = [
            MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Page_Alpha"),
            MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Page_Beta")
        ]
        mock_wiki_pages = [
            MockWikiPage("Page_Alpha", "Content Alpha"),
            MockWikiPage("Page_Beta", "Content Beta")
        ]
        self.mock_session.get.side_effect = mock_redirect_responses
        self.mock_wiki_page_call.side_effect = mock_wiki_pages

        articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(2)
        self.assertEqual(len(articles), 2)
        self.assertIn("Content Alpha", articles)
        self.assertIn("Content Beta", articles)
        self.assertEqual(self.mock_session.get.call_count, 2)
        self.assertEqual(self.mock_wiki_page_call.call_count, 2)

    def test_skip_non_existent_page(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/NonExistent")
        self.mock_wiki_page_call.return_value = MockWikiPage("NonExistent", "", exists=False)
        
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='INFO') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0) 
            self.assertTrue(any("Page 'NonExistent' does not exist" in msg for msg in log.output))


    def test_skip_category_page(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Category:Stuff")
        self.mock_wiki_page_call.return_value = MockWikiPage("Category:Stuff", "Category content", is_category=True)
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='INFO') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Page 'Category:Stuff' does not exist, is a category, or disambiguation." in msg for msg in log.output))


    def test_skip_disambiguation_page(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Disambig")
        self.mock_wiki_page_call.return_value = MockWikiPage("Disambig", "Disambiguation content", is_disambig=True)
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='INFO') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Page 'Disambig' does not exist, is a category, or disambiguation." in msg for msg in log.output))

    def test_content_empty_after_cleaning(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/EmptyContent")
        self.mock_wiki_page_call.return_value = MockWikiPage("EmptyContent", "{{template}}") 
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Content for page 'EmptyContent' became empty after cleaning." in msg for msg in log.output))

    def test_no_text_content_from_api(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/NoText")
        self.mock_wiki_page_call.return_value = MockWikiPage("NoText", "") 
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("No text content found for page (API): NoText" in msg for msg in log.output))

    def test_requests_timeout_exception(self):
        self.mock_session.get.side_effect = corpus_wikipedia_updater.requests.exceptions.Timeout("Connection timed out")
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Timeout fetching random page URL" in msg for msg in log.output))

    def test_requests_request_exception(self):
        self.mock_session.get.side_effect = corpus_wikipedia_updater.requests.exceptions.RequestException("Network error")
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Request error fetching random page URL: Network error" in msg for msg in log.output))
    
    def test_generic_exception_during_processing(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/ErrorPage")
        self.mock_wiki_page_call.side_effect = Exception("Unexpected processing error")
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Unexpected error processing page 'ErrorPage': Unexpected processing error" in msg for msg in log.output))

    def test_max_attempts_reached(self):
        self.mock_session.get.return_value = MockResponse(b"", 200, "https://en.wikipedia.org/wiki/BadPage")
        self.mock_wiki_page_call.return_value = MockWikiPage("BadPage", "", exists=False) 
        num_to_fetch = 2
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(num_to_fetch)
            self.assertEqual(len(articles), 0)
            self.assertEqual(self.mock_session.get.call_count, num_to_fetch * 3) 
            self.assertTrue(any(f"API fetch: Expected {num_to_fetch} articles, but only got 0" in msg for msg in log.output))

    def test_duplicate_page_titles_are_skipped(self):
        mock_redirect_responses = [
            MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Duplicate_Page"),
            MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Duplicate_Page"), 
            MockResponse(b"", 200, "https://en.wikipedia.org/wiki/Unique_Page")
        ]
        
        def wiki_page_side_effect(title):
            if title == "Duplicate_Page":
                return MockWikiPage("Duplicate_Page", "Content Dup")
            elif title == "Unique_Page":
                return MockWikiPage("Unique_Page", "Content Unique")
            return MockWikiPage(title, "", exists=False)

        self.mock_session.get.side_effect = mock_redirect_responses
        self.mock_wiki_page_call.side_effect = wiki_page_side_effect

        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='DEBUG') as log: 
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_api(2) 
            self.assertEqual(len(articles), 2)
            self.assertIn("Content Dup", articles)
            self.assertIn("Content Unique", articles)
            self.assertEqual(self.mock_session.get.call_count, 3)
            self.assertEqual(self.mock_wiki_page_call.call_count, 2) 
            self.assertTrue(any("Already fetched 'Duplicate_Page'. Skipping." in msg for msg in log.output))


class TestFetchRandomWikipediaScrape(unittest.TestCase):
    """Tests for fetch_random_wikipedia_articles_scrape."""

    def setUp(self):
        self.requests_session_patcher = patch('util.corpus_wikipedia_updater.requests.Session')
        self.mock_session_constructor = self.requests_session_patcher.start()
        self.mock_session = MagicMock()
        self.mock_session_constructor.return_value = self.mock_session

        self.beautifulsoup_patcher = patch('util.corpus_wikipedia_updater.BeautifulSoup') # Path to BS within the module
        self.mock_bs_constructor = self.beautifulsoup_patcher.start()
        self.mock_soup = MagicMock(spec=corpus_wikipedia_updater.BeautifulSoup) 
        self.mock_bs_constructor.return_value = self.mock_soup

        self.time_sleep_patcher = patch('time.sleep', return_value=None)
        self.mock_time_sleep = self.time_sleep_patcher.start()
        
        self.mock_session.get.return_value = MockResponse(
            b"<html><body><h1 id='firstHeading'>Scrape Page Title</h1><div class='mw-parser-output'><p>Scraped content.</p></div></body></html>",
            200,
            "https://en.wikipedia.org/wiki/Scrape_Page_1"
        )
        
        mock_title_tag_scrape = MockBeautifulSoupTag(text="Scrape Page Title", name='h1')
        self.mock_p_tag_scrape = MockBeautifulSoupTag(text="Scraped content.", name='p')
        self.mock_content_div_scrape = MockBeautifulSoupTag(name='div', children=[self.mock_p_tag_scrape])

        def soup_find_side_effect_scrape(name=None, id=None, class_=None):
            if name == 'h1' and id == 'firstHeading':
                return mock_title_tag_scrape
            if name == 'div' and class_ == 'mw-parser-output':
                return self.mock_content_div_scrape
            return None
        
        def content_div_find_all_side_effect_scrape(names, class_=None):
            found_children = []
            if isinstance(names, list):
                for child in self.mock_content_div_scrape.children: # type: ignore
                    if child.name in names:
                        found_children.append(child)
            return found_children

        self.mock_soup.find.side_effect = soup_find_side_effect_scrape
        self.mock_content_div_scrape.find_all = MagicMock(side_effect=content_div_find_all_side_effect_scrape) # type: ignore


    def tearDown(self):
        patch.stopall()

    def test_fetch_zero_articles_scrape(self):
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(0)
            self.assertEqual(len(articles), 0)
            self.assertIn("Number of articles to fetch is zero or negative. Skipping scrape fetch.", log.output[0])

    def test_successful_scrape_one_article(self):
        articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0], "Scraped content.")
        self.mock_session.get.assert_called_once()
        self.mock_bs_constructor.assert_called_once()
        self.mock_time_sleep.assert_called_once()
        self.mock_content_div_scrape.find_all.assert_any_call(['p', 'li', 'h2', 'h3', 'h4']) # type: ignore


    def test_scrape_content_empty_after_cleaning(self):
        self.mock_p_tag_scrape._text = "{{template}}" 
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Scraped content for page 'Scrape Page Title' became empty after cleaning." in msg for msg in log.output))

    def test_scrape_no_paragraph_list_heading_text(self):
        self.mock_content_div_scrape.children = [] # type: ignore
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("No paragraph, list, or heading text found for page (scrape): Scrape Page Title" in msg for msg in log.output))

    def test_scrape_main_content_div_not_found(self):
        self.mock_soup.find.side_effect = lambda name, id=None, class_=None: \
            MockBeautifulSoupTag(text="No Div Page", name='h1') if name == 'h1' else \
            None 
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Could not find main content div for page (scrape): No Div Page" in msg for msg in log.output))
            
    def test_scrape_title_tag_not_found(self):
        self.mock_session.get.return_value = MockResponse(
            b"<html><body><div class='mw-parser-output'><p>Content</p></div></body></html>",
            200, "https://en.wikipedia.org/wiki/Title_From_URL_Scrape"
        )
        self.mock_soup.find.side_effect = lambda name, id=None, class_=None: \
            None if name == 'h1' and id == 'firstHeading' else \
            self.mock_content_div_scrape if (name=='div' and class_=='mw-parser-output') else None
        
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='INFO') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
            self.assertEqual(len(articles), 1)
            self.assertEqual(articles[0], "Scraped content.") 
            self.assertTrue(any("Scraped and cleaned content for: Title_From_URL_Scrape" in msg for msg in log.output))


    def test_scrape_requests_timeout_exception(self):
        self.mock_session.get.side_effect = corpus_wikipedia_updater.requests.exceptions.Timeout("Scrape timed out")
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Timeout scraping random page." in msg for msg in log.output))

    def test_scrape_requests_request_exception(self):
        self.mock_session.get.side_effect = corpus_wikipedia_updater.requests.exceptions.RequestException("Scrape network error")
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Request error during scraping: Scrape network error" in msg for msg in log.output))

    def test_scrape_generic_exception(self):
        self.mock_session.get.side_effect = Exception("Generic scrape error") 
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log:
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(1)
            self.assertEqual(len(articles), 0)
            self.assertTrue(any("Unexpected error scraping page 'Unknown Title': Generic scrape error" in msg for msg in log.output))
            
    def test_scrape_max_attempts_reached(self):
        self.mock_session.get.side_effect = corpus_wikipedia_updater.requests.exceptions.Timeout("Scrape timed out")
        num_to_fetch = 1
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='WARNING') as log: 
            articles = corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape(num_to_fetch)
            self.assertEqual(len(articles), 0)
            self.assertEqual(self.mock_session.get.call_count, num_to_fetch * 3)
            self.assertTrue(any(f"Scrape fetch: Expected {num_to_fetch} articles, but only got 0" in msg for msg in log.output))


class TestUpdateCorpusFile(unittest.TestCase):
    """Tests for update_corpus_file."""

    def setUp(self):
        self.original_corpus_output_file = corpus_wikipedia_updater.CORPUS_OUTPUT_FILE
        corpus_wikipedia_updater.CORPUS_OUTPUT_FILE = "/fake/dir/corpus.txt" 

    def tearDown(self):
        corpus_wikipedia_updater.CORPUS_OUTPUT_FILE = self.original_corpus_output_file
        patch.stopall()


    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_successful_update(self, mock_file_open, mock_makedirs):
        content_list = ["Article 1 content.", "Article 2 content."]
        
        result = corpus_wikipedia_updater.update_corpus_file(content_list)
        
        self.assertTrue(result)
        mock_makedirs.assert_called_once_with("/fake/dir", exist_ok=True)
        mock_file_open.assert_called_once_with("/fake/dir/corpus.txt", "a", encoding="utf-8")
        
        handle = mock_file_open()
        expected_calls = [
            call("\n\n--- Article 1 ---\n"),
            call("Article 1 content.\n"),
            call("\n\n--- Article 2 ---\n"),
            call("Article 2 content.\n")
        ]
        handle.write.assert_has_calls(expected_calls)

    def test_no_content_to_add(self):
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='INFO') as log:
            result = corpus_wikipedia_updater.update_corpus_file([])
            self.assertFalse(result) 
            self.assertIn("No new content to add to corpus file.", log.output[0])

    @patch('os.makedirs')
    @patch('builtins.open', side_effect=IOError("Disk full"))
    def test_io_error_writing_file(self, mock_file_open_error, mock_makedirs):
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log:
            result = corpus_wikipedia_updater.update_corpus_file(["Content"])
            self.assertFalse(result)
            self.assertTrue(any("IOError writing to corpus file /fake/dir/corpus.txt: Disk full" in msg for msg in log.output))

    @patch('os.makedirs', side_effect=OSError("Permission denied to create dir"))
    def test_os_error_creating_directory(self, mock_makedirs_error):
        with self.assertLogs(logger='util.corpus_wikipedia_updater', level='ERROR') as log: 
             result = corpus_wikipedia_updater.update_corpus_file(["Content"])
             self.assertFalse(result) 
             self.assertTrue(any(f"Unexpected error updating corpus file {corpus_wikipedia_updater.CORPUS_OUTPUT_FILE}: Permission denied to create dir" in msg for msg in log.output))


class TestMainExecution(unittest.TestCase):
    """Tests for the __main__ execution block by simulating its logic."""

    def setUp(self):
        self.mock_fetch_api: MagicMock = patch('util.corpus_wikipedia_updater.fetch_random_wikipedia_articles_api').start()
        self.mock_fetch_scrape: MagicMock = patch('util.corpus_wikipedia_updater.fetch_random_wikipedia_articles_scrape').start()
        self.mock_update_corpus: MagicMock = patch('util.corpus_wikipedia_updater.update_corpus_file').start()
        self.mock_os_makedirs: MagicMock = patch('util.corpus_wikipedia_updater.os.makedirs').start() 
        self.mock_os_path_exists: MagicMock = patch('util.corpus_wikipedia_updater.os.path.exists').start()
        
        self.mock_logging_info: MagicMock = patch('util.corpus_wikipedia_updater.logging.info').start()
        self.mock_logging_warning: MagicMock = patch('util.corpus_wikipedia_updater.logging.warning').start()
        self.mock_logging_error: MagicMock = patch('util.corpus_wikipedia_updater.logging.error').start()
        self.mock_logging_critical: MagicMock = patch('util.corpus_wikipedia_updater.logging.critical').start()
        
        self.original_num_articles = corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH
        self.original_corpus_file = corpus_wikipedia_updater.CORPUS_OUTPUT_FILE
        
        corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH = 2 
        corpus_wikipedia_updater.CORPUS_OUTPUT_FILE = "/test_corpus_main/main_test.txt"


    def tearDown(self):
        patch.stopall()
        corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH = self.original_num_articles
        corpus_wikipedia_updater.CORPUS_OUTPUT_FILE = self.original_corpus_file
        importlib.reload(corpus_wikipedia_updater)


    def run_simulated_main(self):
        """Simulates the execution flow of the script's __main__ block."""
        corpus_wikipedia_updater.logging.info("Wikipedia Corpus Updater Job starting...")

        run_success_main = False
        
        corpus_dir = os.path.dirname(corpus_wikipedia_updater.CORPUS_OUTPUT_FILE)
        # Use the patched os.path.exists
        if corpus_dir and not corpus_wikipedia_updater.os.path.exists(corpus_dir): 
            try:
                corpus_wikipedia_updater.os.makedirs(corpus_dir) 
                corpus_wikipedia_updater.logging.info(f"Created corpus directory: {corpus_dir}")
            except OSError as e:
                corpus_wikipedia_updater.logging.error(f"Could not create directory for corpus file {corpus_wikipedia_updater.CORPUS_OUTPUT_FILE}: {e}. Exiting.")
                if isinstance(e,type(self.mock_os_makedirs.side_effect)): 
                    return "makedirs_failed" 

        fetched_articles_main = []
        try:
            api_articles = self.mock_fetch_api(corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH)
            if api_articles: fetched_articles_main.extend(api_articles)
            
            if not fetched_articles_main or len(fetched_articles_main) < corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH:
                needed_more = corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH - len(fetched_articles_main)
                corpus_wikipedia_updater.logging.info(f"API fetch yielded {len(fetched_articles_main)} articles. Attempting to fetch {needed_more} more using scraping as fallback.")
                if needed_more > 0:
                    scrape_articles = self.mock_fetch_scrape(needed_more)
                    if scrape_articles: fetched_articles_main.extend(scrape_articles)

        except Exception as e_fetch: 
            corpus_wikipedia_updater.logging.critical(f"Unhandled exception during article fetching: {e_fetch}", exc_info=True)

        if fetched_articles_main:
            if self.mock_update_corpus(fetched_articles_main):
                corpus_wikipedia_updater.logging.info(f"Corpus update successful. Added {len(fetched_articles_main)} articles.")
                run_success_main = True
            else:
                corpus_wikipedia_updater.logging.error("Corpus file update failed after fetching articles.")
        else:
            corpus_wikipedia_updater.logging.warning("No articles were fetched from any source. Corpus file not updated.")

        if run_success_main:
            corpus_wikipedia_updater.logging.info("Wikipedia Corpus Updater Job finished successfully.")
        else:
            corpus_wikipedia_updater.logging.error("Wikipedia Corpus Updater Job finished with errors or no content updated.")
        return run_success_main


    def test_main_success_api_only(self):
        self.mock_os_path_exists.return_value = True 
        self.mock_fetch_api.return_value = ["API Article 1", "API Article 2"]
        self.mock_update_corpus.return_value = True

        result = self.run_simulated_main()
        self.assertTrue(result)
        
        self.mock_fetch_api.assert_called_once_with(2) 
        self.mock_fetch_scrape.assert_not_called()
        self.mock_update_corpus.assert_called_once_with(["API Article 1", "API Article 2"])
        self.mock_logging_info.assert_any_call("Wikipedia Corpus Updater Job finished successfully.")


    def test_main_success_api_and_scrape_fallback(self):
        self.mock_os_path_exists.return_value = True
        self.mock_fetch_api.return_value = ["API Article 1"] 
        self.mock_fetch_scrape.return_value = ["Scrape Article 1"]
        self.mock_update_corpus.return_value = True
        
        result = self.run_simulated_main()
        self.assertTrue(result)

        self.mock_fetch_api.assert_called_once_with(2)
        self.mock_logging_info.assert_any_call(f"API fetch yielded 1 articles. Attempting to fetch 1 more using scraping as fallback.")
        self.mock_fetch_scrape.assert_called_once_with(1) 
        self.mock_update_corpus.assert_called_once_with(["API Article 1", "Scrape Article 1"])


    def test_main_directory_creation(self):
        self.mock_os_path_exists.return_value = False 
        self.mock_fetch_api.return_value = ["Article"]
        self.mock_update_corpus.return_value = True

        result = self.run_simulated_main()
        self.assertTrue(result)
        self.mock_os_makedirs.assert_called_once_with(os.path.dirname(corpus_wikipedia_updater.CORPUS_OUTPUT_FILE))
        self.mock_logging_info.assert_any_call(f"Created corpus directory: {os.path.dirname(corpus_wikipedia_updater.CORPUS_OUTPUT_FILE)}")


    @patch('util.corpus_wikipedia_updater.sys.exit') 
    def test_main_directory_creation_failure(self, mock_sys_exit):
        self.mock_os_path_exists.return_value = False # Directory does not exist
        # Configure the mock_os_makedirs (which is corpus_wikipedia_updater.os.makedirs) to raise an error
        self.mock_os_makedirs.side_effect = OSError("Cannot create dir")
                
        result = self.run_simulated_main() 
        self.assertEqual(result, "makedirs_failed")

        self.mock_logging_error.assert_any_call(f"Could not create directory for corpus file {corpus_wikipedia_updater.CORPUS_OUTPUT_FILE}: Cannot create dir. Exiting.")
        # The original script calls sys.exit(1). Our simulation returns "makedirs_failed".
        # If we were testing the *actual* script execution (e.g. with runpy), we'd assert mock_sys_exit.called_with(1).


    def test_main_no_articles_fetched(self):
        self.mock_os_path_exists.return_value = True
        self.mock_fetch_api.return_value = [] 
        self.mock_fetch_scrape.return_value = [] 
        
        result = self.run_simulated_main()
        self.assertFalse(result) 
        
        self.mock_update_corpus.assert_not_called() 
        self.mock_logging_warning.assert_any_call("No articles were fetched from any source. Corpus file not updated.")
        self.mock_logging_error.assert_any_call("Wikipedia Corpus Updater Job finished with errors or no content updated.")


    def test_main_update_corpus_fails(self):
        self.mock_os_path_exists.return_value = True
        self.mock_fetch_api.return_value = ["Article"]
        self.mock_update_corpus.return_value = False 
        
        result = self.run_simulated_main()
        self.assertFalse(result)

        self.mock_update_corpus.assert_called_once_with(["Article"])
        self.mock_logging_error.assert_any_call("Corpus file update failed after fetching articles.")


    def test_main_api_fetch_raises_critical_exception(self):
        self.mock_os_path_exists.return_value = True
        self.mock_fetch_api.side_effect = Exception("Critical API failure")
        self.mock_fetch_scrape.return_value = ["Scrape Fallback Article"] 
        self.mock_update_corpus.return_value = True

        result = self.run_simulated_main()
        self.assertTrue(result) 

        self.mock_logging_critical.assert_any_call("Unhandled exception during article fetching: Critical API failure", exc_info=True)
        self.mock_fetch_scrape.assert_called_once_with(corpus_wikipedia_updater.NUM_ARTICLES_TO_FETCH) 
        self.mock_update_corpus.assert_called_once_with(["Scrape Fallback Article"])


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)


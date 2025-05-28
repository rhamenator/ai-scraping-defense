# anti-scraping-defense/util/corpus_wikipedia_updater.py
import os
import time
import random
import logging
import re # Added missing import
import requests
from bs4 import BeautifulSoup # For HTML parsing
import wikipediaapi # For a more structured API access
from urllib.parse import unquote

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s', # More detailed format
    handlers=[logging.StreamHandler()]
)

# --- Configuration ---
CORPUS_OUTPUT_FILE = os.getenv("WIKIPEDIA_CORPUS_FILE", "/corpus_data/wikipedia_corpus.txt")
NUM_ARTICLES_TO_FETCH = int(os.getenv("WIKIPEDIA_NUM_ARTICLES", 5))
WIKI_LANGUAGE = os.getenv("WIKIPEDIA_LANGUAGE", "en")
REQUESTS_USER_AGENT = f"CorpusUpdater/1.1 (AI-Scraping-Defense; +https://github.com/your-repo/ai-scraping-defense; process/{os.getpid()})" # Added process ID

# Wikipedia API setup
wiki_wiki = wikipediaapi.Wikipedia(
    language=WIKI_LANGUAGE,
    extract_format=wikipediaapi.ExtractFormat.WIKI,
    user_agent=REQUESTS_USER_AGENT
)

def clean_text(text_content: str) -> str:
    """Basic text cleaning."""
    if not isinstance(text_content, str):
        return ""
    text_content = re.sub(r'\n{3,}', '\n\n', text_content)
    text_content = text_content.strip()
    # Further cleaning for wikitext can be extensive. Examples:
    # Remove {{...}} templates (can be nested and complex)
    text_content = re.sub(r'\{\{[^\{]*?\}\}', '', text_content) # Simple, non-greedy template removal
    # Remove <ref...> tags
    text_content = re.sub(r'<ref[^>]*?>.*?</ref>', '', text_content, flags=re.IGNORECASE | re.DOTALL)
    text_content = re.sub(r'<ref[^>]*?/>', '', text_content, flags=re.IGNORECASE)
    # Remove basic HTML tags if any slip through (though extract_format=WIKI should minimize this)
    text_content = re.sub(r'<[^>]+>', '', text_content)
    # Remove category links like [[Category:...]]
    text_content = re.sub(r'\[\[Category:[^\]]+\]\]', '', text_content, flags=re.IGNORECASE)
    # Remove file/image links like [[File:...]] or [[Image:...]]
    text_content = re.sub(r'\[\[(File|Image):[^\]]+\]\]', '', text_content, flags=re.IGNORECASE)
    # Remove '''bold''' and ''italic'' markup
    text_content = text_content.replace("'''", "").replace("''", "")
    # Remove ==Section Titles==
    text_content = re.sub(r'^==+[^=]+==+\s*$', '', text_content, flags=re.MULTILINE)
    return text_content.strip()

def fetch_random_wikipedia_articles_api(num_articles: int) -> list[str]:
    """Fetches content from random Wikipedia pages using the API."""
    articles_content = []
    if not num_articles or num_articles <= 0:
        logging.warning("Number of articles to fetch is zero or negative. Skipping API fetch.")
        return articles_content

    logging.info(f"Attempting to fetch {num_articles} random Wikipedia articles using API ({WIKI_LANGUAGE})...")
    session = requests.Session()
    session.headers.update({"User-Agent": REQUESTS_USER_AGENT})
    fetched_titles = set()
    attempts = 0
    max_attempts = num_articles * 3 # Try more times to get the desired number of unique articles

    while len(fetched_titles) < num_articles and attempts < max_attempts:
        attempts += 1
        page_title_from_url = "" # Initialize for logging in case of early error
        random_url = f"https://{WIKI_LANGUAGE}.wikipedia.org/wiki/Special:Random"
        try:
            response = session.get(random_url, allow_redirects=True, timeout=15) # Increased timeout
            response.raise_for_status()
            
            page_title_from_url = unquote(response.url.split('/')[-1]) # Decode URL-encoded titles

            if page_title_from_url and page_title_from_url not in fetched_titles:
                logging.debug(f"Random page identified: {page_title_from_url}")
                page = wiki_wiki.page(page_title_from_url)
                
                if page.exists() and not page.is_categorypage and not page.is_disambigpage:
                    content = page.text
                    if content:
                        cleaned_content = clean_text(content)
                        if cleaned_content: # Ensure content remains after cleaning
                            articles_content.append(cleaned_content)
                            fetched_titles.add(page_title_from_url)
                            logging.info(f"Fetched and cleaned content for: {page.title} (Original length: {len(content)}, Cleaned length: {len(cleaned_content)})")
                        else:
                            logging.warning(f"Content for page '{page.title}' became empty after cleaning.")
                    else:
                        logging.warning(f"No text content found for page (API): {page.title}")
                else:
                    logging.info(f"Page '{page_title_from_url}' does not exist, is a category, or disambiguation. Skipping.")
            elif page_title_from_url in fetched_titles:
                logging.debug(f"Already fetched '{page_title_from_url}'. Skipping.")

            time.sleep(random.uniform(1.0, 2.5)) # Be polite
        except requests.exceptions.Timeout:
            logging.error(f"Timeout fetching random page URL ({random_url if 'random_url' in locals() else 'N/A'}). Attempt {attempts}/{max_attempts}.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error fetching random page URL: {e}. Attempt {attempts}/{max_attempts}.")
        except Exception as e:
            logging.error(f"Unexpected error processing page '{page_title_from_url}': {e}. Attempt {attempts}/{max_attempts}.", exc_info=True)
            
    if len(fetched_titles) < num_articles:
        logging.warning(f"API fetch: Expected {num_articles} articles, but only got {len(fetched_titles)} after {max_attempts} attempts.")
    return articles_content # Return whatever was successfully fetched

def fetch_random_wikipedia_articles_scrape(num_articles: int) -> list[str]:
    """Fallback: Fetches content using requests and BeautifulSoup."""
    articles_content = []
    if not num_articles or num_articles <= 0:
        logging.warning("Number of articles to fetch is zero or negative. Skipping scrape fetch.")
        return articles_content

    logging.info(f"Attempting to fetch {num_articles} random Wikipedia articles using scraping ({WIKI_LANGUAGE})...")
    session = requests.Session()
    session.headers.update({"User-Agent": REQUESTS_USER_AGENT})
    fetched_count = 0
    attempts = 0
    max_attempts = num_articles * 3

    while fetched_count < num_articles and attempts < max_attempts:
        attempts += 1
        page_title_text = "Unknown Title"
        try:
            random_url = f"https://{WIKI_LANGUAGE}.wikipedia.org/wiki/Special:Random"
            response = session.get(random_url, timeout=15, allow_redirects=True)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            page_title_tag = soup.find('h1', id='firstHeading')
            page_title_text = page_title_tag.text.strip() if page_title_tag else unquote(response.url.split('/')[-1])

            content_div = soup.find('div', class_='mw-parser-output')
            from bs4.element import Tag
            if isinstance(content_div, Tag):
                for unwanted_tag in content_div.find_all(['table', 'div', 'span', 'style', 'script'], 
                                                         class_=['infobox', 'navbox', 'metadata', 'mw-editsection', 
                                                                 'reflist', 'reference', 'noprint', 'mw-references',
                                                                 'gallery', 'sistersitebox', 'toc']): # Added more classes
                    unwanted_tag.decompose()
                for sup_tag in content_div.find_all('sup', class_='reference'):
                    sup_tag.decompose()
                
                # Get text from paragraphs, lists, and headings to capture more content
                page_text_elements = []
                for element in content_div.find_all(['p', 'li', 'h2', 'h3', 'h4']):
                    text = element.get_text(separator=" ", strip=True)
                    if text:
                        page_text_elements.append(text)
                
                page_text = "\n\n".join(page_text_elements)
                
                if page_text:
                    cleaned_content = clean_text(page_text) # Basic cleaning for scraped HTML text
                    if cleaned_content:
                        articles_content.append(cleaned_content)
                        fetched_count += 1
                        logging.info(f"Scraped and cleaned content for: {page_title_text} (Length: {len(cleaned_content)})")
                    else:
                        logging.warning(f"Scraped content for page '{page_title_text}' became empty after cleaning.")
                else:
                    logging.warning(f"No paragraph, list, or heading text found for page (scrape): {page_title_text}")
            else:
                logging.warning(f"Could not find main content div for page (scrape): {page_title_text}")

            time.sleep(random.uniform(1.5, 3.0))  # Be polite, slightly longer for scraping
        except requests.exceptions.Timeout:
            logging.error(f"Timeout scraping random page. Attempt {attempts}/{max_attempts}.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error during scraping: {e}. Attempt {attempts}/{max_attempts}.")
        except Exception as e:
            logging.error(f"Unexpected error scraping page '{page_title_text}': {e}. Attempt {attempts}/{max_attempts}.", exc_info=True)

    if fetched_count < num_articles:
        logging.warning(f"Scrape fetch: Expected {num_articles} articles, but only got {fetched_count} after {max_attempts} attempts.")
    return articles_content

def update_corpus_file(new_content_list: list[str]):
    """Appends new content to the corpus file."""
    if not new_content_list:
        logging.info("No new content to add to corpus file.")
        return False # Indicate no update was made

    try:
        output_dir = os.path.dirname(CORPUS_OUTPUT_FILE)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(CORPUS_OUTPUT_FILE, "a", encoding="utf-8") as f:
            for i, content_block in enumerate(new_content_list):
                f.write(f"\n\n--- Article {i+1} ---\n") # Add a separator
                f.write(content_block.strip() + "\n")
        logging.info(f"Successfully appended {len(new_content_list)} articles to {CORPUS_OUTPUT_FILE}")
        return True # Indicate success
    except IOError as e:
        logging.error(f"IOError writing to corpus file {CORPUS_OUTPUT_FILE}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error updating corpus file {CORPUS_OUTPUT_FILE}: {e}", exc_info=True)
    return False # Indicate failure

if __name__ == "__main__":
    logging.info("Wikipedia Corpus Updater Job starting...")
    run_success = False
    
    # Ensure the target directory for the corpus exists
    corpus_dir = os.path.dirname(CORPUS_OUTPUT_FILE)
    if corpus_dir and not os.path.exists(corpus_dir):
        try:
            os.makedirs(corpus_dir)
            logging.info(f"Created corpus directory: {corpus_dir}")
        except OSError as e:
            logging.error(f"Could not create directory for corpus file {CORPUS_OUTPUT_FILE}: {e}. Exiting.")
            exit(1) # Critical error, cannot proceed
    
    fetched_articles = []
    try:
        # Prefer API method
        fetched_articles = fetch_random_wikipedia_articles_api(NUM_ARTICLES_TO_FETCH)
        
        if not fetched_articles or len(fetched_articles) < NUM_ARTICLES_TO_FETCH:
            needed_more = NUM_ARTICLES_TO_FETCH - len(fetched_articles)
            logging.info(f"API fetch yielded {len(fetched_articles)} articles. Attempting to fetch {needed_more} more using scraping as fallback.")
            if needed_more > 0:
                fallback_articles = fetch_random_wikipedia_articles_scrape(needed_more)
                fetched_articles.extend(fallback_articles)
    except Exception as e:
        logging.critical(f"Unhandled exception during article fetching: {e}", exc_info=True)
        # Optionally, try scraping as a last resort if API part fails catastrophically
        # if not fetched_articles:
        #    logging.info("Main API fetch failed. Attempting full scrape as fallback.")
        #    fetched_articles = fetch_random_wikipedia_articles_scrape(NUM_ARTICLES_TO_FETCH)


    if fetched_articles:
        if update_corpus_file(fetched_articles):
            logging.info(f"Corpus update successful. Added {len(fetched_articles)} articles.")
            run_success = True
        else:
            logging.error("Corpus file update failed after fetching articles.")
    else:
        logging.warning("No articles were fetched from any source. Corpus file not updated.")

    if run_success:
        logging.info("Wikipedia Corpus Updater Job finished successfully.")
    else:
        logging.error("Wikipedia Corpus Updater Job finished with errors or no content updated.")
    #   # For a CronJob, exiting with an error code 
    #   exit(1) 
    # else:
    #     logging.info("Wikipedia Corpus Updater Job finished without errors, but no content was updated.")
    #     exit(0) # Indicate success even if no new content was added
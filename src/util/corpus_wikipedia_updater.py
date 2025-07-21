# util/corpus_wikipedia_updater.py
import os
import sys
import logging
import re
import time
import wikipedia
from wikipedia.exceptions import DisambiguationError, PageError

# Set up basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# No longer necessary with correct PYTHONPATH
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Configuration ---
# Set the language for Wikipedia
wikipedia.set_lang("en")

# Number of articles to fetch in each run
NUM_ARTICLES_TO_FETCH = int(os.getenv("CORPUS_ARTICLES_TO_FETCH", 50))

# Path to the output corpus file
CORPUS_OUTPUT_FILE = os.getenv("CORPUS_FILE_PATH", "/app/data/wikipedia_corpus.txt")

# Define categories to skip (e.g., lists, disambiguation pages)
DISALLOWED_CATEGORIES = [
    "disambiguation",
    "lists of",
    "articles with",
    "pages needing",
    "living people",
    "deaths in",
    "births in",
]


def clean_text(text: str) -> str:
    """
    Cleans the raw text from a Wikipedia article by removing templates,
    references, and other noisy elements.
    """
    # Remove templates, citations, and file links
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[File:.*?\]\]", "", text, flags=re.DOTALL)

    # Remove section headers
    text = re.sub(r"^==+[^=]+==+\s*", "", text, flags=re.MULTILINE)

    # Remove bold/italic markup and leading list markers
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"^\*\s*", "", text, flags=re.MULTILINE)

    # Replace newlines with spaces and collapse excessive spaces (but keep pairs)
    text = text.replace("\n", " ")
    text = re.sub(r" {3,}", "  ", text)

    return text.strip()


def fetch_random_wikipedia_articles(num_articles: int) -> list[str]:
    """
    Fetches and processes a specified number of random Wikipedia articles.

    Args:
        num_articles: The number of articles to fetch.

    Returns:
        A list of cleaned article content.
    """
    fetched_articles: list[str] = []
    attempts = 0
    max_attempts = num_articles * 3  # Set a reasonable limit on attempts

    logger.info(f"Attempting to fetch {num_articles} valid Wikipedia articles.")

    while len(fetched_articles) < num_articles and attempts < max_attempts:
        attempts += 1
        try:
            # Fetch a random article title
            random_title = wikipedia.random(pages=1)

            # Get the page object
            page = wikipedia.page(random_title, auto_suggest=False, redirect=True)

            # Skip if any category is disallowed
            if any(
                any(dis in cat.lower() for dis in DISALLOWED_CATEGORIES)
                for cat in page.categories
            ):
                logger.debug(f"Skipping '{page.title}' due to disallowed category.")
                continue

            # Clean the content and add to list if it's substantial
            cleaned_content = clean_text(page.content)
            if (
                cleaned_content and len(cleaned_content) > 500
            ):  # Ensure article has some length
                fetched_articles.append(cleaned_content)
                logger.info(
                    f"Successfully fetched and cleaned '{page.title}' ({len(fetched_articles)}/{num_articles})."
                )

            time.sleep(0.5)  # Be polite to the API

        except DisambiguationError as e:
            logger.warning(f"Skipping '{e.title}' because it's a disambiguation page.")
        except PageError:
            logger.warning(f"Could not find a page for a random title, skipping.")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while fetching an article: {e}",
                exc_info=True,
            )
            time.sleep(2)  # Wait a bit longer after an unexpected error

    return fetched_articles


def update_corpus_file(articles: list[str]):
    """
    Appends a list of articles to the corpus file.

    Args:
        articles: A list of cleaned article strings.
    """
    if not articles:
        logger.info("No new articles to add to the corpus file.")
        return

    try:
        # Ensure the directory exists
        output_dir = os.path.dirname(CORPUS_OUTPUT_FILE)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Append the new articles to the file
        with open(CORPUS_OUTPUT_FILE, "a", encoding="utf-8") as f:
            for article in articles:
                f.write(article + "\n")

        logger.info(
            f"Successfully added {len(articles)} new articles to {CORPUS_OUTPUT_FILE}."
        )

    except IOError as e:
        logger.error(f"Failed to write to corpus file {CORPUS_OUTPUT_FILE}: {e}")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during file update: {e}", exc_info=True
        )


def main():
    """Main execution function."""
    logger.info("--- Wikipedia Corpus Updater Started ---")
    articles = fetch_random_wikipedia_articles(NUM_ARTICLES_TO_FETCH)
    update_corpus_file(articles)
    logger.info("--- Wikipedia Corpus Updater Finished ---")


def main():
    """Main execution function."""
    logger.info("--- Wikipedia Corpus Updater Started ---")
    articles = fetch_random_wikipedia_articles(NUM_ARTICLES_TO_FETCH)
    update_corpus_file(articles)
    logger.info("--- Wikipedia Corpus Updater Finished ---")


if __name__ == "__main__":
    main()

# anti_scrape/tarpit/markov_generator.py
# Generates deterministic fake HTML content using Markov chains from PostgreSQL.

import psycopg2
from psycopg2 import pool
import os
import random
import string
import datetime
import logging
import hashlib
import html

from src.shared.model_provider import get_model_adapter

logger = logging.getLogger(__name__)

try:
    from tarpit_rs import (
        generate_dynamic_tarpit_page as rs_generate_dynamic_tarpit_page,
    )

    RUST_ENABLED = True
    logger.info("tarpit_rs module loaded; using Rust implementation where possible.")
except Exception as e:
    rs_generate_dynamic_tarpit_page = None
    RUST_ENABLED = False
    logger.warning(
        f"Could not import tarpit_rs: {e}. Falling back to Python implementation."
    )

# --- Configuration ---
DEFAULT_SENTENCES_PER_PAGE = int(os.getenv("DEFAULT_SENTENCES_PER_PAGE", 15))
FAKE_LINK_COUNT = int(
    os.getenv("FAKE_LINK_COUNT", 7)
)  # Increased link count for maze effect
FAKE_LINK_DEPTH = int(
    os.getenv("FAKE_LINK_DEPTH", 3)
)  # Max directory depth for fake links
MIN_WORDS_FOR_NEXT = 2  # Need at least 2 words history for state_size=2 model

# LLM generator configuration
ENABLE_TARPIT_LLM_GENERATOR = (
    os.getenv("ENABLE_TARPIT_LLM_GENERATOR", "false").lower() == "true"
)
TARPIT_LLM_MODEL_URI = os.getenv("TARPIT_LLM_MODEL_URI")
TARPIT_LLM_MAX_TOKENS = int(os.getenv("TARPIT_LLM_MAX_TOKENS", 400))

LLM_ADAPTER = None
if ENABLE_TARPIT_LLM_GENERATOR and TARPIT_LLM_MODEL_URI:
    try:
        LLM_ADAPTER = get_model_adapter(TARPIT_LLM_MODEL_URI)
        if LLM_ADAPTER:
            logger.info(f"LLM adapter initialized for {TARPIT_LLM_MODEL_URI}")
        else:
            logger.error(
                "Failed to initialize LLM adapter; falling back to Markov generator"
            )
    except Exception as e:
        logger.error(f"Error initializing LLM adapter: {e}")
        LLM_ADAPTER = None

# --- Database Connection (Assuming sync psycopg2 for simplicity) ---
PG_HOST = os.getenv("PG_HOST", "postgres")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DBNAME = os.getenv("PG_DBNAME", "markovdb")
PG_USER = os.getenv("PG_USER", "markovuser")
PG_PASSWORD_FILE = os.getenv("PG_PASSWORD_FILE", "/run/secrets/pg_password")

_db_pool = None


def _get_pg_password():
    """Loads password from secret file."""
    try:
        if not os.path.exists(PG_PASSWORD_FILE):
            raise FileNotFoundError(f"Password file {PG_PASSWORD_FILE} not found")

        with open(PG_PASSWORD_FILE, "r") as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Failed to read PostgreSQL password from {PG_PASSWORD_FILE}: {e}")
        return None


def _get_db_pool():
    """Creates or returns the global connection pool."""
    global _db_pool
    if _db_pool:
        return _db_pool

    logger.info(
        f"Initializing PostgreSQL connection pool: {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}"
    )
    pg_password = _get_pg_password()
    if not pg_password:
        logger.error("PostgreSQL password not available. Cannot connect.")
        return None

    try:
        _db_pool = pool.SimpleConnectionPool(
            1,
            5,
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DBNAME,
            user=PG_USER,
            password=pg_password,
            connect_timeout=5,
        )
        logger.info("PostgreSQL connection pool initialized.")
        return _db_pool
    except psycopg2.OperationalError as e:
        logger.error(f"ERROR: Failed to initialize PostgreSQL pool: {e}")
        _db_pool = None
        return None
    except Exception as e:
        logger.error(f"ERROR: Unexpected error initializing PostgreSQL pool: {e}")
        _db_pool = None
        return None


def _get_db_connection():
    """Fetches a connection and cursor from the pool."""
    db_pool = _get_db_pool()
    if not db_pool:
        return None, None
    try:
        conn = db_pool.getconn()
        return conn, conn.cursor()
    except Exception as e:
        logger.error(f"ERROR: Failed to obtain PostgreSQL connection: {e}")
        return None, None


def _release_db_connection(conn, cursor):
    """Return a connection to the pool and close its cursor."""
    if cursor:
        try:
            cursor.close()
        except Exception as e:  # pragma: no cover - log unexpected errors
            logger.error(f"Error closing cursor: {e}")
    if conn and _db_pool:
        try:
            _db_pool.putconn(conn)
        except Exception as e:  # pragma: no cover - log unexpected errors
            logger.error(f"Error releasing DB connection: {e}")


# --- Helper Functions ---


def generate_random_page_name(length=10):
    """Generates a random alphanumeric string for page/link names."""
    # Use the current random state (should be seeded externally)
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_fake_links(count=FAKE_LINK_COUNT, depth=FAKE_LINK_DEPTH):
    """Generates a list of plausible but fake internal link targets."""
    links = []
    base_path = "/tarpit"  # Base path for all tarpit links

    for _ in range(count):
        # Link to other fake pages or fake JS endpoints
        link_type = random.choice(["page", "js", "data", "css"])
        num_dirs = random.randint(0, depth)
        dirs = [
            generate_random_page_name(random.randint(5, 8)) for _ in range(num_dirs)
        ]
        filename_base = generate_random_page_name()

        if link_type == "page":
            ext = ".html"
            path_prefix = "/page/"
        elif link_type == "js":
            ext = ".js"
            path_prefix = "/js/"
        elif link_type == "data":
            ext = random.choice([".json", ".xml", ".csv"])
            path_prefix = "/data/"
        else:  # css
            ext = ".css"
            path_prefix = "/styles/"

        full_path = base_path + path_prefix + "/".join(dirs) + "/" + filename_base + ext
        # Normalize path (remove double slashes, etc.) - Python's os.path.normpath isn't URL aware
        full_path = full_path.replace("//", "/")
        links.append(full_path)

    return links


def get_next_word_from_db(word1_id, word2_id):
    """Queries PostgreSQL for the next word based on the previous two."""
    conn, cursor = _get_db_connection()
    if not conn or not cursor:
        return None

    try:
        # Query for possible next words and their frequencies, ordered by frequency desc
        cursor.execute(
            """
            SELECT w.word, s.freq
            FROM markov_sequences s
            JOIN markov_words w ON s.next_id = w.id
            WHERE s.p1 = %s AND s.p2 = %s
            ORDER BY s.freq DESC, random() -- Add random() for variety among equal frequencies
            LIMIT 20; -- Limit results for performance
            """,
            (word1_id, word2_id),
        )
        results = cursor.fetchall()

        if not results:
            return None  # No known sequence follows these two words

        # --- Probabilistic Selection ---
        # Instead of just picking the most frequent, pick probabilistically
        # based on frequency to introduce more variability.
        words = [row[0] for row in results]
        frequencies = [row[1] for row in results]
        total_freq = sum(frequencies)

        if total_freq == 0:  # Should not happen if results exist, but safety check
            return random.choice(words)

        # Normalize frequencies to probabilities
        probabilities = [f / total_freq for f in frequencies]

        # Choose based on weighted probability
        return random.choices(words, weights=probabilities, k=1)[0]

    except psycopg2.Error as e:
        logger.error(
            f"Database error fetching next word for ({word1_id}, {word2_id}): {e}"
        )
        global _db_pool
        _db_pool = None  # Force pool reinitialization on next call
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching next word: {e}")
        return None
    finally:
        _release_db_connection(conn, cursor)


def get_word_id(word):
    """Gets the ID for a word, returns ID for '' (empty string) if not found."""
    conn, cursor = _get_db_connection()
    if not conn or not cursor or not word:
        return 1  # ID for empty string (start/end token)

    try:
        cursor.execute("SELECT id FROM markov_words WHERE word = %s", (word,))
        result = cursor.fetchone()
        return (
            result[0] if result else 1
        )  # Default to empty string ID if word not found
    except Exception as e:
        logger.error(f"Error fetching ID for word '{word}': {e}")
        return 1  # Default to empty string ID on error
    finally:
        _release_db_connection(conn, cursor)


# --- Markov Text Generation using DB ---
def generate_markov_text_from_db(sentences=DEFAULT_SENTENCES_PER_PAGE):
    """Generates paragraphs of Markov text by querying PostgreSQL."""
    conn, cursor = _get_db_connection()
    if not conn or not cursor:
        logger.error("No DB connection for Markov text generation.")
        return "<p>Content generation unavailable.</p>"
    _release_db_connection(conn, cursor)

    # Use pre-seeded random state
    generated_content = ""
    word1_id, word2_id = 1, 1  # Start with empty history (ID 1)

    word_count = 0
    max_words = sentences * random.randint(15, 30)  # Approximate total words

    current_paragraph = []

    while word_count < max_words:
        next_word = get_next_word_from_db(word1_id, word2_id)

        if next_word is None or next_word == "":  # Reached end of a chain or error
            # End current paragraph if any words were added
            if current_paragraph:
                generated_content += "<p>" + " ".join(current_paragraph) + ".</p>\n"
                current_paragraph = []

            # Attempt to restart chain from a random point if needed
            # This is simplified - a better approach might pick a random common pair
            word1_id, word2_id = 1, 1
            if (
                next_word is None and word_count < max_words / 2
            ):  # Only restart if stuck early
                continue  # Try fetching again with reset state
            else:
                break  # Stop if stuck late or explicitly got empty string

        current_paragraph.append(html.escape(next_word))
        word_count += 1

        # Shift history
        word1_id = word2_id
        word2_id = get_word_id(next_word)  # Get ID for the next state

        # End paragraph on punctuation (simple heuristic)
        if next_word.endswith((".", "!", "?")) and len(current_paragraph) > 5:
            generated_content += "<p>" + " ".join(current_paragraph) + "</p>\n"
            current_paragraph = []
            word1_id, word2_id = 1, 1  # Reset history after punctuation

    # Add any remaining words in the current paragraph
    if current_paragraph:
        generated_content += "<p>" + " ".join(current_paragraph) + ".</p>\n"

    if not generated_content:
        return "<p>Could not generate content.</p>"  # Fallback

    return generated_content


# --- LLM Text Generation ---
def generate_llm_text(sentences=DEFAULT_SENTENCES_PER_PAGE):
    """Generate paragraphs using a configured LLM adapter."""
    if not LLM_ADAPTER:
        return None
    prompt = (
        f"Write {sentences} short paragraphs of plausible but meaningless technical documentation. "
        "Separate paragraphs with blank lines."
    )
    try:
        messages = [{"role": "user", "content": prompt}]
        try:
            result = LLM_ADAPTER.predict(messages, max_tokens=TARPIT_LLM_MAX_TOKENS)
        except Exception:
            result = LLM_ADAPTER.predict(prompt, max_tokens=TARPIT_LLM_MAX_TOKENS)
        text = result.get("response") if isinstance(result, dict) else str(result)
        paragraphs = [
            f"<p>{html.escape(p.strip())}</p>" for p in text.splitlines() if p.strip()
        ]
        if paragraphs:
            return "\n".join(paragraphs)
    except Exception as e:
        logger.error(f"LLM text generation failed: {e}")
    return None


# --- Main Generator Function ---
def _generate_dynamic_tarpit_page_py():
    """
    Generates a full HTML page with deterministically generated
    Markov text (from Postgres) and fake links.
    Assumes random module has been seeded externally.
    """
    logger.debug("Generating dynamic tarpit page content (Python)...")
    # 1. Generate page text
    if ENABLE_TARPIT_LLM_GENERATOR:
        page_content = generate_llm_text(DEFAULT_SENTENCES_PER_PAGE)
        if not page_content:
            logger.warning("LLM generation failed; falling back to Markov text")
            page_content = generate_markov_text_from_db(DEFAULT_SENTENCES_PER_PAGE)
    else:
        page_content = generate_markov_text_from_db(DEFAULT_SENTENCES_PER_PAGE)

    # 2. Generate Fake Links
    fake_links = generate_fake_links()
    link_html = "<ul>\n"
    for link in fake_links:
        # Create somewhat readable link text from the path
        try:
            link_text = (
                link.split("/")[-1]
                .split(".")[0]
                .replace("_", " ")
                .replace("-", " ")
                .capitalize()
            )
            if not link_text:
                link_text = "Resource Link"
            link_text = html.escape(link_text)
        except:
            link_text = "Link"  # Fallback
        link_html += f'    <li><a href="{link}">{link_text}</a></li>\n'
    link_html += "</ul>\n"

    # 3. Assemble HTML
    # Use a slightly different title/structure for variety
    page_title = " ".join(
        word.capitalize()
        for word in generate_random_page_name(random.randint(2, 4)).split()
    )
    page_title = html.escape(page_title)
    html_structure = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{page_title} - System Documentation</title>
    <meta name="robots" content="noindex, nofollow">
    <meta name="generator" content="AntiScrape Tarpit v1.0">
    <style>
        body {{ font-family: 'Courier New', Courier, monospace; background-color: #f0f0f0; color: #333; padding: 2em; line-height: 1.6; }}
        h1 {{ border-bottom: 1px solid #ccc; padding-bottom: 0.5em; color: #555; }}
        h2 {{ color: #666; margin-top: 2em; }}
        a {{ color: #3478af; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        ul {{ list-style-type: square; padding-left: 2em; }}
        p {{ text-align: justify; }}
        .footer-link {{ display: inline-block; margin-top: 40px; font-size: 0.8em; color: #aaa; visibility: hidden; }}
    </style>
</head>
<body>
    <h1>{page_title}</h1>
    {page_content}
    <h2>Further Reading:</h2>
    {link_html}
    <a href="/internal-docs/admin" class="footer-link">Admin Console</a>
</body>
</html>"""

    logger.debug("Dynamic tarpit page content generated.")
    return html_structure


def generate_dynamic_tarpit_page() -> str:
    """Generate a tarpit page using the configured backend."""
    if ENABLE_TARPIT_LLM_GENERATOR:
        return _generate_dynamic_tarpit_page_py()
    if RUST_ENABLED:
        try:
            return rs_generate_dynamic_tarpit_page()
        except Exception as e:
            logger.warning(
                f"tarpit_rs error generating page: {e}; falling back to Python implementation"
            )
    return _generate_dynamic_tarpit_page_py()


def _run_as_script() -> None:
    """Helper to execute the module's main block. Exposed for tests."""
    print("--- Generating Sample Tarpit Page (requires DB connection) ---")
    random.seed("test_seed_123")
    dynamic_html = generate_dynamic_tarpit_page()
    print("\n--- Generated HTML ---")
    print(dynamic_html)
    if _db_pool:
        _db_pool.closeall()
        print("Database connections closed.")


if __name__ == "__main__":
    _run_as_script()

# anti_scrape/rag/train_markov_postgres.py
# Trains the Markov model by populating the PostgreSQL database from a text corpus.

import os
import sys
import time
import re
import psycopg2 # Ensure psycopg2-binary is in requirements.txt
from psycopg2.extras import execute_batch
import logging
import argparse
from collections import defaultdict, deque

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Connection Environment Variables ---
PG_HOST = os.getenv("PG_HOST", "localhost") # Default to localhost for local runs
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DBNAME = os.getenv("PG_DBNAME", "markovdb")
PG_USER = os.getenv("PG_USER", "markovuser")
PG_PASSWORD_FILE = os.getenv("PG_PASSWORD_FILE", "./secrets/pg_password.txt") # Default relative path

# --- Constants ---
EMPTY_WORD = ''
EMPTY_WORD_ID = 1 # Ensure the init_markov.sql script reserves ID 1 for ''
BATCH_SIZE = 10000 # Number of sequences to batch insert/update for performance

def get_pg_password():
    """Loads password from secret file."""
    secret_path = PG_PASSWORD_FILE
    # Check common locations: relative, /run/secrets/, ../secrets/
    if not os.path.exists(secret_path):
        alt_path_run = os.path.join("/run/secrets", os.path.basename(PG_PASSWORD_FILE))
        if os.path.exists(alt_path_run):
            secret_path = alt_path_run
        else:
            alt_path_proj = os.path.join(os.path.dirname(__file__), '..', 'secrets', os.path.basename(PG_PASSWORD_FILE))
            if os.path.exists(alt_path_proj):
                secret_path = alt_path_proj
            else:
                 logger.error(f"Password file not found at '{PG_PASSWORD_FILE}', '{alt_path_run}', or '{alt_path_proj}'")
                 return None
    try:
        with open(secret_path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        logger.error(f"Failed to read PostgreSQL password from {secret_path}: {e}")
        return None

def connect_db():
    """Establishes connection to the PostgreSQL database."""
    pg_password = get_pg_password()
    if not pg_password:
        return None
    try:
        logger.info(f"Connecting to PostgreSQL: {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}")
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DBNAME,
            user=PG_USER,
            password=pg_password,
            connect_timeout=10
        )
        logger.info("Successfully connected to PostgreSQL.")
        # Set autocommit off for explicit transaction management
        conn.autocommit = False
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"ERROR: Failed to connect to PostgreSQL: {e}")
        return None
    except Exception as e:
        logger.error(f"ERROR: Unexpected error connecting to PostgreSQL: {e}")
        return None

def tokenize_text(text):
    """
    Simple tokenizer: splits by whitespace and converts to lowercase.
    Removes most punctuation, keeping apostrophes within words.
    """
    # Remove punctuation except apostrophes and hyphens within words
    text = re.sub(r"(?<!\w)['\-](?!\w)", '', text) # Remove leading/trailing ' -
    text = re.sub(r"[^\w\s'-]", '', text) # Remove other punctuation
    # Basic split and lowercase
    words = text.lower().split()
    # Filter out empty strings
    return [word for word in words if word]

def get_word_id(cursor, word_cache, word):
    """Gets the ID for a word, inserting it if it doesn't exist."""
    if word in word_cache:
        return word_cache[word]

    try:
        cursor.execute("SELECT id FROM markov_words WHERE word = %s", (word,))
        result = cursor.fetchone()
        if result:
            word_id = result[0]
        else:
            # Insert the new word and return its ID
            # Use ON CONFLICT just in case of race conditions (though unlikely in single script)
            cursor.execute(
                "INSERT INTO markov_words (word) VALUES (%s) ON CONFLICT (word) DO UPDATE SET word=EXCLUDED.word RETURNING id",
                (word,)
            )
            word_id = cursor.fetchone()[0]
            if word_id % 1000 == 0: # Log progress periodically
                 logger.info(f"Cached {len(word_cache)} unique words (last ID: {word_id})")
        word_cache[word] = word_id # Cache the ID
        return word_id
    except psycopg2.Error as e:
        logger.error(f"Database error getting/inserting word '{word}': {e}")
        raise # Propagate error to rollback transaction
    except Exception as e:
        logger.error(f"Unexpected error with word '{word}': {e}")
        raise

def train_from_corpus(corpus_path):
    """Reads corpus file and populates the Markov database."""
    conn = connect_db()
    if not conn:
        return

    logger.info(f"Starting Markov training from corpus: {corpus_path}")
    start_time = time.time()
    processed_sequences = 0
    word_cache = {EMPTY_WORD: EMPTY_WORD_ID} # Pre-cache empty word ID

    try:
        with conn.cursor() as cursor, open(corpus_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Ensure the empty word token exists with ID 1
            cursor.execute("INSERT INTO markov_words (id, word) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING", (EMPTY_WORD_ID, EMPTY_WORD))
            conn.commit() # Commit this essential setup

            # SQL for inserting/updating sequences
            upsert_sql = """
                INSERT INTO markov_sequences (p1, p2, next_id, freq)
                VALUES (%s, %s, %s, 1)
                ON CONFLICT (p1, p2, next_id) DO UPDATE SET freq = markov_sequences.freq + 1;
            """
            sequence_batch = []

            # Process text line by line or chunk by chunk
            line_num = -1  # Ensure line_num is always defined
            for line_num, line in enumerate(f):
                words = tokenize_text(line)
                if not words:
                    continue

                # Use a deque-like structure for history (state_size=2)
                # Start with empty word history
                p1_id = EMPTY_WORD_ID
                p2_id = EMPTY_WORD_ID

                for word in words:
                    # Check for excessively long words (potential parsing errors)
                    if len(word) > 100:
                        logger.warning(f"Skipping excessively long token on line {line_num+1}: '{word[:50]}...'")
                        continue

                    next_id = get_word_id(cursor, word_cache, word)

                    # Add sequence (p1_id, p2_id -> next_id) to batch
                    sequence_batch.append((p1_id, p2_id, next_id))
                    processed_sequences += 1

                    # Update history for next iteration
                    p1_id = p2_id
                    p2_id = next_id

                    # Execute batch if full
                    if len(sequence_batch) >= BATCH_SIZE:
                        execute_batch(cursor, upsert_sql, sequence_batch)
                        # conn.commit() # Commit more frequently for large files?
                        logger.info(f"Processed {processed_sequences} sequences (checkpoint)...")
                        sequence_batch = []

                # Add final sequence ending with the empty token
                # Links the last word pair of the line/chunk to the "end" state
                sequence_batch.append((p1_id, p2_id, EMPTY_WORD_ID))
                processed_sequences += 1

                # Commit periodically based on line number for very large files
                if line_num % 10000 == 0:
                     if sequence_batch: # Commit remaining batch items
                         execute_batch(cursor, upsert_sql, sequence_batch)
                         sequence_batch = []
                     conn.commit()
                     logger.info(f"Committed up to line {line_num+1}")


            # Process any remaining sequences in the last batch
            if sequence_batch:
                execute_batch(cursor, upsert_sql, sequence_batch)

            conn.commit() # Final commit

        end_time = time.time()
        logger.info(f"Markov training complete. Processed {processed_sequences} sequences from {line_num+1} lines in {end_time - start_time:.2f} seconds.")
        logger.info(f"Final unique words count: {len(word_cache)}")

    except FileNotFoundError:
        logger.error(f"ERROR: Corpus file not found at {corpus_path}")
    except psycopg2.Error as e:
        logger.error(f"Database error during training: {e}")
        logger.info("Rolling back transaction.")
        conn.rollback() # Rollback transaction on DB error
    except Exception as e:
        logger.error(f"ERROR: Unexpected error during training: {e}", exc_info=True)
        logger.info("Rolling back transaction.")
        conn.rollback() # Rollback on other errors
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

# --- Command Line Argument Parsing ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PostgreSQL Markov model from text corpus.")
    parser.add_argument("corpus_file", help="Path to the text corpus file.")
    # Example: Add argument for state size if implementing higher-order Markov chains
    # parser.add_argument("--state-size", type=int, default=2, help="Number of previous words to use as state (e.g., 2).")

    args = parser.parse_args()

    if not os.path.exists(args.corpus_file):
        print(f"Error: Corpus file not found: {args.corpus_file}")
        sys.exit(1)

    train_from_corpus(args.corpus_file)
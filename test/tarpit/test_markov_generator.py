# test/tarpit/markov_generator.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import psycopg2  # For exception types
import random
import importlib  # For reloading the module to test __main__

# Import the module to test
# Ensure that the 'tarpit' package is discoverable in PYTHONPATH
from src.tarpit import markov_generator


# Helper to reset module-level globals for test isolation
def reset_markov_generator_globals():
    markov_generator._db_pool = None
    # Reset other globals if they were introduced and modified by tests


class TestMarkovGenerator(unittest.TestCase):

    def setUp(self):
        reset_markov_generator_globals()  # Reset before each test

        # Patch environment variables for DB connection
        self.env_patcher = patch.dict(
            os.environ,
            {
                "PG_HOST": "test_host",
                "PG_PORT": "1234",
                "PG_DBNAME": "test_db",
                "PG_USER": "test_user",
                "PG_PASSWORD_FILE": "/fake/path/pg_password.txt",
            },
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

        # Reload the module to pick up patched environment variables for its constants
        # This is important if PG_HOST etc. are defined at module import time.
        importlib.reload(markov_generator)

    # --- Test _get_pg_password ---
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data="db_secret_password")
    def test_get_pg_password_success(self, mock_file, mock_exists):
        # Ensure PG_PASSWORD_FILE is patched for the SUT if it's read at module level
        with patch.object(
            markov_generator, "PG_PASSWORD_FILE", "/fake/path/pg_password.txt"
        ):
            password = markov_generator._get_pg_password()
            self.assertEqual(password, "db_secret_password")
            mock_exists.assert_called_once_with("/fake/path/pg_password.txt")
            mock_file.assert_called_once_with("/fake/path/pg_password.txt", "r")

    @patch("os.path.exists", return_value=False)
    @patch.object(markov_generator.logger, "error")
    def test_get_pg_password_file_not_found(self, mock_logger_error, mock_exists):
        with patch.object(
            markov_generator, "PG_PASSWORD_FILE", "/nonexistent/path/pg_password.txt"
        ):
            password = markov_generator._get_pg_password()
            self.assertIsNone(password)
            # The SUT logs the error, check if it was called
            mock_logger_error.assert_called_once()
            self.assertIn(
                "Failed to read PostgreSQL password", mock_logger_error.call_args[0][0]
            )

    # --- Test _get_db_connection ---
    @patch("src.tarpit.markov_generator._get_pg_password", return_value="test_password")
    @patch("src.tarpit.markov_generator.pool.SimpleConnectionPool")
    def test_get_db_connection_success_new_connection(
        self, mock_pool_cls, mock_get_pass
    ):
        mock_pool = MagicMock()
        mock_conn_instance = MagicMock()
        mock_cursor_instance = MagicMock()
        mock_conn_instance.cursor.return_value = mock_cursor_instance
        mock_pool.getconn.return_value = mock_conn_instance
        mock_pool_cls.return_value = mock_pool

        conn, cursor = markov_generator._get_db_connection()

        self.assertIsNotNone(conn)
        self.assertIsNotNone(cursor)
        self.assertEqual(conn, mock_conn_instance)
        self.assertEqual(cursor, mock_cursor_instance)
        mock_pool.getconn.assert_called_once()
        mock_pool_cls.assert_called_once()
        self.assertEqual(markov_generator._db_pool, mock_pool)

    @patch("src.tarpit.markov_generator._get_pg_password", return_value="test_password")
    def test_get_db_connection_reuse_existing(self, mock_get_pass):
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool.getconn.return_value = mock_conn
        markov_generator._db_pool = mock_pool

        with patch(
            "src.tarpit.markov_generator.pool.SimpleConnectionPool"
        ) as mock_pool_cls:
            conn, cursor = markov_generator._get_db_connection()
            self.assertEqual(conn, mock_conn)
            self.assertEqual(cursor, mock_cursor)
            mock_pool_cls.assert_not_called()
            mock_pool.getconn.assert_called_once()

    @patch(
        "src.tarpit.markov_generator._get_pg_password", return_value=None
    )  # Password unavailable
    @patch.object(markov_generator.logger, "error")
    def test_get_db_connection_no_password(self, mock_logger_error, mock_get_pass):
        conn, cursor = markov_generator._get_db_connection()
        self.assertIsNone(conn)
        self.assertIsNone(cursor)
        mock_logger_error.assert_any_call(
            "PostgreSQL password not available. Cannot connect."
        )

    @patch("src.tarpit.markov_generator._get_pg_password", return_value="test_password")
    @patch(
        "src.tarpit.markov_generator.pool.SimpleConnectionPool",
        side_effect=psycopg2.OperationalError("DB connection failed"),
    )
    @patch.object(markov_generator.logger, "error")
    def test_get_db_connection_operational_error(
        self, mock_logger_error, mock_pool_cls, mock_get_pass
    ):
        conn, cursor = markov_generator._get_db_connection()
        self.assertIsNone(conn)
        self.assertIsNone(cursor)
        mock_pool_cls.assert_called_once()
        mock_logger_error.assert_any_call(
            "ERROR: Failed to initialize PostgreSQL pool: DB connection failed"
        )

    # --- Test generate_random_page_name ---
    def test_generate_random_page_name(self):
        name1 = markov_generator.generate_random_page_name(length=8)
        self.assertEqual(len(name1), 8)
        self.assertTrue(
            all(c.isalnum() or c.islower() for c in name1)
        )  # Checks if all are lowercase alphanumeric

        name2 = markov_generator.generate_random_page_name(length=12)
        self.assertEqual(len(name2), 12)

        # Test determinism with seed (if random is seeded externally)
        random.seed(42)
        name_s1 = markov_generator.generate_random_page_name()
        random.seed(42)
        name_s2 = markov_generator.generate_random_page_name()
        self.assertEqual(name_s1, name_s2)

    # --- Test generate_fake_links ---
    @patch("src.tarpit.markov_generator.generate_random_page_name")
    def test_generate_fake_links(self, mock_gen_page_name):
        mock_gen_page_name.side_effect = lambda length=10: "randomname"[
            :length
        ]  # Predictable "random" names

        links = markov_generator.generate_fake_links(count=2, depth=1)
        self.assertEqual(len(links), 2)
        for link in links:
            self.assertTrue(link.startswith("/tarpit/"))
            self.assertIn(
                "randomname", link
            )  # Check if our mocked name generator was used
            # Example: /tarpit/page/randomn/randomname.html
            self.assertTrue(
                link.endswith((".html", ".js", ".json", ".xml", ".csv", ".css"))
            )

    # --- Test get_word_id ---
    @patch("src.tarpit.markov_generator._get_db_connection")
    def test_get_word_id_success(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (123,)  # Simulate word found
        mock_get_conn.return_value = (MagicMock(), mock_cursor)

        word_id = markov_generator.get_word_id("testword")
        self.assertEqual(word_id, 123)
        mock_cursor.execute.assert_called_once_with(
            "SELECT id FROM markov_words WHERE word = %s", ("testword",)
        )

    @patch("src.tarpit.markov_generator._get_db_connection")
    def test_get_word_id_not_found_returns_empty_id(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Simulate word not found
        mock_get_conn.return_value = (MagicMock(), mock_cursor)

        word_id = markov_generator.get_word_id("unknownword")
        self.assertEqual(word_id, 1)  # Should return EMPTY_WORD_ID (1)

    @patch(
        "src.tarpit.markov_generator._get_db_connection", return_value=(None, None)
    )  # DB connection fails
    def test_get_word_id_db_connection_fails(self, mock_get_conn):
        word_id = markov_generator.get_word_id("anyword")
        self.assertEqual(word_id, 1)  # Should default to EMPTY_WORD_ID

    # --- Test get_next_word_from_db ---
    @patch("src.tarpit.markov_generator._get_db_connection")
    @patch("random.choices")  # To control probabilistic selection
    def test_get_next_word_from_db_success(self, mock_random_choices, mock_get_conn):
        mock_cursor = MagicMock()
        # Simulate DB returning multiple possible next words with frequencies
        mock_cursor.fetchall.return_value = [("next", 10), ("another", 5), ("last", 2)]
        mock_get_conn.return_value = (MagicMock(), mock_cursor)

        # Make random.choices return a predictable choice
        mock_random_choices.return_value = ["next"]

        next_word = markov_generator.get_next_word_from_db(10, 20)
        self.assertEqual(next_word, "next")
        mock_cursor.execute.assert_called_once()
        mock_random_choices.assert_called_once_with(
            ["next", "another", "last"],  # words
            weights=[10 / 17, 5 / 17, 2 / 17],  # probabilities
            k=1,
        )

    @patch("src.tarpit.markov_generator._get_db_connection")
    def test_get_next_word_from_db_no_results(self, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # No sequence found
        mock_get_conn.return_value = (MagicMock(), mock_cursor)

        next_word = markov_generator.get_next_word_from_db(10, 20)
        self.assertIsNone(next_word)

    @patch("src.tarpit.markov_generator._get_db_connection")
    @patch.object(markov_generator.logger, "error")
    def test_get_next_word_from_db_query_error(self, mock_logger_error, mock_get_conn):
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = psycopg2.Error("Query failed")
        mock_get_conn.return_value = (MagicMock(), mock_cursor)

        next_word = markov_generator.get_next_word_from_db(10, 20)
        self.assertIsNone(next_word)
        mock_logger_error.assert_called_once()
        self.assertIn(
            "Database error fetching next word", mock_logger_error.call_args[0][0]
        )
        # Check if pool was reset
        self.assertIsNone(markov_generator._db_pool)

    # --- Test generate_markov_text_from_db ---
    @patch("src.tarpit.markov_generator._get_db_connection")
    @patch("src.tarpit.markov_generator.get_next_word_from_db")
    @patch("src.tarpit.markov_generator.get_word_id")
    @patch(
        "random.randint", return_value=1
    )  # Generate 1 sentence * 1 word = 1 word max
    def test_generate_markov_text_from_db_simple(
        self, mock_rand_int, mock_get_id, mock_get_next_word, mock_get_conn
    ):
        mock_cursor = MagicMock()
        mock_get_conn.return_value = (MagicMock(), mock_cursor)

        # Simulate word generation: "This", "is", "a", "test", None (end)
        mock_get_next_word.side_effect = ["This", "is", "a", "test", None]
        mock_get_id.side_effect = [2, 3, 4, 5]  # IDs for This, is, a, test

        # Test generating a small number of sentences (controlled by max_words via randint mock)
        # random.randint(15,30) is used for words per sentence in SUT.
        # Here DEFAULT_SENTENCES_PER_PAGE = 15.
        # Max words = 15 * random.randint(15,30).
        # We mocked randint to 1, so max_words = 15 * 1 = 15.
        # Our side_effect for get_next_word has 4 words then None.
        with patch.object(markov_generator, "DEFAULT_SENTENCES_PER_PAGE", 1), patch(
            "random.randint", return_value=4
        ):  # max_words = 1 * 4 = 4
            text = markov_generator.generate_markov_text_from_db(sentences=1)

        self.assertEqual(text.strip(), "<p>This is a test.</p>")
        self.assertGreaterEqual(
            mock_get_next_word.call_count, 4
        )  # Called until None or max_words
        self.assertGreaterEqual(mock_get_id.call_count, 4)

    @patch(
        "src.tarpit.markov_generator._get_db_connection", return_value=(None, None)
    )  # DB fails
    def test_generate_markov_text_db_unavailable(self, mock_get_conn):
        text = markov_generator.generate_markov_text_from_db()
        self.assertEqual(text, "<p>Content generation unavailable.</p>")

    # --- Test generate_dynamic_tarpit_page ---
    @patch(
        "src.tarpit.markov_generator.generate_markov_text_from_db",
        return_value="<p>Mocked Markov Text.</p>",
    )
    @patch(
        "src.tarpit.markov_generator.generate_fake_links",
        return_value=["/tarpit/fake/link1.html"],
    )
    @patch(
        "src.tarpit.markov_generator.generate_random_page_name", return_value="mockpage"
    )
    def test_generate_dynamic_tarpit_page_structure(
        self, mock_gen_name, mock_gen_links, mock_gen_text
    ):
        # Assume random is seeded externally as per tarpit_api.py's usage
        html = markov_generator.generate_dynamic_tarpit_page()

        self.assertIn(
            "<title>Mockpage - System Documentation</title>", html
        )  # Title uses generate_random_page_name
        self.assertIn("<p>Mocked Markov Text.</p>", html)
        self.assertIn(
            '<li><a href="/tarpit/fake/link1.html">Link1</a></li>', html
        )  # Check link text derivation
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)
        mock_gen_text.assert_called_once_with(
            markov_generator.DEFAULT_SENTENCES_PER_PAGE
        )
        mock_gen_links.assert_called_once()
        # generate_random_page_name is called for title and inside generate_fake_links
        self.assertGreaterEqual(mock_gen_name.call_count, 1)

    @patch(
        "src.tarpit.markov_generator.generate_fake_links",
        return_value=["/tarpit/fake.html"],
    )
    def test_llm_generator_used_when_enabled(self, mock_links):
        dummy_adapter = MagicMock()
        dummy_adapter.predict.return_value = {"response": "Para one\n\nPara two"}

        with patch.dict(
            os.environ,
            {
                "ENABLE_TARPIT_LLM_GENERATOR": "true",
                "TARPIT_LLM_MODEL_URI": "openai://test-model",
            },
            clear=False,
        ), patch(
            "src.shared.model_provider.get_model_adapter", return_value=dummy_adapter
        ) as mock_get_adapter:
            import importlib

            importlib.reload(markov_generator)

            with patch.object(markov_generator, "RUST_ENABLED", False), patch(
                "src.tarpit.markov_generator.generate_markov_text_from_db",
                return_value="fallback",
            ) as mock_markov:
                html = markov_generator.generate_dynamic_tarpit_page()

            mock_get_adapter.assert_called_once_with(
                "openai://test-model", retries=3, delay=1.0
            )
            mock_markov.assert_not_called()
            self.assertIn("<p>Para one</p>", html)

    # --- Test __main__ block ---
    @patch.object(
        markov_generator, "generate_dynamic_tarpit_page", return_value="<html></html>"
    )
    @patch("builtins.print")
    @patch("random.seed")
    @patch.object(markov_generator, "_db_pool")
    def test_main_block_execution(
        self, mock_db_pool_obj, mock_random_seed, mock_print, mock_gen_page
    ):
        # Simulate the script being run as main
        # This is complex because of the global connection pool.
        # We need to ensure that if _get_db_connection was called by generate_dynamic_tarpit_page (via its chain),
        # then _db_pool would be set, and __main__ should close it.

        # Simulate pool being set by a previous call if generator needed it
        mock_pool_for_main = MagicMock()
        markov_generator._db_pool = mock_pool_for_main

        # Execute the script logic directly via helper
        markov_generator._run_as_script()

        mock_print.assert_any_call(
            "--- Generating Sample Tarpit Page (requires DB connection) ---"
        )
        mock_random_seed.assert_called_once_with("test_seed_123")
        mock_gen_page.assert_called_once()
        mock_print.assert_any_call("\n--- Generated HTML ---")
        mock_print.assert_any_call("<html></html>")

        # Check if the connection (that was simulated as opened) was closed
        mock_pool_for_main.closeall.assert_called_once()
        mock_print.assert_any_call("Database connections closed.")


if __name__ == "__main__":
    unittest.main()

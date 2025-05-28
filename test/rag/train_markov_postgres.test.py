# test\rag\train_markov_postgres.test.py
import unittest
from unittest.mock import patch, MagicMock
from rag import train_markov_postgres

class TestTrainMarkovPostgres(unittest.TestCase):

    @patch('rag.train_markov_postgres.psycopg2.connect')
    def test_db_connection_success(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        train_markov_postgres.store_markov_chain({"hello": ["world"]}, "test_table")
        mock_conn.cursor.assert_called()
        mock_conn.commit.assert_called()

    @patch('rag.train_markov_postgres.psycopg2.connect')
    def test_empty_chain_handling(self, mock_connect):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        train_markov_postgres.store_markov_chain({}, "test_table")
        mock_conn.cursor.assert_not_called()
        mock_conn.commit.assert_not_called()

    def test_tokenize_text(self):
        text = "This is a test."
        tokens = train_markov_postgres.tokenize(text)
        self.assertIsInstance(tokens, list)
        self.assertIn("test", tokens)

    def test_build_markov_chain(self):
        text = "hello world hello bot"
        chain = train_markov_postgres.build_chain(text)
        self.assertIn("hello", chain)
        self.assertIsInstance(chain["hello"], list)

if __name__ == '__main__':
    unittest.main()

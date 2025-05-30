# test/rag/training.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, call, ANY
import os
import psycopg2 # Changed from sqlite3
from psycopg2 import extras as psycopg2_extras # For execute_batch
import datetime
import json
import re
from typing import List, Dict, Any, Tuple, Optional # Ensure these are imported

# Attempt to import freezegun, make it optional for tests not strictly needing it
try:
    from freezegun import freeze_time
    FREEZEGUN_AVAILABLE = True
except ImportError:
    FREEZEGUN_AVAILABLE = False
    def freeze_time(time_to_freeze): # type: ignore
        def decorator(func):
            def wrapper(*args, **kwargs):
                print("Warning: freezegun not installed, time-sensitive tests may be less reliable.")
                return func(*args, **kwargs)
            return wrapper
        return decorator

# Import the module to test
from rag import training
import importlib # For reloading

# Helper to reset module-level states if they exist and are modified by tests
def reset_training_module_globals():
    training.disallowed_paths = set()
    try:
        from user_agents import parse as ua_parse
        training.UA_PARSER_AVAILABLE = True
        training.ua_parse = ua_parse
    except ImportError:
        training.UA_PARSER_AVAILABLE = False
        training.ua_parse = None # type: ignore
    # Reset any other relevant globals if training.py introduces them
    # For example, if it had a global DB connection (it doesn't, which is good)


class TestTrainingScriptWithPostgreSQL(unittest.TestCase):

    def setUp(self):
        """Setup common test resources."""
        reset_training_module_globals()
        self.test_data_dir = "test_temp_training_data_pg" # Unique name
        os.makedirs(self.test_data_dir, exist_ok=True)
        
        # Define paths using self.test_data_dir
        # DB_PATH is no longer used directly by training.py for SQLite, but env vars for PG are.
        self.model_path = os.path.join(self.test_data_dir, "test_model.joblib")
        self.robots_path = os.path.join(self.test_data_dir, "test_robots.txt")
        self.honeypot_log_path = os.path.join(self.test_data_dir, "test_honeypot.log")
        self.captcha_log_path = os.path.join(self.test_data_dir, "test_captcha.log")
        self.access_log_path = os.path.join(self.test_data_dir, "test_access.log")
        self.finetune_train_path = os.path.join(self.test_data_dir, "test_ft_train.jsonl")
        self.finetune_eval_path = os.path.join(self.test_data_dir, "test_ft_eval.jsonl")
        self.dummy_pg_password_file = os.path.join(self.test_data_dir, "dummy_pg_password.txt")

        with open(self.dummy_pg_password_file, "w") as f:
            f.write("testpassword")

        self.env_patcher = patch.dict(os.environ, {
            "TRAINING_LOG_FILE_PATH": self.access_log_path,
            "PG_HOST": "mock_pg_host",
            "PG_PORT": "5432",
            "TRAINING_PG_DBNAME": "mock_loganalysisdb",
            "TRAINING_PG_USER": "mock_loganalysisuser",
            "TRAINING_PG_PASSWORD_FILE": self.dummy_pg_password_file,
            "TRAINING_MODEL_SAVE_PATH": self.model_path,
            "TRAINING_FINETUNE_DATA_DIR": self.test_data_dir,
            "TRAINING_ROBOTS_TXT_PATH": self.robots_path,
            "TRAINING_HONEYPOT_LOG": self.honeypot_log_path,
            "TRAINING_CAPTCHA_LOG": self.captcha_log_path,
            "MIN_SAMPLES_FOR_TRAINING": "10"
        })
        self.env_patcher.start()
        
        # Reload training module to pick up patched env vars for its constants
        importlib.reload(training)
        # Explicitly set paths in training module if they are module-level constants
        # that don't get re-evaluated from os.getenv on each call.
        training.LOG_FILE_PATH = self.access_log_path
        training.PG_HOST = "mock_pg_host"
        training.PG_PORT = "5432"
        training.PG_DBNAME = "mock_loganalysisdb"
        training.PG_USER = "mock_loganalysisuser"
        training.PG_PASSWORD_FILE = self.dummy_pg_password_file
        training.MODEL_SAVE_PATH = self.model_path
        training.FINETUNE_DATA_DIR = self.test_data_dir
        training.FINETUNE_TRAIN_FILE = os.path.join(training.FINETUNE_DATA_DIR, "finetuning_data_train.jsonl")
        training.FINETUNE_EVAL_FILE = os.path.join(training.FINETUNE_DATA_DIR, "finetuning_data_eval.jsonl")
        training.ROBOTS_TXT_PATH = self.robots_path
        training.HONEYPOT_HIT_LOG = self.honeypot_log_path
        training.CAPTCHA_SUCCESS_LOG = self.captcha_log_path
        training.MIN_SAMPLES_FOR_TRAINING = 10


    def tearDown(self):
        """Clean up test resources."""
        self.env_patcher.stop()
        files_to_remove = [
            self.model_path, self.robots_path, self.honeypot_log_path,
            self.captcha_log_path, self.access_log_path,
            self.finetune_train_path, self.finetune_eval_path,
            self.dummy_pg_password_file
        ]
        # Also remove files that training.py might create using its reloaded constants
        if hasattr(training, 'FINETUNE_TRAIN_FILE') and os.path.exists(training.FINETUNE_TRAIN_FILE):
            files_to_remove.append(training.FINETUNE_TRAIN_FILE)
        if hasattr(training, 'FINETUNE_EVAL_FILE') and os.path.exists(training.FINETUNE_EVAL_FILE):
            files_to_remove.append(training.FINETUNE_EVAL_FILE)

        for f_path in files_to_remove:
            if os.path.exists(f_path):
                try: os.remove(f_path)
                except Exception as e: print(f"Warning: Could not remove test file {f_path}: {e}")
        
        if os.path.exists(self.test_data_dir):
            try:
                # Simple cleanup, for more complex scenarios use shutil.rmtree
                if not os.listdir(self.test_data_dir): os.rmdir(self.test_data_dir)
                else:
                    for item in os.listdir(self.test_data_dir):
                        item_path = os.path.join(self.test_data_dir, item)
                        if os.path.isfile(item_path): os.remove(item_path)
                    os.rmdir(self.test_data_dir)
            except OSError as e: print(f"Warning: Could not remove test directory {self.test_data_dir}: {e}")
        
        # Reload to reset any module-level state from training.py
        importlib.reload(training)


    # --- Test _get_pg_password ---
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="db_secret_password")
    def test_get_pg_password_success(self, mock_file, mock_os_exists):
        mock_os_exists.return_value = True
        # Test with a specific path
        password = training._get_pg_password("/fake/pg_password.txt")
        self.assertEqual(password, "db_secret_password")
        mock_os_exists.assert_called_with("/fake/pg_password.txt") # First path tried
        mock_file.assert_called_once_with("/fake/pg_password.txt", 'r')

    @patch("os.path.exists", return_value=False) # All path checks will fail
    @patch("rag.training.print") # Mock print to check error messages
    def test_get_pg_password_file_not_found(self, mock_print, mock_os_exists):
        password = training._get_pg_password("/nonexistent/pg_password.txt")
        self.assertIsNone(password)
        mock_print.assert_any_call(f"Error: PostgreSQL password file not found at specified path or fallbacks: /nonexistent/pg_password.txt")


    # --- Test setup_database ---
    @patch("rag.training.psycopg2.connect")
    @patch("rag.training._get_pg_password", return_value="testpassword") # Mock password loading
    def test_setup_database_creates_tables_and_indexes(self, mock_get_pass, mock_psycopg2_connect):
        mock_conn = MagicMock(spec=psycopg2.extensions.connection)
        mock_cursor = MagicMock(spec=psycopg2.extensions.cursor)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2_connect.return_value = mock_conn

        conn = training.setup_database()
        self.assertIsNotNone(conn, "Database connection should not be None.")
        
        mock_psycopg2_connect.assert_called_once_with(
            host=training.PG_HOST, # Uses module constant after reload
            port=training.PG_PORT,
            dbname=training.PG_DBNAME,
            user=training.PG_USER,
            password="testpassword",
            connect_timeout=10
        )
        
        # Check for table and index creation by inspecting calls to mock_cursor.execute
        execute_calls = mock_cursor.execute.call_args_list
        
        self.assertTrue(
            any("CREATE TABLE IF NOT EXISTS requests" in str(cargs[0][0]).upper() for cargs in execute_calls),
            "CREATE TABLE IF NOT EXISTS requests statement not found in execute calls"
        )
        self.assertTrue(
            any("CREATE INDEX IF NOT EXISTS idx_requests_ip_timestamp" in str(cargs[0][0]).upper() for cargs in execute_calls),
            "CREATE INDEX idx_requests_ip_timestamp statement not found"
        )
        self.assertTrue(
            any("CREATE INDEX IF NOT EXISTS idx_requests_timestamp" in str(cargs[0][0]).upper() for cargs in execute_calls),
            "CREATE INDEX idx_requests_timestamp statement not found"
        )
        
        mock_conn.commit.assert_called() # Should be called after setup
        mock_cursor.close.assert_called_once()


    @patch("rag.training.psycopg2.connect", side_effect=psycopg2.Error("DB connection failed"))
    @patch("rag.training._get_pg_password", return_value="testpassword")
    def test_setup_database_connection_error(self, mock_get_pass, mock_connect):
        conn = training.setup_database()
        self.assertIsNone(conn)

    # --- Test load_robots_txt and is_path_disallowed (conceptually similar, ensure path used) ---
    def test_load_robots_txt_and_is_path_disallowed(self):
        robots_content = "User-agent: *\nDisallow: /admin/\nDisallow: /private/path\nAllow: /public/"
        with open(self.robots_path, "w") as f: # Uses self.robots_path set in setUp
            f.write(robots_content)
        
        training.load_robots_txt(self.robots_path) # Pass the path explicitly
        
        self.assertIn("/admin/", training.disallowed_paths)
        self.assertTrue(training.is_path_disallowed("/admin/page.html"))
        self.assertFalse(training.is_path_disallowed("/public/page.html"))

    # --- Test parse_apache_combined_log_line (remains the same logic) ---
    def test_parse_apache_combined_log_line_valid(self):
        log_line = '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326 "http://www.example.com/start.html" "Mozilla/5.0 (compatible; TestBot/1.1)"'
        parsed = training.parse_apache_combined_log_line(log_line)
        self.assertIsNotNone(parsed)
        if parsed:
            self.assertEqual(parsed['ip'], '127.0.0.1')
            self.assertEqual(parsed['method'], 'GET')
            self.assertEqual(parsed['path'], '/apache_pb.gif')
            self.assertEqual(parsed['user_text'], None) # Check renamed 'user' field
            self.assertTrue(isinstance(datetime.datetime.fromisoformat(parsed['timestamp_iso'].replace('Z', '+00:00')), datetime.datetime))

    # --- Test load_logs_into_db ---
    @patch("builtins.open", new_callable=mock_open)
    @patch("rag.training.parse_apache_combined_log_line")
    @patch("rag.training.psycopg2_extras.execute_batch") # Patch execute_batch
    def test_load_logs_into_db_success(self, mock_execute_batch, mock_parse_log, mock_file_open):
        mock_file_open.return_value.__iter__.return_value = ["log_line_1", "log_line_2"]
        mock_parse_log.side_effect = [
            {"ip": "1.1.1.1", "timestamp_iso": "ts1", "method": "GET", "path": "/p1", "status": 200, "bytes": 100, "user_agent": "ua1", "user_text":None, "ident":None, "protocol":"HTTP/1.1", "referer":None},
            {"ip": "2.2.2.2", "timestamp_iso": "ts2", "method": "POST", "path": "/p2", "status": 404, "bytes": 50, "user_agent": "ua2", "user_text":None, "ident":None, "protocol":"HTTP/1.1", "referer":None}
        ]
        mock_conn = MagicMock(spec=psycopg2.extensions.connection)
        mock_cursor = MagicMock(spec=psycopg2.extensions.cursor)
        mock_conn.cursor.return_value = mock_cursor

        result = training.load_logs_into_db(self.access_log_path, mock_conn)
        
        self.assertTrue(result)
        self.assertEqual(mock_execute_batch.call_count, 1) # For 2 items, one batch
        # Check the SQL uses %s
        args, _ = mock_execute_batch.call_args
        self.assertIn("%s", args[1]) # args[1] is the SQL query string
        mock_conn.commit.assert_called()
        mock_cursor.close.assert_called_once()

    # --- Test extract_features_from_db ---
    @patch("rag.training.ua_parse") 
    def test_extract_features_from_db_with_pg_cursor(self, mock_ua_parse_func):
        mock_ua_parse_func.return_value = MagicMock(is_bot=True, browser=MagicMock(family="TestBrowser"), os=MagicMock(family="TestOS"), device=MagicMock(family="TestDevice"), is_mobile=False, is_tablet=False, is_pc=True, is_touch_capable=False)
        
        mock_pg_cursor = MagicMock(spec=psycopg2.extensions.cursor)
        # Define column names as they would be from a PG query
        col_names = ['id', 'ip', 'ident', 'user_text', 'timestamp_iso', 'method', 'path', 'protocol', 'status', 'bytes', 'referer', 'user_agent']
        
        current_time = datetime.datetime.utcnow()
        log_entry_row_tuple = (
            1, '1.2.3.4', None, None, current_time.isoformat() + "Z", 
            'GET', '/test', 'HTTP/1.1', 200, 1234, 
            'http://referer.com', 'Test User Agent'
        )
        
        # Mock the frequency sub-queries
        mock_pg_cursor.fetchone.side_effect = [
            (5,),    # For COUNT(*)
            ((current_time - datetime.timedelta(seconds=10)).isoformat() + "Z",) # For MAX(timestamp_iso)
        ]

        with patch.object(training, 'UA_PARSER_AVAILABLE', True), \
             patch.object(training, 'ua_parse', mock_ua_parse_func):
            features = training.extract_features_from_db(log_entry_row_tuple, col_names, mock_pg_cursor)
        
        self.assertIn('ua_length', features)
        self.assertEqual(features['ua_library_is_bot'], 1)
        # Check that execute was called for frequency queries with %s placeholders
        self.assertIn(call("SELECT COUNT(*) FROM requests WHERE ip = %s AND timestamp_iso >= %s AND timestamp_iso < %s", ('1.2.3.4', ANY, ANY)), mock_pg_cursor.execute.call_args_list)
        self.assertIn(call("SELECT MAX(timestamp_iso) FROM requests WHERE ip = %s AND timestamp_iso < %s", ('1.2.3.4', ANY)), mock_pg_cursor.execute.call_args_list)
        self.assertEqual(features[f'req_freq_{training.FREQUENCY_WINDOW_SECONDS}s'], 5)
        self.assertAlmostEqual(features['time_since_last_sec'], 10.0, delta=0.001)


    # --- Test assign_label_and_score (logic remains same, ensure it's called correctly) ---
    @freeze_time("2023-01-01 12:00:00") 
    def test_assign_label_and_score_honeypot_hit(self):
        log_entry = {"ip": "1.1.1.1", "user_agent": "TestUA", "path": "/"} 
        honeypot_ips = {"1.1.1.1"}
        captcha_ips = set()
        label, score, reasons = training.assign_label_and_score(log_entry, honeypot_ips, captcha_ips)
        self.assertEqual(label, "bot")
        self.assertAlmostEqual(score, 0.98)

    # --- Test train_and_save_model (logic remains same) ---
    @patch("joblib.dump")
    @patch("sklearn.ensemble.RandomForestClassifier")
    @patch("sklearn.feature_extraction.DictVectorizer")
    @patch("sklearn.model_selection.train_test_split")
    def test_train_and_save_model_sufficient_data(self, mock_split, mock_vectorizer, mock_classifier, mock_joblib_dump):
        num_samples = training.MIN_SAMPLES_FOR_TRAINING 
        features = [{"f1": 1, "f2": 0}] * num_samples 
        labels = ([0] * (num_samples // 2)) + ([1] * (num_samples - num_samples // 2))
        
        mock_split.return_value = (features[:int(num_samples*0.75)], features[int(num_samples*0.75):], 
                                   labels[:int(num_samples*0.75)], labels[int(num_samples*0.75):])
        mock_vec_instance = MagicMock(); mock_vec_instance.fit_transform.return_value = MagicMock() # Mock sparse matrix or array
        mock_vec_instance.transform.return_value = MagicMock()
        mock_vectorizer.return_value = mock_vec_instance
        mock_clf_instance = MagicMock(); mock_clf_instance.predict.return_value = [0]*(num_samples - int(num_samples*0.75))
        mock_clf_instance.predict_proba.return_value = [[0.9, 0.1]]*(num_samples - int(num_samples*0.75))
        mock_classifier.return_value = mock_clf_instance

        pipeline = training.train_and_save_model(features, labels, self.model_path)
        
        self.assertIsNotNone(pipeline)
        mock_joblib_dump.assert_called_once_with(pipeline, self.model_path)

    # --- Test save_data_for_finetuning (logic remains same) ---
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_save_data_for_finetuning_writes_correct_format(self, mock_json_dump, mock_file_open):
        labeled_data = [
            {"ip": "1.1.1.1", "label": "bot", "bot_score": 0.9, "timestamp_iso": "ts1", "user_agent": "BotUA"},
            {"ip": "2.2.2.2", "label": "human", "bot_score": 0.1, "timestamp_iso": "ts2", "user_agent": "HumanUA"},
        ]
        train_file_path = training.FINETUNE_TRAIN_FILE
        eval_file_path = training.FINETUNE_EVAL_FILE

        training.save_data_for_finetuning(labeled_data, train_file_path, eval_file_path, eval_ratio=0.5)
        
        # Check that open was called for train and eval files
        mock_file_open.assert_any_call(train_file_path, 'w', encoding='utf-8')
        mock_file_open.assert_any_call(eval_file_path, 'w', encoding='utf-8')
        
        # Check structure of data passed to json.dump
        self.assertGreater(mock_json_dump.call_count, 0)
        first_call_args = mock_json_dump.call_args_list[0][0][0]
        self.assertIn("log_data", first_call_args)
        self.assertIn("label", first_call_args)

    # --- Test __main__ block (conceptual) ---
    @patch("rag.training.setup_database")
    @patch("rag.training.load_logs_into_db")
    @patch("rag.training.label_data_with_scores")
    @patch("rag.training.train_and_save_model")
    @patch("rag.training.save_data_for_finetuning")
    def test_main_execution_flow_conceptual(self, mock_save_ft, mock_train_model, mock_label_data, mock_load_logs, mock_setup_db):
        mock_db_conn = MagicMock(spec=psycopg2.extensions.connection)
        mock_db_cursor = MagicMock(spec=psycopg2.extensions.cursor)
        mock_db_conn.cursor.return_value = mock_db_cursor
        # Simulate initial DB count check
        mock_db_cursor.fetchone.return_value = (0,) # Empty DB
        mock_setup_db.return_value = mock_db_conn
        
        mock_load_logs.return_value = True 
        mock_label_data.return_value = (
            [{"label": "bot", "bot_score": 0.9, "ip": "1.1.1.1", "timestamp_iso":"t1"}], 
            [{"feature": 1}], 
            [1] 
        )
        mock_train_model.return_value = MagicMock()

        # To simulate the main block, we'd call a main() function if training.py had one.
        # Here, we'll simulate the main execution flow by calling the functions
        # as they would be in the __main__ block.
        
        # Simulate the __main__ block's logic flow
        with patch.object(training, '__name__', '__main__'):
            # This reload will execute the __main__ block of the SUT
            # We need to ensure that the mocks are in place *before* the reload.
            # The patches at the method level handle this.
            importlib.reload(training)

        # Assertions based on the reloaded module's __main__ execution
        mock_setup_db.assert_called_once() # setup_database is called
        # Check if load_logs_into_db was called (it should be if DB was empty)
        mock_load_logs.assert_called_once_with(training.LOG_FILE_PATH, mock_db_conn)
        mock_label_data.assert_called_once_with(mock_db_conn)
        mock_train_model.assert_called_once()
        mock_save_ft.assert_called_once()
        mock_db_conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()

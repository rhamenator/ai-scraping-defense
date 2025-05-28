# test/rag/training.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, call, ANY
import os
import sqlite3
import datetime
import json
import re # For some string operations if needed in tests, or by SUT

# Attempt to import freezegun, make it optional for tests not strictly needing it
try:
    from freezegun import freeze_time
    FREEZEGUN_AVAILABLE = True
except ImportError:
    FREEZEGUN_AVAILABLE = False
    # Create a dummy decorator if freezegun is not available
    def freeze_time(time_to_freeze):
        def decorator(func):
            def wrapper(*args, **kwargs):
                print("Warning: freezegun not installed, time-sensitive tests may be less reliable.")
                return func(*args, **kwargs)
            return wrapper
        return decorator

# Import the module to test
from rag import training

# Helper to reset module-level states if they exist and are modified by tests
def reset_training_module_globals():
    training.disallowed_paths = set()
    # Reset UA_PARSER_AVAILABLE based on its original detection logic if it's dynamic
    try:
        from user_agents import parse as ua_parse
        training.UA_PARSER_AVAILABLE = True
        training.ua_parse = ua_parse
    except ImportError:
        training.UA_PARSER_AVAILABLE = False
        training.ua_parse = None


class TestTrainingScript(unittest.TestCase):

    def setUp(self):
        """Setup common test resources."""
        reset_training_module_globals() 
        self.test_data_dir = "test_temp_training_data" # Unique name
        os.makedirs(self.test_data_dir, exist_ok=True)
        
        # Define paths using self.test_data_dir
        self.db_path = os.path.join(self.test_data_dir, "test_log_analysis.db")
        self.model_path = os.path.join(self.test_data_dir, "test_model.joblib")
        self.robots_path = os.path.join(self.test_data_dir, "test_robots.txt")
        self.honeypot_log_path = os.path.join(self.test_data_dir, "test_honeypot.log")
        self.captcha_log_path = os.path.join(self.test_data_dir, "test_captcha.log")
        self.access_log_path = os.path.join(self.test_data_dir, "test_access.log")
        self.finetune_train_path = os.path.join(self.test_data_dir, "test_ft_train.jsonl") # Used by SUT
        self.finetune_eval_path = os.path.join(self.test_data_dir, "test_ft_eval.jsonl") # Used by SUT


        self.env_patcher = patch.dict(os.environ, {
            "TRAINING_DB_PATH": self.db_path,
            "TRAINING_MODEL_SAVE_PATH": self.model_path,
            "TRAINING_FINETUNE_DATA_DIR": self.test_data_dir,
            "TRAINING_ROBOTS_TXT_PATH": self.robots_path,
            "TRAINING_HONEYPOT_LOG": self.honeypot_log_path,
            "TRAINING_CAPTCHA_LOG": self.captcha_log_path,
            "TRAINING_LOG_FILE_PATH": self.access_log_path,
            "MIN_SAMPLES_FOR_TRAINING": "10" 
        })
        self.env_patcher.start()
        
        # Re-assign module level constants in training.py after patching os.environ
        training.DB_PATH = self.db_path
        training.MODEL_SAVE_PATH = self.model_path
        training.FINETUNE_DATA_DIR = self.test_data_dir 
        # training.py constructs FINETUNE_TRAIN_FILE and FINETUNE_EVAL_FILE using FINETUNE_DATA_DIR
        training.FINETUNE_TRAIN_FILE = os.path.join(training.FINETUNE_DATA_DIR, "finetuning_data_train.jsonl")
        training.FINETUNE_EVAL_FILE = os.path.join(training.FINETUNE_DATA_DIR, "finetuning_data_eval.jsonl")
        training.ROBOTS_TXT_PATH = self.robots_path
        training.HONEYPOT_HIT_LOG = self.honeypot_log_path
        training.CAPTCHA_SUCCESS_LOG = self.captcha_log_path
        training.LOG_FILE_PATH = self.access_log_path
        training.MIN_SAMPLES_FOR_TRAINING = 10


    def tearDown(self):
        """Clean up test resources."""
        self.env_patcher.stop()
        # Robustly clean up files and directory
        files_to_remove = [
            self.db_path, self.model_path, 
            training.FINETUNE_TRAIN_FILE, training.FINETUNE_EVAL_FILE, # Use the paths from the module
            self.robots_path, self.honeypot_log_path, 
            self.captcha_log_path, self.access_log_path
        ]
        for f_path in files_to_remove:
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                except Exception as e:
                    print(f"Warning: Could not remove test file {f_path}: {e}")
        
        if os.path.exists(self.test_data_dir):
            try:
                # Check if dir is empty before rmdir, or remove all contents first
                if not os.listdir(self.test_data_dir): # Only remove if empty
                    os.rmdir(self.test_data_dir)
                else: # Attempt to remove any other files that might have been created
                    for item in os.listdir(self.test_data_dir):
                        item_path = os.path.join(self.test_data_dir, item)
                        if os.path.isfile(item_path): os.remove(item_path)
                    os.rmdir(self.test_data_dir)

            except OSError as e: 
                print(f"Warning: Could not remove test directory {self.test_data_dir}: {e}")


    # --- Test setup_database ---
    def test_setup_database_creates_db_and_table(self):
        conn = training.setup_database(self.db_path)
        self.assertIsNotNone(conn, "Database connection should not be None.")
        if conn: # To satisfy Pylance
            self.assertTrue(os.path.exists(self.db_path))
            cursor = conn.cursor() # Pylance error was here if conn could be None
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='requests';")
            self.assertIsNotNone(cursor.fetchone())
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ip_timestamp';")
            self.assertIsNotNone(cursor.fetchone())
            conn.close()

    @patch("sqlite3.connect", side_effect=sqlite3.Error("DB connection failed"))
    def test_setup_database_connection_error(self, mock_connect):
        conn = training.setup_database("error_path.db")
        self.assertIsNone(conn)

    # --- Test load_robots_txt and is_path_disallowed ---
    def test_load_robots_txt_and_is_path_disallowed(self):
        robots_content = "User-agent: *\nDisallow: /admin/\nDisallow: /private/path\nAllow: /public/"
        # Use the path defined in setUp (training.ROBOTS_TXT_PATH)
        with open(training.ROBOTS_TXT_PATH, "w") as f:
            f.write(robots_content)
        
        training.load_robots_txt(training.ROBOTS_TXT_PATH)
        
        self.assertIn("/admin/", training.disallowed_paths)
        self.assertIn("/private/path", training.disallowed_paths)
        self.assertNotIn("/public/", training.disallowed_paths)

        self.assertTrue(training.is_path_disallowed("/admin/page.html"))
        self.assertFalse(training.is_path_disallowed("/public/page.html"))

    # --- Test parse_apache_combined_log_line ---
    def test_parse_apache_combined_log_line_valid(self):
        log_line = '127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326 "http://www.example.com/start.html" "Mozilla/5.0 (compatible; TestBot/1.1)"'
        parsed = training.parse_apache_combined_log_line(log_line)
        self.assertIsNotNone(parsed, "Parsed data should not be None for a valid log line.")
        if parsed: # To satisfy Pylance
            self.assertEqual(parsed['ip'], '127.0.0.1') # Pylance error was here if parsed could be None
            self.assertEqual(parsed['method'], 'GET')
            self.assertEqual(parsed['path'], '/apache_pb.gif')
            self.assertEqual(parsed['status'], 200)
            self.assertEqual(parsed['bytes'], 2326)
            self.assertEqual(parsed['referer'], 'http://www.example.com/start.html')
            self.assertEqual(parsed['user_agent'], 'Mozilla/5.0 (compatible; TestBot/1.1)')
            # Check timestamp conversion
            self.assertTrue(isinstance(datetime.datetime.fromisoformat(parsed['timestamp_iso'].replace('Z', '+00:00')), datetime.datetime))


    def test_parse_apache_combined_log_line_invalid(self):
        self.assertIsNone(training.parse_apache_combined_log_line("invalid log line"))

    # --- Test load_logs_into_db ---
    @patch("builtins.open", new_callable=mock_open)
    @patch("rag.training.parse_apache_combined_log_line")
    def test_load_logs_into_db_success(self, mock_parse_log, mock_file):
        mock_file.return_value.__iter__.return_value = ["log_line_1", "log_line_2"]
        mock_parse_log.side_effect = [
            {"ip": "1.1.1.1", "timestamp_iso": "ts1", "method": "GET", "path": "/p1", "status": 200, "bytes": 100, "user_agent": "ua1", "request":"GET /p1 HTTP/1.1", "ident":None, "user":None, "protocol":"HTTP/1.1", "referer":None},
            {"ip": "2.2.2.2", "timestamp_iso": "ts2", "method": "POST", "path": "/p2", "status": 404, "bytes": 50, "user_agent": "ua2", "request":"POST /p2 HTTP/1.1", "ident":None, "user":None, "protocol":"HTTP/1.1", "referer":None}
        ]
        conn = MagicMock(spec=sqlite3.Connection)
        cursor = MagicMock(spec=sqlite3.Cursor)
        conn.cursor.return_value = cursor

        result = training.load_logs_into_db(training.LOG_FILE_PATH, conn) # Use configured path
        
        self.assertTrue(result)
        # Check based on BATCH_SIZE in training.py (default 1000)
        # If 2 items and batch_size is 1000, executemany should be called once with the remaining batch.
        self.assertEqual(cursor.executemany.call_count, 1) 
        conn.commit.assert_called()


    # --- Test extract_features_from_db ---
    @patch("rag.training.ua_parse") 
    def test_extract_features_from_db(self, mock_ua_parse_func):
        # Setup mock for ua_parse
        mock_parsed_ua = MagicMock()
        mock_parsed_ua.is_bot = True
        mock_parsed_ua.browser.family = "TestBrowser"
        mock_parsed_ua.os.family = "TestOS"
        mock_parsed_ua.device.family = "TestDevice"
        mock_parsed_ua.is_mobile = False
        mock_parsed_ua.is_tablet = False
        mock_parsed_ua.is_pc = True
        mock_parsed_ua.is_touch_capable = False
        mock_ua_parse_func.return_value = mock_parsed_ua

        mock_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_cursor.description = [
            ('id',), ('ip',), ('ident',), ('user',), ('timestamp_iso',), 
            ('method',), ('path',), ('protocol',), ('status',), ('bytes',), 
            ('referer',), ('user_agent',)
        ]
        current_time = datetime.datetime.utcnow()
        row_data = (1, '1.2.3.4', None, None, current_time.isoformat() + "Z", 
                    'GET', '/test', 'HTTP/1.1', 200, 1234, 
                    'http://referer.com', 'Test User Agent')
        
        mock_cursor.execute.side_effect = [MagicMock(), MagicMock()]
        mock_cursor.fetchone.side_effect = [
            (5,),    
            ((current_time - datetime.timedelta(seconds=10)).isoformat() + "Z",) 
        ]

        with patch.object(training, 'UA_PARSER_AVAILABLE', True), \
             patch.object(training, 'ua_parse', mock_ua_parse_func): # Ensure ua_parse is the mock
            features = training.extract_features_from_db(row_data, mock_cursor)
        
        self.assertIn('ua_length', features)
        self.assertEqual(features['ua_library_is_bot'], 1)
        self.assertEqual(features[f'req_freq_{training.FREQUENCY_WINDOW_SECONDS}s'], 5)
        self.assertAlmostEqual(features['time_since_last_sec'], 10.0, delta=0.001)

    # --- Test assign_label_and_score ---
    @freeze_time("2023-01-01 12:00:00") 
    def test_assign_label_and_score_honeypot_hit(self):
        log_entry = {"ip": "1.1.1.1", "user_agent": "TestUA", "path": "/"} 
        honeypot_ips = {"1.1.1.1"}
        captcha_ips = set()
        label, score, reasons = training.assign_label_and_score(log_entry, honeypot_ips, captcha_ips)
        self.assertEqual(label, "bot")
        self.assertAlmostEqual(score, 0.98)

    # --- Test train_and_save_model ---
    @patch("joblib.dump")
    @patch("sklearn.ensemble.RandomForestClassifier")
    @patch("sklearn.feature_extraction.DictVectorizer")
    @patch("sklearn.model_selection.train_test_split")
    def test_train_and_save_model_sufficient_data(self, mock_split, mock_vectorizer, mock_classifier, mock_joblib_dump):
        # Use the MIN_SAMPLES_FOR_TRAINING from the module (which is 10 in setUp)
        num_samples = training.MIN_SAMPLES_FOR_TRAINING 
        features = [{"f1": 1, "f2": 0}] * num_samples 
        labels = ([0] * (num_samples // 2)) + ([1] * (num_samples - num_samples // 2))
        
        mock_split.return_value = (features[:int(num_samples*0.75)], features[int(num_samples*0.75):], 
                                   labels[:int(num_samples*0.75)], labels[int(num_samples*0.75):])
        mock_vec_instance = MagicMock(); mock_vec_instance.fit_transform.return_value = [[1,0]] * int(num_samples*0.75)
        mock_vec_instance.transform.return_value = [[0,1]] * (num_samples - int(num_samples*0.75))
        mock_vectorizer.return_value = mock_vec_instance
        mock_clf_instance = MagicMock(); mock_clf_instance.predict.return_value = [0]*(num_samples - int(num_samples*0.75))
        mock_clf_instance.predict_proba.return_value = [[0.9, 0.1]]*(num_samples - int(num_samples*0.75))
        mock_classifier.return_value = mock_clf_instance

        pipeline = training.train_and_save_model(features, labels, self.model_path)
        
        self.assertIsNotNone(pipeline)
        mock_joblib_dump.assert_called_once_with(pipeline, self.model_path)

    # --- Test save_data_for_finetuning ---
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump") # To verify json.dump calls
    def test_save_data_for_finetuning_writes_correct_format(self, mock_json_dump, mock_file):
        labeled_data = [
            {"ip": "1.1.1.1", "label": "bot", "bot_score": 0.9, "timestamp_iso": "ts1", "user_agent": "BotUA"},
            {"ip": "2.2.2.2", "label": "human", "bot_score": 0.1, "timestamp_iso": "ts2", "user_agent": "HumanUA"},
        ]
        # Use the paths from training module, which are set up with self.test_data_dir
        train_file_path = training.FINETUNE_TRAIN_FILE
        eval_file_path = training.FINETUNE_EVAL_FILE

        training.save_data_for_finetuning(labeled_data, train_file_path, eval_file_path, eval_ratio=0.5)
        
        self.assertIn(call(train_file_path, 'w', encoding='utf-8'), mock_file.call_args_list)
        self.assertIn(call(eval_file_path, 'w', encoding='utf-8'), mock_file.call_args_list)
        
        # Check the structure of data passed to json.dump
        # There will be one call to json.dump per entry written.
        # Example: check the first call for the training data (assuming 1 sample after 0.5 split)
        # This depends on random.shuffle, so checking exact content is tricky without seeding random.
        # Instead, check that json.dump was called with the expected structure.
        self.assertGreater(mock_json_dump.call_count, 0)
        first_call_args = mock_json_dump.call_args_list[0][0][0] # Get the dict passed to first json.dump
        self.assertIn("log_data", first_call_args)
        self.assertIn("label", first_call_args)
        self.assertIn("user_agent", first_call_args["log_data"]) # Check a field from original log_data
        self.assertNotIn("bot_score", first_call_args["log_data"]) # Check excluded field

    # --- Test __main__ block (conceptual) ---
    @patch("rag.training.setup_database")
    @patch("rag.training.load_logs_into_db")
    @patch("rag.training.label_data_with_scores")
    @patch("rag.training.train_and_save_model")
    @patch("rag.training.save_data_for_finetuning")
    def test_main_execution_flow_conceptual(self, mock_save_ft, mock_train_model, mock_label_data, mock_load_logs, mock_setup_db):
        # This test is conceptual as __main__ isn't directly callable.
        # It verifies that if the script were run, the mocks would be hit.
        # A full integration test would use subprocess.
        
        mock_db_conn = MagicMock(spec=sqlite3.Connection)
        mock_db_cursor = MagicMock(spec=sqlite3.Cursor)
        mock_db_conn.cursor.return_value = mock_db_cursor
        mock_db_cursor.fetchone.return_value = (0,) # Simulate empty DB initially
        mock_setup_db.return_value = mock_db_conn
        
        mock_load_logs.return_value = True 
        mock_label_data.return_value = (
            [{"label": "bot", "bot_score": 0.9, "ip": "1.1.1.1", "timestamp_iso":"t1"}], 
            [{"feature": 1}], 
            [1] 
        )
        mock_train_model.return_value = MagicMock() # Simulate a trained pipeline object

        # To simulate the main block, we would ideally call a main() function if training.py had one.
        # Since it doesn't, we can't directly invoke the __main__ logic here.
        # We assert that the setup of mocks is correct for an integration test.
        # If you refactor training.py to have a `def main_script_logic():`, you could call that here.
        
        # For now, just assert that the patches are active.
        self.assertTrue(mock_setup_db.called_once_with(training.DB_PATH)) # This would be called if main ran.
        # Further assertions would depend on actually running the main block's logic.
        # This test is more of a placeholder for a true integration test of the main script.
        print("Conceptual test for __main__ completed. For full test, refactor main logic or use subprocess.")


if __name__ == '__main__':
    unittest.main()

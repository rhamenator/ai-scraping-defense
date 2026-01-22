# test/rag/training.test.py
import datetime
import importlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, mock_open, patch

import pandas as pd

from rag import training


class TestTrainingPipelineComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up a clean environment for each test."""
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(self.test_dir, exist_ok=True)

        self.model_path = os.path.join(self.test_dir, "model.joblib")
        self.robots_path = os.path.join(self.test_dir, "robots.txt")
        self.honeypot_log_path = os.path.join(self.test_dir, "honeypot.log")
        self.captcha_log_path = os.path.join(self.test_dir, "captcha.log")
        self.finetune_train_path = os.path.join(self.test_dir, "ft_train.jsonl")
        self.finetune_eval_path = os.path.join(self.test_dir, "ft_eval.jsonl")
        self.pg_password_path = os.path.join(self.test_dir, "pgpass")

        with open(self.pg_password_path, "w") as f:
            f.write("testpass")

        self.env_patcher = patch.dict(
            os.environ,
            {
                "TRAINING_MODEL_SAVE_PATH": self.model_path,
                "TRAINING_FINETUNE_TRAIN_FILE": self.finetune_train_path,
                "TRAINING_FINETUNE_EVAL_FILE": self.finetune_eval_path,
                "TRAINING_ROBOTS_TXT_PATH": self.robots_path,
                "TRAINING_HONEYPOT_LOG": self.honeypot_log_path,
                "TRAINING_CAPTCHA_LOG": self.captcha_log_path,
                "MIN_SAMPLES_FOR_TRAINING": "10",
                "PG_HOST": "mock-pg-host",
                "TRAINING_PG_PASSWORD_FILE": self.pg_password_path,
            },
        )
        self.env_patcher.start()
        sys.modules.setdefault("markov_train_rs", MagicMock())
        if "src.rag" not in sys.modules:
            importlib.import_module("src.rag")
        importlib.reload(training)

    def tearDown(self):
        """Clean up the environment after each test."""
        self.env_patcher.stop()
        import shutil

        shutil.rmtree(self.test_dir)

    def test_load_robots_txt(self):
        """Test loading and parsing of the robots.txt file."""
        with open(self.robots_path, "w") as f:
            f.write("User-agent: *\nDisallow: /admin/\nDisallow: /private/data\n")

        # Corrected: Pass the path argument to the function as required.
        training.load_robots_txt(self.robots_path)
        self.assertIn("/admin/", training.disallowed_paths)
        self.assertIn("/private/data", training.disallowed_paths)
        self.assertNotIn("/", training.disallowed_paths)

    def test_load_feedback_data(self):
        """Test loading feedback data from honeypot and captcha logs."""
        with open(self.honeypot_log_path, "w") as f:
            f.write('{"ip": "1.1.1.1", "path": "/login.php"}\\n')
            f.write('{"ip": "2.2.2.2", "path": "/admin"}\\n')
        with open(self.captcha_log_path, "w") as f:
            f.write('{"ip": "3.3.3.3", "result": "success"}\\n')
            f.write('{"ip": "4.4.4.4", "result": "failure"}\\n')

        honeypot_ips, captcha_ips = training.load_feedback_data()
        self.assertEqual(honeypot_ips, {"1.1.1.1", "2.2.2.2"})
        self.assertEqual(captcha_ips, {"3.3.3.3"})  # Only successes are counted

    def test_lookup_country_code(self):
        fake_resp = MagicMock()
        fake_resp.country.iso_code = "US"
        fake_reader = MagicMock()
        fake_reader.country.return_value = fake_resp
        with patch("geoip2.database.Reader", return_value=fake_reader):
            with tempfile.NamedTemporaryFile() as tmpfile:
                with patch.object(training, "GEOIP_DB_PATH", tmpfile.name):
                    training._geoip_reader = None
                    code = training.lookup_country_code("8.8.8.8")
        self.assertEqual(code, "US")

    def test_assign_labels_and_scores(self):
        """Test the comprehensive labeling logic based on multiple factors."""
        training.disallowed_paths = {"/admin/"}
        honeypot_ips = {"1.1.1.1"}
        captcha_ips = {"3.3.3.3"}

        df = pd.DataFrame(
            {
                "ip": ["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4", "5.5.5.5"],
                "user_agent": ["BadBot", "GoodBot", "Mozilla", "python-requests", ""],
                "path": ["/login.php", "/index.html", "/home", "/admin/panel", "/"],
                "status": [200, 200, 200, 403, 500],
                "referer": ["-", "google.com", "-", "-", "-"],
                "req_freq_60s": [100, 5, 1, 50, 2],
                "time_since_last_sec": [0.1, 20, 60, 0.5, 30],
            }
        )

        labeled_df = training.assign_labels_and_scores(df, honeypot_ips, captcha_ips)

        # Honeypot IP -> bot
        self.assertEqual(labeled_df[labeled_df.ip == "1.1.1.1"].label.iloc[0], "bot")
        # Captcha Success IP -> human
        self.assertEqual(labeled_df[labeled_df.ip == "3.3.3.3"].label.iloc[0], "human")
        # High frequency, disallowed path, known bad UA -> bot
        self.assertEqual(labeled_df[labeled_df.ip == "4.4.4.4"].label.iloc[0], "bot")
        # Empty UA should get a high score -> bot
        self.assertEqual(labeled_df[labeled_df.ip == "5.5.5.5"].label.iloc[0], "bot")
        # Benign-looking request -> human
        self.assertEqual(labeled_df[labeled_df.ip == "2.2.2.2"].label.iloc[0], "human")

    @patch("rag.training.joblib.dump")
    @patch("sklearn.ensemble.RandomForestClassifier.fit")
    def test_train_and_save_model(self, mock_fit, mock_dump):
        """Test that the model training function runs, fits, and saves a model."""
        df = pd.DataFrame(
            {
                "label": ["bot"] * 5 + ["human"] * 5,
                "ua_length": range(10),
                "status": [200] * 10,
                "bytes": range(100, 110),
                "path_depth": range(10),
                "path_length": range(10, 20),
                "path_is_root": [1, 0] * 5,
                "path_is_wp": [0] * 10,
                "path_disallowed": [1] * 5 + [0] * 5,
                "ua_is_known_bad": [1] * 5 + [0] * 5,
                "ua_is_known_benign_crawler": [0] * 10,
                "ua_is_empty": [0] * 10,
                "referer_is_empty": [1] * 10,
                "hour_of_day": range(10),
                "day_of_week": [d % 7 for d in range(10)],
                "req_freq_60s": range(10),
                "time_since_last_sec": range(10),
                "country_code_id": [0] * 10,
            }
        )

        training.train_and_save_model(df, self.model_path)

        mock_fit.assert_called_once()
        mock_dump.assert_called_once()
        self.assertEqual(mock_dump.call_args[0][1], self.model_path)

    def test_save_data_for_finetuning(self):
        """Test that data is correctly formatted and saved for fine-tuning."""
        df = pd.DataFrame(
            {
                "label": ["bot", "human"],
                "bot_score": [0.95, 0.05],
                "labeling_reasons": [["High Freq", "Bad UA"], ["Low Score"]],
                "ip": ["1.1.1.1", "2.2.2.2"],
                "user_agent": ["Bot/1.0", "Mozilla"],
                "timestamp": [
                    datetime.datetime.now(datetime.timezone.utc),
                    datetime.datetime.now(datetime.timezone.utc),
                ],
            }
        )

        training.save_data_for_finetuning(
            df, self.finetune_train_path, self.finetune_eval_path, 0.5
        )

        self.assertTrue(os.path.exists(self.finetune_train_path))
        with open(self.finetune_train_path, "r") as f:
            record = json.loads(f.readline())
            self.assertIn("log_data", record)
            self.assertIn("label", record)
            log_data_inner = json.loads(record["log_data"])
            self.assertEqual(log_data_inner["ip"], "1.1.1.1")
            self.assertNotIn("bot_score", log_data_inner)
        self.assertNotIn("labeling_reasons", log_data_inner)

    @patch("rag.training.joblib.dump")
    def test_model_accuracy_comparison(self, mock_dump):
        """Ensure RandomForest, XGBoost, and Logistic Regression train and return accuracy."""
        df = pd.DataFrame(
            {
                "label": ["bot"] * 10 + ["human"] * 10,
                "ua_length": [20] * 20,
                "status": [200] * 20,
                "bytes": [150] * 20,
                "path_depth": [1] * 20,
                "path_length": [10] * 20,
                "path_is_root": [0] * 20,
                "path_is_wp": [0] * 20,
                "path_disallowed": [1] * 10 + [0] * 10,
                "ua_is_known_bad": [1] * 10 + [0] * 10,
                "ua_is_known_benign_crawler": [0] * 20,
                "ua_is_empty": [0] * 20,
                "referer_is_empty": [1] * 20,
                "hour_of_day": [12] * 20,
                "day_of_week": [1] * 20,
                "req_freq_60s": [50] * 10 + [1] * 10,
                "time_since_last_sec": [0.1] * 10 + [10] * 10,
                "country_code_id": [0] * 20,
            }
        )

        _, acc_rf = training.train_and_save_model(df, self.model_path, "rf")
        _, acc_xgb = training.train_and_save_model(df, self.model_path, "xgb")
        _, acc_lr = training.train_and_save_model(df, self.model_path, "lr")

        self.assertGreaterEqual(acc_rf, 0.9)
        self.assertGreaterEqual(acc_xgb, 0.9)
        self.assertGreaterEqual(acc_lr, 0.8)


if __name__ == "__main__":
    unittest.main()

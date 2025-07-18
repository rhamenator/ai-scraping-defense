# test/rag/finetune.test.py
import unittest
from unittest.mock import patch, MagicMock
import os
import json
import numpy as np
import tempfile
import shutil

from rag import finetune

class TestFinetuneScriptComprehensive(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.test_dir, 'data')
        self.model_dir = os.path.join(self.test_dir, 'model')
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.model_dir, exist_ok=True)

        self.train_file = os.path.join(self.data_dir, "train.jsonl")
        self.eval_file = os.path.join(self.data_dir, "eval.jsonl")

        # Create dummy data files with more realistic, nested JSON
        self.log_entry_bot = {"ip": "1.1.1.1", "user_agent": "BadBot", "headers": {"X-Evil": "true"}}
        self.log_entry_human = {"ip": "2.2.2.2", "user_agent": "Mozilla/5.0", "headers": {"Accept-Language": "en-US"}}
        
        with open(self.train_file, 'w') as f:
            f.write(json.dumps({"log_data": json.dumps(self.log_entry_bot), "label": "bot"}) + '\\n')
        with open(self.eval_file, 'w') as f:
            f.write(json.dumps({"log_data": json.dumps(self.log_entry_human), "label": "human"}) + '\\n')
            
        self.env_patcher = patch.dict(os.environ, {
            "TRAINING_DATA_FILE": self.train_file,
            "VALIDATION_DATA_FILE": self.eval_file,
            "OUTPUT_DIR": self.model_dir,
            "MODEL_NAME": "distilbert-base-uncased" # Use a known model for consistency
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        shutil.rmtree(self.test_dir)

    def test_prepare_text_for_model(self):
        """Test the text preparation function with complex log data."""
        log_entry = {
            "ip": "192.168.1.1", "user_agent": "TestAgent/1.0", "method": "POST",
            "path": "/api/v2/users", "status": 403, "referer": "http://evil.com",
            "headers": {"Accept": "application/json", "X-Custom-Header": "Value123", "Content-Length": "50"}
        }
        text = finetune.prepare_text_for_model(log_entry)
        
        self.assertIn("[IP:192.168.1.1]", text)
        self.assertIn("[UA:TestAgent/1.0]", text)
        self.assertIn("[M:POST]", text)
        self.assertIn("[P:/api/v2/users]", text)
        self.assertIn("[S:403]", text)
        self.assertIn("[R:http://evil.com]", text)
        self.assertIn("Accept=application/json", text)
        self.assertIn("X-Custom-Header=Value123", text)
        # Check that unimportant headers are excluded
        self.assertNotIn("Content-Length", text)

    @patch("rag.finetune.load_dataset")
    def test_load_and_prepare_dataset(self, mock_load_dataset):
        """Test data loading, JSON parsing, and tokenization."""
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {"input_ids": [[1,2,3]], "attention_mask": [[1,1,1]]}
        
        # Simulate the behavior of the Hugging Face `map` function
        def map_side_effect(func, **kwargs):
            batch = {'log_data': [json.dumps(self.log_entry_bot)], 'label': ['bot']}
            return func(batch)
            
        mock_dataset = MagicMock()
        mock_dataset.map.side_effect = map_side_effect
        mock_load_dataset.return_value = mock_dataset

        prepared_data = finetune.load_and_prepare_dataset(self.train_file, mock_tokenizer)
        
        self.assertIsNotNone(prepared_data)
        # Check that the tokenizer was applied
        self.assertIn('input_ids', prepared_data)
        # Check that the label was correctly mapped
        self.assertEqual(prepared_data['label'], [1]) # bot -> 1

    def test_compute_metrics(self):
        """Test the metrics computation for evaluation, including argmax logic."""
        with patch('rag.finetune.evaluate.load') as mock_evaluate_load:
            mock_metric = MagicMock()
            # Simulate a metric object that can compute accuracy and f1
            mock_metric.compute.side_effect = [
                {'accuracy': 0.75}, # First call for accuracy
                {'f1': 0.66}         # Second call for f1
            ]
            mock_evaluate_load.return_value = mock_metric
            
            # Logits represent the raw output from the model for two examples
            logits = np.array([[0.1, 0.9], [0.8, 0.2]]) # Predicts class 1, then class 0
            labels = np.array([1, 0])
            eval_pred = (logits, labels)
            
            metrics = finetune.compute_metrics(eval_pred)
            
            # The predictions should be the argmax of the logits
            predictions = np.argmax(logits, axis=-1)
            self.assertTrue(np.array_equal(predictions, np.array([1, 0])))
            
            # Check that the metrics were computed correctly
            self.assertEqual(metrics['accuracy'], 0.75)
            self.assertEqual(metrics['f1'], 0.66)

    @patch('rag.finetune.Trainer')
    @patch('rag.finetune.TrainingArguments')
    @patch('rag.finetune.AutoModelForSequenceClassification')
    @patch('rag.finetune.AutoTokenizer.from_pretrained')
    @patch('rag.finetune.load_and_prepare_dataset')
    def test_fine_tune_model_full_flow(self, mock_load_data, mock_tokenizer, mock_model_cls, mock_train_args, mock_trainer):
        """Test the main fine_tune_model function orchestrates correctly."""
        # Setup mocks to return other mocks
        mock_tokenizer.return_value = MagicMock()
        mock_model_cls.from_pretrained.return_value = MagicMock()
        mock_load_data.return_value = MagicMock() # Mock dataset object
        mock_trainer_instance = MagicMock()
        mock_trainer_instance.train.return_value = MagicMock(metrics={"train_loss": 0.123})
        mock_trainer.return_value = mock_trainer_instance

        # Run the main function
        finetune.fine_tune_model()

        # Assert that the main components were called as expected
        mock_tokenizer.assert_called_with("distilbert-base-uncased")
        self.assertEqual(mock_load_data.call_count, 2)
        mock_model_cls.from_pretrained.assert_called_with("distilbert-base-uncased", num_labels=2)
        mock_train_args.assert_called()
        mock_trainer.assert_called()
        mock_trainer_instance.train.assert_called()
        mock_trainer_instance.save_model.assert_called()

if __name__ == '__main__':
    unittest.main()

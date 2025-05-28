# test/rag/finetune.test.py
import unittest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import json
import numpy as np

# Import the module to test
from rag import finetune

# Mock external library objects that would normally be imported
# We can patch these at the module level where finetune.py imports them.

class TestFinetuneScript(unittest.TestCase):

    def setUp(self):
        self.test_output_dir = "test_finetune_output_v3" 
        self.test_data_dir = os.path.join(self.test_output_dir, "data")
        self.test_model_dir = os.path.join(self.test_output_dir, "model")
        self.test_log_dir = os.path.join(self.test_output_dir, "logs")

        os.makedirs(self.test_data_dir, exist_ok=True)
        os.makedirs(self.test_model_dir, exist_ok=True)
        os.makedirs(self.test_log_dir, exist_ok=True)

        self.dummy_train_file = os.path.join(self.test_data_dir, "finetuning_data_train.jsonl")
        self.dummy_eval_file = os.path.join(self.test_data_dir, "finetuning_data_eval.jsonl")

        self.sample_log_entry_dict = {
            "ip": "1.2.3.4", "user_agent": "TestBot/1.0", "method": "GET",
            "path": "/test", "status": 200, "referer": "http://example.com",
            "headers": {"Accept-Language": "en-US"}
        }
        # Create dummy files with content
        with open(self.dummy_train_file, 'w') as f:
            json.dump({"log_data": self.sample_log_entry_dict, "label": "bot"}, f); f.write('\n')
            json.dump({"log_data": {**self.sample_log_entry_dict, "ip":"1.2.3.5"}, "label": "human"}, f); f.write('\n')
        with open(self.dummy_eval_file, 'w') as f:
            json.dump({"log_data": {**self.sample_log_entry_dict, "ip":"1.2.3.6"}, "label": "bot"}, f); f.write('\n')


        self.env_patcher = patch.dict(os.environ, {
            "FINETUNE_DATA_DIR": self.test_data_dir, 
            "OUTPUT_DIR": self.test_model_dir,
            "LOGGING_DIR": self.test_log_dir,
            "BASE_MODEL_NAME": "mock-distilbert-base-uncased", 
            "NUM_TRAIN_EPOCHS": "1", 
            "PER_DEVICE_TRAIN_BATCH_SIZE": "1",
            "PER_DEVICE_EVAL_BATCH_SIZE": "1",
            "LOGGING_STEPS": "1",
            "EVAL_STEPS": "1",
            "SAVE_STEPS": "1",
            "MAX_SEQ_LENGTH": "128"
        })
        self.env_patcher.start()

        import importlib
        importlib.reload(finetune)


    def tearDown(self):
        self.env_patcher.stop()
        # Robust cleanup
        if os.path.exists(self.dummy_train_file): os.remove(self.dummy_train_file)
        if os.path.exists(self.dummy_eval_file): os.remove(self.dummy_eval_file)
        
        # Clean up directories, handling potential errors if files still exist
        for dir_path in [self.test_data_dir, self.test_model_dir, self.test_log_dir, self.test_output_dir]:
            if os.path.exists(dir_path):
                try:
                    for item in os.listdir(dir_path): # Remove files first if dir is not empty
                        item_path = os.path.join(dir_path, item)
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path): # Basic recursive removal for one level
                            for sub_item in os.listdir(item_path):
                                os.remove(os.path.join(item_path, sub_item))
                            os.rmdir(item_path)
                    os.rmdir(dir_path)
                except OSError: # Catch error if dir still not empty or other issues
                    # print(f"Warning: Could not completely remove test directory {dir_path}")
                    pass 
        
        import importlib 
        importlib.reload(finetune)


    def test_prepare_text_for_model(self):
        log_entry = {
            "ip": "192.168.1.1", "user_agent": "TestAgent", "method": "GET",
            "path": "/api/data", "status": 200, "referer": "None",
            "headers": {"Accept": "application/json", "X-Custom": "TestValue"}
        }
        text = finetune.prepare_text_for_model(log_entry)
        self.assertIsInstance(text, str)
        self.assertIn("[IP:192.168.1.1]", text)
        self.assertIn("Accept=application/json", text) 
        self.assertNotIn("X-Custom", text) 

        log_entry_minimal = {"ip": "10.0.0.1", "method": "POST", "status": 404}
        text_minimal = finetune.prepare_text_for_model(log_entry_minimal)
        self.assertIn("[UA:None]", text_minimal)
        self.assertEqual(finetune.prepare_text_for_model("not a dict"), "")


    @patch("rag.finetune.load_dataset") 
    @patch("rag.finetune.AutoTokenizer.from_pretrained")
    def test_load_and_prepare_dataset_success(self, mock_tokenizer_from_pretrained, mock_hf_load_dataset):
        mock_tokenizer_instance = MagicMock()
        mock_tokenizer_instance.return_value = {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}
        mock_tokenizer_from_pretrained.return_value = mock_tokenizer_instance

        class DummyHFDataset:
            def __init__(self, data_dict):
                self.data = data_dict
                self._length = len(data_dict[next(iter(data_dict))]) 

            def map(self, function, batched=False, remove_columns=None):
                batch_input = {key: [] for key in self.data.keys()}
                for i in range(self._length):
                    for key in self.data.keys():
                        batch_input[key].append(self.data[key][i])
                processed_batch = function(batch_input)
                return processed_batch 

            def __len__(self):
                return self._length

        sample_data_for_hf = {
            'log_data': [json.dumps(self.sample_log_entry_dict)], 
            'label': ['bot']
        }
        mock_hf_load_dataset.return_value = DummyHFDataset(sample_data_for_hf)

        dataset_result = finetune.load_and_prepare_dataset(self.dummy_train_file, mock_tokenizer_instance)

        self.assertIsNotNone(dataset_result, "Dataset should not be None on success.")
        self.assertIsInstance(dataset_result, dict, "Processed dataset should be a dictionary.")
        
        # Explicit check and assignment for Pylance type narrowing
        if isinstance(dataset_result, dict):
            # Now Pylance should be confident dataset_result is a dict and not None
            self.assertIn("input_ids", dataset_result) # Line 143 in user's error context
            self.assertIn("label", dataset_result)     
            self.assertEqual(dataset_result["label"], [1]) 
        else:
            # This case should not be reached if the above assertions pass
            self.fail("dataset_result was not a dictionary or was None, despite assertions.")


    @patch("rag.finetune.load_dataset", side_effect=FileNotFoundError("Mocked File Not Found"))
    def test_load_and_prepare_dataset_file_not_found(self, mock_hf_load_dataset):
        mock_tokenizer = MagicMock()
        dataset = finetune.load_and_prepare_dataset("nonexistent.jsonl", mock_tokenizer)
        self.assertIsNone(dataset)

    def test_compute_metrics(self):
        mock_accuracy_metric = MagicMock()
        mock_accuracy_metric.compute.return_value = {"accuracy": 0.85}
        mock_f1_metric = MagicMock()
        mock_f1_metric.compute.return_value = {"f1": 0.80}

        with patch("evaluate.load") as mock_evaluate_load:
            mock_evaluate_load.side_effect = lambda name: mock_accuracy_metric if name == "accuracy" else mock_f1_metric
            
            logits = np.array([[0.1, 0.9], [0.8, 0.2], [0.6, 0.4], [0.3, 0.7]]) 
            labels = np.array([1, 0, 0, 1]) 
            eval_pred = (logits, labels)
            
            metrics = finetune.compute_metrics(eval_pred)
            
            self.assertAlmostEqual(metrics["accuracy"], 0.85)
            self.assertAlmostEqual(metrics["f1"], 0.80)


    @patch("rag.finetune.AutoTokenizer.from_pretrained")
    @patch("rag.finetune.load_and_prepare_dataset")
    @patch("rag.finetune.AutoModelForSequenceClassification.from_pretrained")
    @patch("rag.finetune.TrainingArguments")
    @patch("rag.finetune.DataCollatorWithPadding")
    @patch("rag.finetune.Trainer")
    @patch("os.makedirs") 
    def test_fine_tune_model_full_flow(
        self, mock_trainer_cls, mock_collator_cls, mock_args_cls, 
        mock_model_from_pretrained, mock_load_prepare, mock_tokenizer_from_pretrained,
        mock_os_makedirs
    ):
        mock_tokenizer_instance = MagicMock(name="tokenizer_instance")
        mock_tokenizer_from_pretrained.return_value = mock_tokenizer_instance
        mock_train_dataset = MagicMock(name="train_dataset")
        # Ensure mock_train_dataset is Sized for len() in finetune.py if called by Trainer
        mock_train_dataset.__len__.return_value = 10 
        mock_eval_dataset = MagicMock(name="eval_dataset")
        mock_load_prepare.side_effect = [mock_train_dataset, mock_eval_dataset]
        
        mock_model_instance = MagicMock(name="model_instance")
        mock_model_from_pretrained.return_value = mock_model_instance
        mock_training_args_instance = MagicMock(name="training_args_instance")
        mock_args_cls.return_value = mock_training_args_instance
        mock_data_collator_instance = MagicMock(name="data_collator_instance")
        mock_collator_cls.return_value = mock_data_collator_instance
        mock_trainer_instance = MagicMock(name="trainer_instance")
        mock_trainer_instance.train.return_value = MagicMock(metrics={"train_loss": 0.1})
        mock_trainer_instance.evaluate.return_value = {"eval_accuracy": 0.9}
        mock_trainer_cls.return_value = mock_trainer_instance

        finetune.fine_tune_model()

        mock_tokenizer_from_pretrained.assert_called_once_with(finetune.BASE_MODEL_NAME)
        self.assertEqual(mock_load_prepare.call_count, 2)
        mock_model_from_pretrained.assert_called_once_with(finetune.BASE_MODEL_NAME, num_labels=2)
        mock_trainer_instance.train.assert_called_once()
        mock_trainer_instance.evaluate.assert_called_once_with(eval_dataset=mock_eval_dataset)
        mock_trainer_instance.save_model.assert_called_once()

    @patch("rag.finetune.load_and_prepare_dataset", return_value=None) 
    @patch("rag.finetune.AutoTokenizer.from_pretrained")
    @patch.object(finetune, 'print') 
    def test_fine_tune_model_dataset_load_failure(self, mock_print, mock_tokenizer_load, mock_dataset_load):
        mock_tokenizer_load.return_value = MagicMock() 
        finetune.fine_tune_model()
        printed_error = False
        for call_args in mock_print.call_args_list:
            if "ERROR: Could not load datasets. Aborting fine-tuning." in call_args[0][0]:
                printed_error = True; break
        self.assertTrue(printed_error)

    @patch("os.makedirs")
    @patch("rag.finetune.fine_tune_model")
    def test_main_block_execution(self, mock_fine_tune_func, mock_makedirs):
        # This test simulates the calls made if __name__ == "__main__" is true.
        # It requires finetune.OUTPUT_DIR and finetune.LOGGING_DIR to be set,
        # which they are by the env_patcher in setUp and module reload.
        
        # Simulate the calls made in the __main__ block
        # We are not actually running the script as main, but testing its intended calls.
        finetune.os.makedirs(finetune.OUTPUT_DIR, exist_ok=True)
        finetune.os.makedirs(finetune.LOGGING_DIR, exist_ok=True)
        finetune.fine_tune_model() # This will use the mocked version

        mock_makedirs.assert_any_call(finetune.OUTPUT_DIR, exist_ok=True)
        mock_makedirs.assert_any_call(finetune.LOGGING_DIR, exist_ok=True)
        mock_fine_tune_func.assert_called_once()


if __name__ == '__main__':
    unittest.main()

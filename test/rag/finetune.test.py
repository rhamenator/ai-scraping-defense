# test\rag\finetune.test.py
import unittest
from unittest.mock import patch, MagicMock
from rag import finetune

class TestFinetune(unittest.TestCase):

    @patch('rag.finetune.Dataset')
    @patch('rag.finetune.Trainer')
    def test_finetune_model_invocation(self, mock_trainer, mock_dataset):
        mock_train = MagicMock()
        mock_train.train.return_value = "success"
        mock_trainer.return_value = mock_train

        result = finetune.train_model("mock_dataset.json")
        self.assertEqual(result, "success")

    @patch('rag.finetune.Dataset')
    def test_load_dataset(self, mock_dataset):
        mock_data = MagicMock()
        mock_data.map.return_value = ["processed"]
        mock_dataset.load_dataset.return_value = mock_data

        dataset = finetune.load_training_data("mock_dataset.json")
        self.assertEqual(dataset, ["processed"])

    def test_invalid_dataset_file(self):
        with self.assertRaises(FileNotFoundError):
            finetune.load_training_data("nonexistent_file.json")

if __name__ == '__main__':
    unittest.main()

# test\rag\training.test.py
import unittest
from unittest.mock import patch, MagicMock
from rag import training

class TestTraining(unittest.TestCase):

    @patch('rag.training.SomeLLMTrainer')
    def test_train_model(self, mock_trainer):
        mock_instance = MagicMock()
        mock_instance.run.return_value = "model_trained"
        mock_trainer.return_value = mock_instance

        result = training.train("training_corpus.txt")
        self.assertEqual(result, "model_trained")

    def test_preprocess_text_removes_stopwords(self):
        sample = "this is a test of the preprocessing"
        cleaned = training.preprocess_text(sample)
        for stopword in ['the', 'is', 'a']:
            self.assertNotIn(stopword, cleaned.split())

    def test_preprocess_text_returns_lowercase(self):
        sample = "This Is Mixed Case"
        cleaned = training.preprocess_text(sample)
        self.assertEqual(cleaned, cleaned.lower())

    def test_tokenize_handles_empty_string(self):
        tokens = training.tokenize("")
        self.assertEqual(tokens, [])

if __name__ == '__main__':
    unittest.main()

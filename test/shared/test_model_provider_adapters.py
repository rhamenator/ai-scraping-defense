import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.shared.model_adapters import GoogleGeminiAdapter, MistralAdapter


class TestGoogleGeminiAdapter(unittest.TestCase):
    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False)
    @patch("src.shared.model_adapters.genai")
    def test_predict_uses_models_api(self, mock_genai):
        client = mock_genai.Client.return_value
        client.models.generate_content.return_value = SimpleNamespace(text="classified")

        adapter = GoogleGeminiAdapter("models/gemini-test")
        result = adapter.predict("request")

        client.models.generate_content.assert_called_once_with(
            model="gemini-test", contents="request"
        )
        self.assertEqual(result, {"response": "classified"})


class TestMistralAdapter(unittest.TestCase):
    @patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}, clear=False)
    @patch("src.shared.model_adapters.Mistral")
    def test_predict_uses_v2_chat_complete_api(self, mock_mistral):
        client = mock_mistral.return_value
        response = MagicMock()
        response.choices[0].message.content = "classified"
        client.chat.complete.return_value = response
        messages = [{"role": "user", "content": "request"}]

        adapter = MistralAdapter("mistral-test")
        result = adapter.predict(messages, temperature=0.1)

        client.chat.complete.assert_called_once_with(
            model="mistral-test", messages=messages, temperature=0.1
        )
        self.assertEqual(result, {"response": "classified"})


if __name__ == "__main__":
    unittest.main()

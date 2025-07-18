# test/shared/model_adapters.test.py
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import sys
import os
import httpx

# Add the project root to the path to help static analysis tools find the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Import the actual classes from the module
from src.shared.model_adapters import (
    SklearnAdapter,
    MarkovAdapter,
    HttpModelAdapter,
)

class TestModelAdaptersComprehensive(unittest.TestCase):

    def setUp(self):
        # This setup will be used for patching joblib in the SklearnAdapter test
        self.joblib_patcher = patch('src.shared.model_adapters.joblib.load')
        self.mock_joblib_load = self.joblib_patcher.start()

    def tearDown(self):
        self.joblib_patcher.stop()

    def test_sklearn_adapter_success(self):
        """Test the SklearnAdapter with a mock model."""
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.9, 0.1]])
        self.mock_joblib_load.return_value = mock_model

        # The adapter takes a URI, which is used by joblib.load
        adapter = SklearnAdapter(model_uri="/fake/path/model.joblib")
        
        # The data should be a list of dictionaries as expected by DictVectorizer
        data = [{'feature1': 10, 'feature2': 20}]
        predictions = adapter.predict(data)
        
        self.mock_joblib_load.assert_called_once_with("/fake/path/model.joblib")
        mock_model.predict_proba.assert_called_once_with(data)
        self.assertIsInstance(predictions, np.ndarray)
        np.testing.assert_array_equal(predictions, mock_model.predict_proba.return_value)

    def test_sklearn_adapter_model_not_loaded(self):
        """Test SklearnAdapter returns a default value if the model failed to load."""
        self.mock_joblib_load.side_effect = FileNotFoundError
        
        with self.assertLogs(level='ERROR') as cm:
            adapter = SklearnAdapter(model_uri="/bad/path/model.joblib")
            self.assertIn("model file not found", cm.output[0])
        
        # Check that predict returns a default failure prediction
        predictions = adapter.predict([{'feature1': 1}])
        self.assertEqual(predictions, [[0.0]])

    def test_markov_adapter_success(self):
        """Test the MarkovAdapter successfully calls the generator function."""
        # The MarkovAdapter's model is a function, so we patch that function
        with patch('src.shared.model_adapters.generate_dynamic_tarpit_page', return_value="<p>Generated Text</p>") as mock_generate:
            # Re-import the module within the patch context if MARKOV_AVAILABLE is set at import time
            with patch('src.shared.model_adapters.MARKOV_AVAILABLE', True):
                 adapter = MarkovAdapter(model_uri="N/A") # URI is not used for this adapter
                 result = adapter.predict({}) # Data is not used
                 
                 self.assertEqual(result, "<p>Generated Text</p>")
                 mock_generate.assert_called_once()

    def test_markov_adapter_unavailable(self):
        """Test MarkovAdapter's behavior when the generator module is not available."""
        with patch('src.shared.model_adapters.MARKOV_AVAILABLE', False):
            adapter = MarkovAdapter(model_uri="N/A")
            result = adapter.predict({})
            self.assertEqual(result, "Error: Markov model not available.")

    @patch('src.shared.model_adapters.httpx.Client')
    def test_http_adapter_success(self, mock_http_client):
        """Test the HttpModelAdapter for a successful API call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"prediction": "bot", "score": 0.9}
        
        # Configure the context manager used by the adapter
        mock_client_instance = mock_http_client.return_value.__enter__.return_value
        mock_client_instance.post.return_value = mock_response

        adapter = HttpModelAdapter(model_uri="http://model-api/predict", config={"api_key": "test-key"})
        
        data = {"text": "some suspicious log"}
        result = adapter.predict(data)
        
        self.assertEqual(result, {"prediction": "bot", "score": 0.9})
        mock_client_instance.post.assert_called_once()
        # Check that the authorization header was set
        self.assertIn("Authorization", mock_client_instance.post.call_args[1]['headers'])
        self.assertEqual(mock_client_instance.post.call_args[1]['headers']['Authorization'], "Bearer test-key")

    @patch('src.shared.model_adapters.httpx.Client')
    def test_http_adapter_api_error(self, mock_http_client):
        """Test the HttpModelAdapter when the remote API returns an error status."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client_instance = mock_http_client.return_value.__enter__.return_value
        # Make the mock raise an HTTPStatusError, like httpx does
        mock_client_instance.post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        )
        
        adapter = HttpModelAdapter(model_uri="http://model-api/predict")
        
        with self.assertLogs(level='ERROR') as cm:
            result = adapter.predict({})
            self.assertIn("HTTP error 500", cm.output[0])
        
        self.assertEqual(result, {"error": "Model API returned status 500"})

if __name__ == '__main__':
    unittest.main()

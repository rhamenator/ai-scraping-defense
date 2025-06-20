# shared/model_adapters.py
from abc import ABC, abstractmethod
import joblib
import os
import logging
from typing import Any, Dict, List, Optional
import httpx
import sys

# Ensure parent directories are in the path for module resolution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# This import now correctly imports the function, not a class, from your file.
try:
    from tarpit.markov_generator import generate_dynamic_tarpit_page
    MARKOV_AVAILABLE = True
except ImportError:
    MARKOV_AVAILABLE = False
    # Create a dummy function if not available so the program doesn't crash on import
    def generate_dynamic_tarpit_page() -> str:
        return "Markov model unavailable."

class BaseModelAdapter(ABC):
    """
    Abstract Base Class for all model adapters.
    Ensures that every adapter has a 'predict' method.
    """
    def __init__(self, model_uri: str, config: Optional[Dict[str, Any]] = None):
        self.model_uri = model_uri
        # FIX: Correctly handle optional config dictionary to resolve Pylance error.
        self.config = config or {}
        self.model: Any = None
        self._load_model()

    @abstractmethod
    def _load_model(self):
        """Abstract method to load the model from the specified URI."""
        pass

    @abstractmethod
    def predict(self, data: Any, **kwargs) -> Any:
        """Abstract method to make a prediction based on the input data."""
        pass

class SklearnAdapter(BaseModelAdapter):
    """Adapter for scikit-learn models stored in .joblib files."""
    def _load_model(self):
        try:
            logging.info(f"Loading scikit-learn model from: {self.model_uri}")
            self.model = joblib.load(self.model_uri)
            logging.info("Scikit-learn model loaded successfully.")
        except FileNotFoundError:
            logging.error(f"Scikit-learn model file not found at: {self.model_uri}")
        except Exception as e:
            logging.error(f"Failed to load scikit-learn model from {self.model_uri}: {e}")

    def predict(self, data: List[Dict[str, Any]], **kwargs) -> Any:
        if self.model is None:
            logging.warning("Scikit-learn model not loaded, returning default failure prediction.")
            return [[0.0]]
        try:
            # Your pipeline's DictVectorizer expects a list of dictionaries.
            return self.model.predict_proba(data)
        except Exception as e:
            logging.error(f"Error during scikit-learn prediction: {e}", exc_info=True)
            return [[0.0]]

class MarkovAdapter(BaseModelAdapter):
    """Adapter for the PostgreSQL-based Markov chain text generator."""
    def _load_model(self):
        # FIX: No class to instantiate. The "model" is the imported function itself.
        if MARKOV_AVAILABLE:
            logging.info("MarkovGenerator functions are available.")
            self.model = generate_dynamic_tarpit_page
        else:
            logging.error("markov_generator.py not found. MarkovAdapter will not be functional.")

    def predict(self, data: Dict[str, Any], **kwargs) -> str:
        """For the Markov model, 'predict' means 'generate text'."""
        if self.model is None:
            return "Error: Markov model not available."
        
        # This adapter doesn't need input data, it just generates text.
        return self.model()

class HttpModelAdapter(BaseModelAdapter):
    """Adapter for a remote model served over an HTTP API."""
    def _load_model(self):
        logging.info(f"HTTP Model Adapter configured for endpoint: {self.model_uri}")
        if not self.model_uri:
            raise ValueError("MODEL_URI must be set for HttpModelAdapter")
        self.api_key = self.config.get("api_key")

    def predict(self, data: Any, **kwargs) -> Dict[str, Any]:
        headers = kwargs.get("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client() as client:
                response = client.post(self.model_uri, json=data, headers=headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP error {e.response.status_code} calling model API: {e.response.text}")
            return {"error": f"Model API returned status {e.response.status_code}"}
        except Exception as e:
            logging.error(f"Failed to call remote model API at {self.model_uri}: {e}")
            return {"error": "Could not connect to model API"}

# shared/model_provider.py
import os
import logging
import sys
from typing import Optional

# Ensure parent directories are in the path for module resolution
# This is no longer necessary if PYTHONPATH is set correctly in the environment
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.shared.model_adapters import SklearnAdapter, MarkovAdapter, HttpModelAdapter, BaseModelAdapter

# A mapping from the MODEL_TYPE string to the corresponding adapter class.
# This makes the provider easily extensible with new model types.
ADAPTER_MAP = {
    "sklearn": SklearnAdapter,
    "markov": MarkovAdapter,
    "http": HttpModelAdapter,
}

def load_model() -> Optional[BaseModelAdapter]:
    """
    Factory function to load the appropriate model adapter based on environment variables.

    Reads the following Environment Variables:
    - MODEL_TYPE: (Required) The type of model to load (e.g., 'sklearn', 'markov', 'http').
    - MODEL_URI:  (Required) The resource identifier for the model.
        - For 'sklearn': A file path, e.g., '/app/models/bot_detection_rf_model.joblib'
        - For 'markov': Not directly used; adapter uses PG_* env vars. A placeholder like 'postgres' is fine.
        - For 'http': The full URL of the prediction endpoint, e.g., 'https://api.example.com/predict'
    """
    model_type = os.getenv("MODEL_TYPE")
    model_uri = os.getenv("MODEL_URI")
    
    logging.info(f"Attempting to load model of type '{model_type}' from URI '{model_uri}'")

    if not model_type:
        logging.error("CRITICAL: MODEL_TYPE environment variable is not set. Cannot load model.")
        return None

    adapter_class = ADAPTER_MAP.get(model_type.lower())

    if not adapter_class:
        logging.error(f"CRITICAL: Unknown MODEL_TYPE: '{model_type}'. Available types are: {list(ADAPTER_MAP.keys())}")
        return None
    
    if not model_uri:
        logging.error(f"CRITICAL: MODEL_URI environment variable is not set for type '{model_type}'. Cannot load model.")
        return None

    try:
        # Instantiate and return the chosen adapter
        return adapter_class(model_uri)
    except Exception as e:
        logging.error(f"CRITICAL: Failed to instantiate model adapter for type '{model_type}': {e}", exc_info=True)
        return None
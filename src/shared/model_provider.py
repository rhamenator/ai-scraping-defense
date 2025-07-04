# src/shared/model_provider.py
import os
import logging
import sys
from typing import Optional

# Ensure parent directories are in the path for module resolution
from src.shared.model_adapters import (
    SklearnAdapter, MarkovAdapter, HttpModelAdapter, BaseModelAdapter,
    OpenAIAdapter, AnthropicAdapter, GoogleGeminiAdapter, CohereAdapter,
    OllamaAdapter, LlamaCppAdapter, MistralAdapter
)

# A mapping from the MODEL_TYPE string to the corresponding adapter class.
# This makes the provider easily extensible with new model types.
ADAPTER_MAP = {
    "sklearn": SklearnAdapter,
    "markov": MarkovAdapter,
    "http": HttpModelAdapter,
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GoogleGeminiAdapter,
    "cohere": CohereAdapter,
    "mistral": MistralAdapter,  # <-- Added Mistral
    "ollama": OllamaAdapter,
    "llamacpp": LlamaCppAdapter,
}

def load_model() -> Optional[BaseModelAdapter]:
    """
    Factory function to load the appropriate model adapter based on environment variables.

    Reads the following Environment Variables:
    - MODEL_TYPE: (Required) The type of model to load (e.g., 'sklearn', 'mistral', 'ollama').
    - MODEL_URI:  (Required) The resource identifier for the model.
    - Other env vars for API keys (e.g., MISTRAL_API_KEY) are read by the adapter itself.
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
        # Configuration for the adapter can be passed here if needed,
        # but for API keys, it's often handled by the adapter reading env vars.
        # Example: config = {"api_key": os.getenv("MISTRAL_API_KEY")}
        # return adapter_class(model_uri, config)
        
        # For simplicity, we'll let the adapter handle its own config.
        return adapter_class(model_uri)
    except Exception as e:
        logging.error(f"CRITICAL: Failed to instantiate model adapter for type '{model_type}': {e}", exc_info=True)
        return None

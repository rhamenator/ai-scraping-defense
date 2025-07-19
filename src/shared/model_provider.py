# src/shared/model_provider.py
"""Factory for obtaining model adapters based on a URI."""
import os
import logging
from typing import Optional

# Import all adapter classes from the model_adapters module
from src.shared.model_adapters import (
    BaseModelAdapter, SklearnAdapter, MarkovAdapter, HttpModelAdapter,
    OpenAIAdapter, AnthropicAdapter, GoogleGeminiAdapter, CohereAdapter,
    MistralAdapter, OllamaAdapter, LlamaCppAdapter,
    LocalLLMApiAdapter, ExternalAPIAdapter
)

# The ADAPTER_MAP now maps the URI scheme (e.g., "openai") to the adapter class.
ADAPTER_MAP = {
    "sklearn": SklearnAdapter,
    "markov": MarkovAdapter,
    "http": HttpModelAdapter,
    "https": HttpModelAdapter, # Alias for http
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "google-gemini": GoogleGeminiAdapter,
    "cohere": CohereAdapter,
    "mistral": MistralAdapter,
    "ollama": OllamaAdapter,
    "llamacpp": LlamaCppAdapter,
    "local-llm": LocalLLMApiAdapter,
    "external-api": ExternalAPIAdapter,
}

def get_model_adapter(model_uri: Optional[str] = None, config: Optional[dict] = None) -> Optional[BaseModelAdapter]:
    """
    Factory function to get the appropriate model adapter based on the MODEL_URI.
    The URI scheme determines which adapter is loaded.
    Example URIs:
    - sklearn:///app/models/bot_detection_rf_model.joblib
    - openai://gpt-4-turbo
    - mistral://mistral-large-latest
    - ollama://llama3
    - http://my-custom-api.com/predict
    """
    if model_uri is None:
        model_uri = os.getenv("MODEL_URI")
    if not model_uri:
        logging.error("CRITICAL: MODEL_URI environment variable is not set. Cannot load model.")
        return None

    try:
        # Split the URI into 'scheme' and 'path' parts. e.g., "openai" and "gpt-4-turbo"
        scheme, path = model_uri.split("://", 1)
        scheme = scheme.lower()
    except ValueError:
        # Handle cases where the URI format is incorrect.
        logging.error(f"Invalid MODEL_URI format: '{model_uri}'. Must be in 'scheme://path' format.")
        return None

    # Look up the appropriate adapter class from the map.
    adapter_class = ADAPTER_MAP.get(scheme)
    if not adapter_class:
        logging.error(f"CRITICAL: Unknown model URI scheme: '{scheme}'. Available schemes are: {list(ADAPTER_MAP.keys())}")
        return None

    logging.info(f"Loading model adapter '{adapter_class.__name__}' for model path '{path}'")
    try:
        # Instantiate the chosen adapter, passing the path part of the URI as the model identifier.
        # For sklearn, this path will be absolute inside the container, e.g., /app/models/model.joblib
        # The '///' in the URI (e.g., sklearn:///) is important for correctly parsing file paths.
        model_path = path
        if scheme == "sklearn" and path.startswith('/'):
            model_path = path
        elif scheme == "sklearn":
             # This case is for relative paths, but absolute is recommended in containers.
            model_path = os.path.join("/app", path)

        if config is not None:
            return adapter_class(model_path, config)
        return adapter_class(model_path)
    except Exception as e:
        logging.error(f"Failed to instantiate model adapter for scheme '{scheme}': {e}", exc_info=True)
        return None

# shared/model_adapters.py
from abc import ABC, abstractmethod
import os
import logging
from typing import Any, Dict, List, Optional
import httpx
import sys

# --- Refactored Imports ---
# No longer need sys.path manipulation if PYTHONPATH is set correctly

# Import third-party libraries safely
try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False

# Local module import
try:
    from src.tarpit.markov_generator import generate_dynamic_tarpit_page
    MARKOV_AVAILABLE = True
except ImportError:
    MARKOV_AVAILABLE = False
    def generate_dynamic_tarpit_page() -> str:
        return "Markov model unavailable."

# --- Base Class ---
class BaseModelAdapter(ABC):
    """Abstract Base Class for all model adapters."""
    def __init__(self, model_uri: str, config: Optional[Dict[str, Any]] = None):
        self.model_uri = model_uri
        self.config = config or {}
        self.model: Any = None
        self._load_model()

    @abstractmethod
    def _load_model(self):
        """Abstract method to load/initialize the model or client."""
        pass

    @abstractmethod
    def predict(self, data: Any, **kwargs) -> Any:
        """Abstract method to make a prediction based on the input data."""
        pass

# --- Existing Adapters ---
class SklearnAdapter(BaseModelAdapter):
    """Adapter for scikit-learn models stored in .joblib files."""
    def _load_model(self):
        if not JOBLIB_AVAILABLE:
            logging.error("joblib library not installed. Cannot load scikit-learn model.")
            return
        try:
            self.model = joblib.load(self.model_uri)
            logging.info("Scikit-learn model loaded successfully.")
        except Exception as e:
            logging.error(f"Failed to load scikit-learn model from {self.model_uri}: {e}")

    def predict(self, data: List[Dict[str, Any]], **kwargs) -> Any:
        if self.model is None:
            return [[0.0]] 
        return self.model.predict_proba(data)

class MarkovAdapter(BaseModelAdapter):
    """Adapter for the PostgreSQL-based Markov chain text generator."""
    def _load_model(self):
        if MARKOV_AVAILABLE:
            self.model = generate_dynamic_tarpit_page
        else:
            logging.error("markov_generator not available.")

    def predict(self, data: Dict[str, Any], **kwargs) -> str:
        if self.model is None:
            return "Error: Markov model not available."
        return self.model()

class HttpModelAdapter(BaseModelAdapter):
    """Adapter for a generic remote model served over an HTTP API."""
    def _load_model(self):
        if not self.model_uri:
            raise ValueError("MODEL_URI must be set for HttpModelAdapter")
        self.api_key = self.config.get("api_key")

    def predict(self, data: Any, **kwargs) -> Dict[str, Any]:
        headers = kwargs.get("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client() as client:
                response = client.post(self.model_uri, json=data, headers=headers, timeout=20.0)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logging.error(f"Failed to call remote model API at {self.model_uri}: {e}")
            return {"error": "Could not connect to model API"}

# --- LLM VENDOR ADAPTERS ---

class OpenAIAdapter(BaseModelAdapter):
    """Adapter for OpenAI's GPT models."""
    def _load_model(self):
        if not OPENAI_AVAILABLE:
            logging.error("openai library not installed. OpenAIAdapter is not available.")
            return
        api_key = self.config.get("api_key")
        if not api_key:
            logging.error("api_key not found in config for OpenAIAdapter.")
            return
        self.model = openai.OpenAI(api_key=api_key)
        logging.info("OpenAI client configured successfully.")

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "OpenAI client not initialized"}
        try:
            completion = self.model.chat.completions.create(
                model=self.model_uri,  # e.g., "gpt-4-turbo"
                messages=data,
                **kwargs
            )
            response_content = completion.choices[0].message.content
            return {"response": response_content}
        except Exception as e:
            logging.error(f"Error during OpenAI prediction: {e}")
            return {"error": str(e)}

class AnthropicAdapter(BaseModelAdapter):
    """Adapter for Anthropic's Claude models."""
    def _load_model(self):
        if not ANTHROPIC_AVAILABLE:
            logging.error("anthropic library not installed. AnthropicAdapter is not available.")
            return
        api_key = self.config.get("api_key")
        if not api_key:
            logging.error("api_key not found in config for AnthropicAdapter.")
            return
        self.model = anthropic.Anthropic(api_key=api_key)
        logging.info("Anthropic client configured successfully.")

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Anthropic client not initialized"}
        try:
            system_prompt = kwargs.pop("system", "You are a helpful assistant.")
            message = self.model.messages.create(
                model=self.model_uri,  # e.g., "claude-3-opus-20240229"
                system=system_prompt,
                messages=data,
                max_tokens=kwargs.get("max_tokens", 1024)
            )
            response_content = message.content[0].text
            return {"response": response_content}
        except Exception as e:
            logging.error(f"Error during Anthropic prediction: {e}")
            return {"error": str(e)}

class GoogleGeminiAdapter(BaseModelAdapter):
    """Adapter for Google's Gemini models."""
    def _load_model(self):
        if not GEMINI_AVAILABLE:
            logging.error("google-generativeai library not installed. GoogleGeminiAdapter is not available.")
            return
        api_key = self.config.get("api_key")
        if not api_key:
            logging.error("api_key not found in config for GoogleGeminiAdapter.")
            return
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.model_uri) # e.g., "gemini-1.5-flash"
        logging.info("Google Gemini client configured successfully.")

    def predict(self, data: str, **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Google Gemini client not initialized"}
        try:
            response = self.model.generate_content(data)
            return {"response": response.text}
        except Exception as e:
            logging.error(f"Error during Google Gemini prediction: {e}")
            return {"error": str(e)}

class CohereAdapter(BaseModelAdapter):
    """Adapter for Cohere's models."""
    def _load_model(self):
        if not COHERE_AVAILABLE:
            logging.error("cohere library not installed. CohereAdapter is not available.")
            return
        api_key = self.config.get("api_key")
        if not api_key:
            logging.error("api_key not found in config for CohereAdapter.")
            return
        self.model = cohere.Client(api_key=api_key)
        logging.info("Cohere client configured successfully.")

    def predict(self, data: str, **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Cohere client not initialized"}
        try:
            response = self.model.chat(
                model=self.model_uri, # e.g., "command-r-plus"
                message=data,
                **kwargs
            )
            return {"response": response.text}
        except Exception as e:
            logging.error(f"Error during Cohere prediction: {e}")
            return {"error": str(e)}

# --- LOCAL & OPEN-SOURCE MODEL ADAPTERS ---

class OllamaAdapter(BaseModelAdapter):
    """Adapter for local models served via Ollama."""
    def _load_model(self):
        if not OLLAMA_AVAILABLE:
            logging.error("ollama library not installed. OllamaAdapter is not available.")
            return
        host = self.config.get("host") 
        try:
            self.model = ollama.Client(host=host)
            self.model.list()
            logging.info(f"Ollama client configured successfully for host: {host or 'default'}")
        except Exception as e:
            logging.error(f"Failed to connect to Ollama host: {host or 'default'}. Error: {e}")
            self.model = None

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Ollama client not initialized or failed to connect"}
        try:
            response = self.model.chat(
                model=self.model_uri, # e.g., "llama3:latest"
                messages=data,
                stream=False
            )
            response_content = response['message']['content']
            return {"response": response_content}
        except Exception as e:
            logging.error(f"Error during Ollama prediction: {e}")
            return {"error": str(e)}
            
class LlamaCppAdapter(BaseModelAdapter):
    """Adapter for local models running via llama-cpp-python."""
    def _load_model(self):
        if not LLAMA_CPP_AVAILABLE:
            logging.error("llama-cpp-python library not installed. LlamaCppAdapter is not available.")
            return
        try:
            # model_uri is the path to the .gguf file
            # Config can contain n_gpu_layers, n_ctx, etc.
            self.model = Llama(model_path=self.model_uri, **self.config)
            logging.info(f"llama-cpp-python model loaded successfully from {self.model_uri}")
        except Exception as e:
            logging.error(f"Failed to load llama-cpp-python model from {self.model_uri}: {e}")
            self.model = None

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "llama-cpp-python model not loaded"}
        try:
            response = self.model.create_chat_completion(
                messages=data,
                **kwargs
            )
            response_content = response['choices'][0]['message']['content']
            return {"response": response_content}
        except Exception as e:
            logging.error(f"Error during llama-cpp-python prediction: {e}")
            return {"error": str(e)}
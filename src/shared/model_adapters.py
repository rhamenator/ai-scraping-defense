# src/shared/model_adapters.py
from abc import ABC, abstractmethod
import os
import logging
from typing import Any, Dict, List, Optional
import httpx

# This pattern ensures that even if an import fails, the module variable
# is still defined (as None), which resolves Pylance's "possibly unbound" errors.
try:
    import joblib
except ImportError:
    joblib = None

try:
    import openai
except ImportError:
    openai = None

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import cohere
except ImportError:
    cohere = None

try:
    from mistralai.client import MistralClient
    from mistralai.models.chat_completion import ChatMessage
except ImportError:
    MistralClient = None
    ChatMessage = None

try:
    import ollama
except ImportError:
    ollama = None

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

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

class SklearnAdapter(BaseModelAdapter):
    def _load_model(self):
        if not joblib:
            logging.error("joblib library not installed. Cannot load scikit-learn model.")
            return
        try:
            self.model = joblib.load(self.model_uri)
            logging.info("Scikit-learn model loaded successfully.")
        except Exception as e:
            logging.error(f"Failed to load scikit-learn model from {self.model_uri}: {e}")

    def predict(self, data: List[Dict[str, Any]], **kwargs) -> Any:
        if self.model is None: return [[0.0]]
        return self.model.predict_proba(data)

class MarkovAdapter(BaseModelAdapter):
    def _load_model(self):
        self.model = generate_dynamic_tarpit_page if MARKOV_AVAILABLE else None

    def predict(self, data: Dict[str, Any], **kwargs) -> str:
        if self.model is None: return "Error: Markov model not available."
        return self.model()

class HttpModelAdapter(BaseModelAdapter):
    def _load_model(self):
        if not self.model_uri:
            raise ValueError("MODEL_URI must be set for HttpModelAdapter")
        self.api_key = os.getenv("EXTERNAL_API_KEY")

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
    def _load_model(self):
        if not openai:
            logging.error("openai library not installed. OpenAIAdapter is not available.")
            return
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logging.error("OPENAI_API_KEY environment variable not found.")
            return
        if not self.model_uri:
            logging.error("MODEL_URI must be set for OpenAIAdapter")
            return
        # Configure the OpenAI client
        try:
            self.model = openai.OpenAI(api_key=api_key)
            logging.info("OpenAI client configured successfully.")
        except Exception as e:
            logging.error(f"Failed to configure OpenAI client: {e}")
            self.model = None
            return

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model: return {"error": "OpenAI client not initialized"}
        try:
            completion = self.model.chat.completions.create(model=self.model_uri, messages=data, **kwargs)
            return {"response": completion.choices[0].message.content}
        except Exception as e:
            logging.error(f"Error during OpenAI prediction: {e}"); return {"error": str(e)}

class AnthropicAdapter(BaseModelAdapter):
    def _load_model(self):
        if not anthropic:
            logging.error("anthropic library not installed. AnthropicAdapter is not available.")
            return
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logging.error("ANTHROPIC_API_KEY environment variable not found.")
            return
        if not self.model_uri:
            logging.error("MODEL_URI must be set for AnthropicAdapter")
            return
        try:                
            self.model = anthropic.Anthropic(api_key=api_key)
            logging.info("Anthropic client configured successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Anthropic client: {e}")
            self.model = None
            return

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model: return {"error": "Anthropic client not initialized"}
        try:
            system_prompt = kwargs.pop("system", "You are a helpful assistant.")
            message = self.model.messages.create(model=self.model_uri, system=system_prompt, messages=data, max_tokens=kwargs.get("max_tokens", 1024))
            return {"response": message.content[0].text}
        except Exception as e:
            logging.error(f"Error during Anthropic prediction: {e}"); return {"error": str(e)}

class GoogleGeminiAdapter(BaseModelAdapter):
    def _load_model(self):
        if not genai:
            logging.error("google-generativeai library not installed. GoogleGeminiAdapter is not available.")
            return
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logging.error("GOOGLE_API_KEY environment variable not found.")
            return
        if not self.model_uri:
            logging.error("MODEL_URI must be set for GoogleGeminiAdapter")
            return
        # Configure the Google Gemini client
        try:
            genai.configure(api_key=api_key)    # type: ignore
            self.model = genai.GenerativeModel(self.model_uri)  # type: ignore
            logging.info("Google Gemini client configured successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Google Gemini client: {e}")
            self.model = None
            return

    def predict(self, data: str, **kwargs) -> Dict[str, Any]:
        if not self.model: return {"error": "Google Gemini client not initialized"}
        try:
            response = self.model.generate_content(data)
            return {"response": response.text}
        except Exception as e:
            logging.error(f"Error during Google Gemini prediction: {e}"); return {"error": str(e)}

class CohereAdapter(BaseModelAdapter):
    def _load_model(self):
        if not cohere:
            logging.error("cohere library not installed. CohereAdapter is not available.")
            return
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            logging.error("COHERE_API_KEY environment variable not found.")
            return
        if not self.model_uri:
            logging.error("MODEL_URI must be set for CohereAdapter")
            return
        # Configure the Cohere client
        try:
            self.model = cohere.Client(api_key=api_key)
            logging.info("Cohere client configured successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Cohere client: {e}")
            self.model = None

    def predict(self, data: str, **kwargs) -> Dict[str, Any]:
        if not self.model: return {"error": "Cohere client not initialized"}
        try:
            response = self.model.chat(model=self.model_uri, message=data, **kwargs)
            return {"response": response.text}
        except Exception as e:
            logging.error(f"Error during Cohere prediction: {e}"); return {"error": str(e)}

class MistralAdapter(BaseModelAdapter):
    def _load_model(self):
        if not MistralClient:
            logging.error("mistralai library not installed. MistralAdapter is not available.")
            return
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            logging.error("MISTRAL_API_KEY environment variable not found.")
            return
        if not self.model_uri:
            logging.error("MODEL_URI must be set for MistralAdapter")
            return
        # Configure the Mistral client
        if not ChatMessage:
            logging.error("ChatMessage class not available. MistralAdapter requires mistralai.client.")
            return
        if not self.model_uri.startswith("mistral://"):
            logging.error("MODEL_URI must start with 'mistral://' for MistralAdapter")
            return
        self.model_uri = self.model_uri.replace("mistral://", "")
        # Initialize the Mistral client with the API key
        try:
            self.model = MistralClient(api_key=api_key)
            logging.info("Mistral AI client configured successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Mistral AI client: {e}")
            self.model = None

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model or not ChatMessage: return {"error": "Mistral AI client not initialized"}
        try:
            messages = [ChatMessage(role=msg['role'], content=msg['content']) for msg in data]
            chat_response = self.model.chat(model=self.model_uri, messages=messages, **kwargs)
            return {"response": chat_response.choices[0].message.content}
        except Exception as e:
            logging.error(f"Error during Mistral AI prediction: {e}"); return {"error": str(e)}

# --- LOCAL & OPEN-SOURCE MODEL ADAPTERS ---
class OllamaAdapter(BaseModelAdapter):
    def _load_model(self):
        if not ollama:
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
            response = self.model.chat(model=self.model_uri, messages=data, stream=False)
            return {"response": response['message']['content']}
        except Exception as e:
            logging.error(f"Error during Ollama prediction: {e}"); return {"error": str(e)}

class LlamaCppAdapter(BaseModelAdapter):
    def _load_model(self):
        if not Llama:
            logging.error("llama-cpp-python library not installed. LlamaCppAdapter is not available.")
            return
        try:
            self.model = Llama(model_path=self.model_uri, **self.config)
            logging.info(f"llama-cpp-python model loaded successfully from {self.model_uri}")
        except Exception as e:
            logging.error(f"Failed to load llama-cpp-python model from {self.model_uri}: {e}")
            self.model = None

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "llama-cpp-python model not loaded"}
        try:
            response = self.model.create_chat_completion(messages=data, **kwargs)
            return {"response": response['choices'][0]['message']['content']}
        except Exception as e:
            logging.error(f"Error during llama-cpp-python prediction: {e}"); return {"error": str(e)}

# --- Factory Function ---
def get_model_adapter(model_uri: str, config: Optional[Dict[str, Any]] = None) -> BaseModelAdapter:
    """Factory function to get the appropriate model adapter based on the model URI."""
    if model_uri.startswith("http"):
        return HttpModelAdapter(model_uri, config)
    elif model_uri.startswith("sklearn://"):
        return SklearnAdapter(model_uri.replace("sklearn://", ""), config)
    elif model_uri.startswith("markov://"):
        return MarkovAdapter(model_uri.replace("markov://", ""), config)
    elif model_uri.startswith("openai://"):
        return OpenAIAdapter(model_uri.replace("openai://", ""), config)
    elif model_uri.startswith("anthropic://"):
        return AnthropicAdapter(model_uri.replace("anthropic://", ""), config)
    elif model_uri.startswith("google-gemini://"):
        return GoogleGeminiAdapter(model_uri.replace("google-gemini://", ""), config)
    elif model_uri.startswith("cohere://"):
        return CohereAdapter(model_uri.replace("cohere://", ""), config)
    elif model_uri.startswith("mistral://"):
        return MistralAdapter(model_uri.replace("mistral://", ""), config)
    elif model_uri.startswith("ollama://"):
        return OllamaAdapter(model_uri.replace("ollama://", ""), config)
    elif model_uri.startswith("llama-cpp://"):
        return LlamaCppAdapter(model_uri.replace("llama-cpp://", ""), config)
    else:
        raise ValueError(f"Unknown model URI scheme: {model_uri}")
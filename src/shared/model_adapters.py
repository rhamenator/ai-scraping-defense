"""Adapter interfaces for various model providers."""

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


def _is_trusted_model_path(path: str) -> bool:
    """Return True if path is within the trusted model directory."""
    trusted_dir = Path(
        os.environ.get("TRUSTED_MODEL_DIR", os.path.join(os.getcwd(), "models"))
    ).resolve()
    abs_path = Path(path).resolve()
    try:
        return trusted_dir in abs_path.parents or abs_path == trusted_dir
    except Exception:
        return False


# This pattern ensures that even if an import fails, the module variable
# is still defined (as None)
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

# UPDATED: Import the new recommended 'google.genai' library
try:
    from google import genai
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
    from tarpit_rs import generate_dynamic_tarpit_page

    MARKOV_AVAILABLE = True
except ImportError:
    MARKOV_AVAILABLE = False

    def generate_dynamic_tarpit_page(rng=None) -> str:  # type: ignore[override]
        return "Markov model unavailable."


# --- Base Class ---
class BaseModelAdapter(ABC):
    def __init__(self, model_uri: str, config: Optional[Dict[str, Any]] = None):
        self.model_uri = model_uri
        self.config = config or {}
        self.model: Any = None
        self._load_model()

    @abstractmethod
    def _load_model(self):
        pass

    @abstractmethod
    def predict(self, data: Any, **kwargs) -> Any:
        pass


# --- Adapter Implementations ---
class SklearnAdapter(BaseModelAdapter):
    def _load_model(self):
        if not joblib:
            logging.error(
                "joblib library not installed. Cannot load scikit-learn model."
            )
            return
        if not _is_trusted_model_path(self.model_uri):
            logging.error("model path %s is outside trusted directory", self.model_uri)
            return
        try:
            # model_uri is the file path, e.g., /app/models/model.joblib
            self.model = joblib.load(self.model_uri)
            logging.info(f"Scikit-learn model loaded from {self.model_uri}")
        except FileNotFoundError:
            logging.error("model file not found")
        except Exception as e:
            logging.error(f"Failed to load scikit-learn model: {e}")

    def predict(self, data: List[Dict[str, Any]], **kwargs) -> Any:
        if self.model is None:
            return [[0.0]]
        return self.model.predict_proba(data)


class MarkovAdapter(BaseModelAdapter):
    def _load_model(self):
        self.model = generate_dynamic_tarpit_page if MARKOV_AVAILABLE else None

    def predict(self, data: Dict[str, Any], **kwargs) -> str:
        if self.model is None:
            return "Error: Markov model not available."
        return self.model()


class HttpModelAdapter(BaseModelAdapter):
    def _load_model(self):
        # For this adapter, the model_uri is the full URL.
        if not self.model_uri:
            raise ValueError("MODEL_URI must be set for HttpModelAdapter")
        self.api_key = self.config.get("api_key") or os.getenv("EXTERNAL_API_KEY")

    def predict(self, data: Any, **kwargs) -> Dict[str, Any]:
        headers = kwargs.get("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client() as client:
                # The full URL is stored in model_uri for this adapter
                response = client.post(
                    self.model_uri, json=data, headers=headers, timeout=20.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logging.error(f"HTTP error {status} calling remote model API")
            return {"error": f"Model API returned status {status}"}
        except Exception as e:
            logging.error(f"Failed to call remote model API at {self.model_uri}: {e}")
            return {"error": "Could not connect to model API"}


class OpenAIAdapter(BaseModelAdapter):
    def _load_model(self):
        if not openai:
            logging.error("openai library not installed.")
            return
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logging.error("OPENAI_API_KEY not set.")
            return
        self.model = openai.OpenAI(api_key=api_key)
        logging.info("OpenAI client configured.")

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "OpenAI client not initialized"}
        try:
            # model_uri is the model name, e.g., "gpt-4-turbo"
            completion = self.model.chat.completions.create(
                model=self.model_uri, messages=data, **kwargs
            )
            return {"response": completion.choices[0].message.content}
        except Exception as e:
            logging.error(f"Error during OpenAI prediction: {e}")
            return {"error": str(e)}


class AnthropicAdapter(BaseModelAdapter):
    def _load_model(self):
        if not anthropic:
            logging.error("anthropic library not installed.")
            return
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logging.error("ANTHROPIC_API_KEY not set.")
            return
        self.model = anthropic.Anthropic(api_key=api_key)
        logging.info("Anthropic client configured.")

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Anthropic client not initialized"}
        try:
            system_prompt = kwargs.pop("system", "You are a helpful assistant.")
            # model_uri is the model name, e.g., "claude-3-opus-20240229"
            message = self.model.messages.create(
                model=self.model_uri,
                system=system_prompt,
                messages=data,
                max_tokens=kwargs.get("max_tokens", 1024),
            )
            return {"response": message.content[0].text}
        except Exception as e:
            logging.error(f"Error during Anthropic prediction: {e}")
            return {"error": str(e)}


class GoogleGeminiAdapter(BaseModelAdapter):
    def _load_model(self):
        # UPDATED: Check for the new genai library
        if not genai:
            logging.error(
                "'google-genai' library not installed. GoogleGeminiAdapter is not available."
            )
            return

        # The new SDK can use GOOGLE_API_KEY or GEMINI_API_KEY
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            logging.error(
                "GOOGLE_API_KEY or GEMINI_API_KEY environment variable not found."
            )
            return

        # UPDATED: The new SDK uses a central Client object.
        try:
            self.model = genai.Client(api_key=api_key)
            logging.info("Google GenAI client configured successfully.")
        except Exception as e:
            logging.error(f"Failed to configure Google GenAI client: {e}")
            self.model = None

    def predict(self, data: str, **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Google GenAI client not initialized"}
        try:
            # UPDATED: The new SDK uses a different method signature.
            # The model name is passed directly to the method.
            response = self.model.generate_content(
                model=f"models/{self.model_uri}",  # The new SDK often requires the "models/" prefix
                contents=data,
            )
            return {"response": response.text}
        except Exception as e:
            logging.error(f"Error during Google GenAI prediction: {e}")
            return {"error": str(e)}


class CohereAdapter(BaseModelAdapter):
    def _load_model(self):
        if not cohere:
            logging.error("cohere library not installed.")
            return
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            logging.error("COHERE_API_KEY not set.")
            return
        self.model = cohere.Client(api_key=api_key)
        logging.info("Cohere client configured.")

    def predict(self, data: str, **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Cohere client not initialized"}
        try:
            # model_uri is the model name, e.g., "command-r-plus"
            response = self.model.chat(model=self.model_uri, message=data, **kwargs)
            return {"response": response.text}
        except Exception as e:
            logging.error(f"Error during Cohere prediction: {e}")
            return {"error": str(e)}


class MistralAdapter(BaseModelAdapter):
    def _load_model(self):
        if not MistralClient:
            logging.error("mistralai library not installed.")
            return
        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            logging.error("MISTRAL_API_KEY not set.")
            return
        self.model = MistralClient(api_key=api_key)
        logging.info("Mistral AI client configured.")

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model or not ChatMessage:
            return {"error": "Mistral AI client not initialized"}
        try:
            messages = [
                ChatMessage(role=msg["role"], content=msg["content"]) for msg in data
            ]
            # model_uri is the model name, e.g., "mistral-large-latest"
            chat_response = self.model.chat(
                model=self.model_uri, messages=messages, **kwargs
            )
            return {"response": chat_response.choices[0].message.content}
        except Exception as e:
            logging.error(f"Error during Mistral AI prediction: {e}")
            return {"error": str(e)}


class OllamaAdapter(BaseModelAdapter):
    def _load_model(self):
        if not ollama:
            logging.error("ollama library not installed.")
            return
        # For Ollama, the URI path is the model name, and the host comes from config.
        host = self.config.get("host")  # e.g., http://localhost:11434
        try:
            self.model = ollama.Client(host=host)
            self.model.list()
            logging.info(f"Ollama client configured for host: {host or 'default'}")
        except Exception as e:
            logging.error(f"Failed to connect to Ollama host: {e}")
            self.model = None

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "Ollama client not initialized"}
        try:
            # model_uri is the model name, e.g., "llama3"
            response = self.model.chat(
                model=self.model_uri, messages=data, stream=False
            )
            return {"response": response["message"]["content"]}
        except Exception as e:
            logging.error(f"Error during Ollama prediction: {e}")
            return {"error": str(e)}


class LlamaCppAdapter(BaseModelAdapter):
    def _load_model(self):
        if not Llama:
            logging.error("llama-cpp-python library not installed.")
            return
        try:
            # model_uri is the file path to the .gguf model
            self.model = Llama(model_path=self.model_uri, **self.config)
            logging.info(f"llama-cpp-python model loaded from {self.model_uri}")
        except Exception as e:
            logging.error(f"Failed to load llama-cpp-python model: {e}")
            self.model = None

    def predict(self, data: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        if not self.model:
            return {"error": "llama-cpp-python model not loaded"}
        try:
            response = self.model.create_chat_completion(messages=data, **kwargs)
            return {"response": response["choices"][0]["message"]["content"]}
        except Exception as e:
            logging.error(f"Error during llama-cpp-python prediction: {e}")
            return {"error": str(e)}


class LocalLLMApiAdapter(BaseModelAdapter):
    """Adapter for a locally hosted OpenAI-compatible API."""

    def _load_model(self):
        self.timeout = self.config.get("timeout", 30.0)
        self.model_name = self.config.get("model")
        self.api_url = self.model_uri

    def predict(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        try:
            prompt_json = json.dumps(data, ensure_ascii=False)
        except Exception:
            prompt_json = json.dumps({"ip": data.get("ip")})
        prompt = (
            "Analyze the following request JSON and classify as MALICIOUS_BOT, BENIGN_CRAWLER, or HUMAN: "
            f"{prompt_json}"
        )
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": False,
        }
        try:
            with httpx.Client() as client:
                resp = client.post(self.api_url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                result = resp.json()
                content = (
                    result.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                return {"classification": content}
        except Exception as e:
            logging.error(f"Local LLM API request failed: {e}")
            return {"error": str(e)}


class ExternalAPIAdapter(BaseModelAdapter):
    """Adapter for the external classification API."""

    def _load_model(self):
        self.timeout = self.config.get("timeout", 15.0)
        self.api_key = self.config.get("api_key")
        self.api_url = self.model_uri

    def predict(self, data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client() as client:
                resp = client.post(
                    self.api_url, json=data, headers=headers, timeout=self.timeout
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logging.error(f"External API request failed: {e}")
            return {"error": str(e)}

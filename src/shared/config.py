import os
from typing import Dict, Any

# In shared/config.py
import os

def get_secret(file_variable_name: str) -> str | None:
    """Reads a secret from the file path specified in an environment variable."""
    file_path = os.environ.get(file_variable_name)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return f.read().strip()
        except IOError as e:
            print(f"Warning: Could not read secret file at {file_path}: {e}")
    return None

# Update how REDIS_PASSWORD is defined to use this new function
REDIS_PASSWORD = get_secret("REDIS_PASSWORD_FILE")

# Service Ports
AI_SERVICE_PORT = int(os.getenv("AI_SERVICE_PORT", 8000))
ESCALATION_ENGINE_PORT = int(os.getenv("ESCALATION_ENGINE_PORT", 8003))
TARPIT_API_PORT = int(os.getenv("TARPIT_API_PORT", 8005))
ADMIN_UI_PORT = int(os.getenv("ADMIN_UI_PORT", 5002))

# Service URLs
AI_SERVICE_URL = f"http://ai_service:{AI_SERVICE_PORT}"
ESCALATION_ENGINE_URL = f"http://escalation_engine:{ESCALATION_ENGINE_PORT}"
TARPIT_API_URL = f"http://tarpit_api:{TARPIT_API_PORT}"
ADMIN_UI_URL = f"http://admin_ui:{ADMIN_UI_PORT}"

# Mock API URLs
EXTERNAL_API_URL = os.getenv("EXTERNAL_API_URL", "http://mock_external_api:8000")
IP_REPUTATION_API_URL = os.getenv("IP_REPUTATION_API_URL", "http://mock_ip_reputation_api:8000")
COMMUNITY_BLOCKLIST_API_URL = os.getenv("COMMUNITY_BLOCKLIST_API_URL", "http://mock_community_blocklist_api:8000")

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@db:5432/ai_defense_db")

# AI Model Configuration
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "gpt-3.5-turbo")
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", 1500))
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", 0.7))

# Application Settings
APP_ENV = os.getenv("APP_ENV", "production")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

def get_config() -> Dict[str, Any]:
    """Returns all configuration as a dictionary"""
    return {k: v for k, v in globals().items() 
            if not k.startswith('_') and k.isupper()}
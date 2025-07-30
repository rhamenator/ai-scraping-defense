"""Central configuration dataclass and helpers for environment settings."""

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


def get_secret(file_variable_name: str) -> Optional[str]:
    """Read a secret from the file path specified in an environment variable."""
    file_path = os.environ.get(file_variable_name)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return f.read().strip()
        except IOError as exc:
            print(f"Warning: Could not read secret file at {file_path}: {exc}")
    return None


@dataclass(frozen=True)
class Config:
    """Configuration loaded from environment variables once on import."""

    # Internal service hosts
    AI_SERVICE_HOST: str = field(
        default_factory=lambda: os.getenv("AI_SERVICE_HOST", "ai_service")
    )
    ESCALATION_ENGINE_HOST: str = field(
        default_factory=lambda: os.getenv("ESCALATION_ENGINE_HOST", "escalation_engine")
    )
    TARPIT_API_HOST: str = field(
        default_factory=lambda: os.getenv("TARPIT_API_HOST", "tarpit_api")
    )
    ADMIN_UI_HOST: str = field(
        default_factory=lambda: os.getenv("ADMIN_UI_HOST", "admin_ui")
    )
    CLOUD_DASHBOARD_HOST: str = field(
        default_factory=lambda: os.getenv("CLOUD_DASHBOARD_HOST", "cloud_dashboard")
    )
    CONFIG_RECOMMENDER_HOST: str = field(
        default_factory=lambda: os.getenv(
            "CONFIG_RECOMMENDER_HOST", "config_recommender"
        )
    )
    PROMPT_ROUTER_HOST: str = field(
        default_factory=lambda: os.getenv("PROMPT_ROUTER_HOST", "prompt_router")
    )

    # Service ports
    AI_SERVICE_PORT: int = field(
        default_factory=lambda: int(os.getenv("AI_SERVICE_PORT", 8000))
    )
    ESCALATION_ENGINE_PORT: int = field(
        default_factory=lambda: int(os.getenv("ESCALATION_ENGINE_PORT", 8003))
    )
    TARPIT_API_PORT: int = field(
        default_factory=lambda: int(os.getenv("TARPIT_API_PORT", 8001))
    )
    ADMIN_UI_PORT: int = field(
        default_factory=lambda: int(os.getenv("ADMIN_UI_PORT", 5002))
    )
    CLOUD_DASHBOARD_PORT: int = field(
        default_factory=lambda: int(os.getenv("CLOUD_DASHBOARD_PORT", 5006))
    )
    CONFIG_RECOMMENDER_PORT: int = field(
        default_factory=lambda: int(os.getenv("CONFIG_RECOMMENDER_PORT", 8010))
    )
    PROMPT_ROUTER_PORT: int = field(
        default_factory=lambda: int(os.getenv("PROMPT_ROUTER_PORT", 8009))
    )

    # Redis
    REDIS_HOST: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "redis"))
    REDIS_PORT: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", 6379)))
    REDIS_DB_BLOCKLIST: int = field(
        default_factory=lambda: int(os.getenv("REDIS_DB_BLOCKLIST", 2))
    )
    REDIS_DB_TAR_PIT_HOPS: int = field(
        default_factory=lambda: int(os.getenv("REDIS_DB_TAR_PIT_HOPS", 4))
    )
    REDIS_DB_FREQUENCY: int = field(
        default_factory=lambda: int(os.getenv("REDIS_DB_FREQUENCY", 3))
    )
    REDIS_DB_FINGERPRINTS: int = field(
        default_factory=lambda: int(os.getenv("REDIS_DB_FINGERPRINTS", 5))
    )
    REDIS_PASSWORD: Optional[str] = field(
        default_factory=lambda: get_secret("REDIS_PASSWORD_FILE")
    )

    # General application settings
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    APP_ENV: str = field(default_factory=lambda: os.getenv("APP_ENV", "production"))
    DEBUG: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    # Multi-tenant identifier used to namespace keys
    TENANT_ID: str = field(default_factory=lambda: os.getenv("TENANT_ID", "default"))

    # Tarpit configuration
    ESCALATION_ENDPOINT: str = field(
        default_factory=lambda: os.getenv(
            "ESCALATION_ENDPOINT", "http://escalation_engine:8003/escalate"
        )
    )
    TAR_PIT_MIN_DELAY_SEC: float = field(
        default_factory=lambda: float(os.getenv("TAR_PIT_MIN_DELAY_SEC", 0.6))
    )
    TAR_PIT_MAX_DELAY_SEC: float = field(
        default_factory=lambda: float(os.getenv("TAR_PIT_MAX_DELAY_SEC", 1.2))
    )
    SYSTEM_SEED: str = field(
        default_factory=lambda: os.getenv(
            "SYSTEM_SEED", "default_system_seed_value_change_me"
        )
    )
    TAR_PIT_MAX_HOPS: int = field(
        default_factory=lambda: int(os.getenv("TAR_PIT_MAX_HOPS", 250))
    )
    TAR_PIT_HOP_WINDOW_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("TAR_PIT_HOP_WINDOW_SECONDS", 86400))
    )
    BLOCKLIST_TTL_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("BLOCKLIST_TTL_SECONDS", 86400))
    )
    ENABLE_TARPIT_CATCH_ALL: bool = field(
        default_factory=lambda: os.getenv("ENABLE_TARPIT_CATCH_ALL", "true").lower()
        == "true"
    )

    # AI webhook configuration
    ALERT_METHOD: str = field(
        default_factory=lambda: os.getenv("ALERT_METHOD", "none").lower()
    )
    ALERT_GENERIC_WEBHOOK_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("ALERT_GENERIC_WEBHOOK_URL")
    )
    ALERT_SLACK_WEBHOOK_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("ALERT_SLACK_WEBHOOK_URL")
    )
    ALERT_SMTP_HOST: str = field(
        default_factory=lambda: os.getenv("ALERT_SMTP_HOST", "mailhog")
    )
    ALERT_SMTP_PORT: int = field(
        default_factory=lambda: int(os.getenv("ALERT_SMTP_PORT", 587))
    )
    ALERT_SMTP_USER: Optional[str] = field(
        default_factory=lambda: os.getenv("ALERT_SMTP_USER")
    )
    ALERT_SMTP_PASSWORD_FILE: str = field(
        default_factory=lambda: os.getenv(
            "ALERT_SMTP_PASSWORD_FILE", "/run/secrets/smtp_password"
        )
    )
    ALERT_SMTP_PASSWORD: Optional[str] = field(
        default_factory=lambda: get_secret("ALERT_SMTP_PASSWORD_FILE")
    )
    ALERT_SMTP_USE_TLS: bool = field(
        default_factory=lambda: os.getenv("ALERT_SMTP_USE_TLS", "true").lower()
        == "true"
    )
    ALERT_EMAIL_FROM: Optional[str] = field(
        default_factory=lambda: os.getenv(
            "ALERT_EMAIL_FROM", os.getenv("ALERT_SMTP_USER")
        )
    )
    ALERT_EMAIL_TO: Optional[str] = field(
        default_factory=lambda: os.getenv("ALERT_EMAIL_TO")
    )
    ALERT_MIN_REASON_SEVERITY: str = field(
        default_factory=lambda: os.getenv("ALERT_MIN_REASON_SEVERITY", "Local LLM")
    )
    ENABLE_COMMUNITY_REPORTING: bool = field(
        default_factory=lambda: os.getenv("ENABLE_COMMUNITY_REPORTING", "true").lower()
        == "true"
    )
    COMMUNITY_BLOCKLIST_REPORT_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("COMMUNITY_BLOCKLIST_REPORT_URL")
    )
    COMMUNITY_BLOCKLIST_API_KEY_FILE: str = field(
        default_factory=lambda: os.getenv(
            "COMMUNITY_BLOCKLIST_API_KEY_FILE",
            "/run/secrets/community_blocklist_api_key",
        )
    )
    COMMUNITY_BLOCKLIST_API_KEY: Optional[str] = field(
        default_factory=lambda: get_secret("COMMUNITY_BLOCKLIST_API_KEY_FILE")
    )
    COMMUNITY_BLOCKLIST_REPORT_TIMEOUT: float = field(
        default_factory=lambda: float(
            os.getenv("COMMUNITY_BLOCKLIST_REPORT_TIMEOUT", 10.0)
        )
    )
    WEBHOOK_API_KEY: Optional[str] = field(
        default_factory=lambda: os.getenv("WEBHOOK_API_KEY")
    )

    # Escalation engine configuration
    ESCALATION_THRESHOLD: float = field(
        default_factory=lambda: float(os.getenv("ESCALATION_THRESHOLD", 0.8))
    )
    ESCALATION_API_KEY: Optional[str] = field(
        default_factory=lambda: os.getenv("ESCALATION_API_KEY")
    )
    ESCALATION_WEBHOOK_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("ESCALATION_WEBHOOK_URL")
    )
    LOCAL_LLM_API_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("LOCAL_LLM_API_URL")
    )
    LOCAL_LLM_MODEL: Optional[str] = field(
        default_factory=lambda: os.getenv("LOCAL_LLM_MODEL")
    )
    LOCAL_LLM_TIMEOUT: float = field(
        default_factory=lambda: float(os.getenv("LOCAL_LLM_TIMEOUT", 45.0))
    )
    EXTERNAL_API_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("EXTERNAL_CLASSIFICATION_API_URL")
        or os.getenv("EXTERNAL_API_URL")
    )
    EXTERNAL_API_KEY: Optional[str] = field(
        default_factory=lambda: get_secret("EXTERNAL_CLASSIFICATION_API_KEY_FILE")
    )
    EXTERNAL_API_TIMEOUT: float = field(
        default_factory=lambda: float(os.getenv("EXTERNAL_API_TIMEOUT", 15.0))
    )
    ENABLE_LOCAL_LLM_CLASSIFICATION: bool = field(
        default_factory=lambda: os.getenv(
            "ENABLE_LOCAL_LLM_CLASSIFICATION", "true"
        ).lower()
        == "true"
    )
    ENABLE_EXTERNAL_API_CLASSIFICATION: bool = field(
        default_factory=lambda: os.getenv(
            "ENABLE_EXTERNAL_API_CLASSIFICATION", "true"
        ).lower()
        == "true"
    )
    ENABLE_IP_REPUTATION: bool = field(
        default_factory=lambda: os.getenv("ENABLE_IP_REPUTATION", "false").lower()
        == "true"
    )
    IP_REPUTATION_API_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("IP_REPUTATION_API_URL")
    )
    IP_REPUTATION_API_KEY: Optional[str] = field(
        default_factory=lambda: get_secret("IP_REPUTATION_API_KEY_FILE")
    )
    IP_REPUTATION_TIMEOUT: float = field(
        default_factory=lambda: float(os.getenv("IP_REPUTATION_TIMEOUT", 10.0))
    )
    IP_REPUTATION_MALICIOUS_SCORE_BONUS: float = field(
        default_factory=lambda: float(
            os.getenv("IP_REPUTATION_MALICIOUS_SCORE_BONUS", 0.3)
        )
    )
    IP_REPUTATION_MIN_MALICIOUS_THRESHOLD: float = field(
        default_factory=lambda: float(
            os.getenv("IP_REPUTATION_MIN_MALICIOUS_THRESHOLD", 50)
        )
    )
    ENABLE_CAPTCHA_TRIGGER: bool = field(
        default_factory=lambda: os.getenv("ENABLE_CAPTCHA_TRIGGER", "false").lower()
        == "true"
    )
    CAPTCHA_SCORE_THRESHOLD_LOW: float = field(
        default_factory=lambda: float(os.getenv("CAPTCHA_SCORE_THRESHOLD_LOW", 0.2))
    )
    CAPTCHA_SCORE_THRESHOLD_HIGH: float = field(
        default_factory=lambda: float(os.getenv("CAPTCHA_SCORE_THRESHOLD_HIGH", 0.5))
    )
    CAPTCHA_VERIFICATION_URL: Optional[str] = field(
        default_factory=lambda: os.getenv("CAPTCHA_VERIFICATION_URL")
    )
    CAPTCHA_SECRET: Optional[str] = field(
        default_factory=lambda: get_secret("CAPTCHA_SECRET_FILE")
        or os.getenv("CAPTCHA_SECRET")
    )
    CAPTCHA_SUCCESS_LOG: str = field(
        default_factory=lambda: os.getenv(
            "CAPTCHA_SUCCESS_LOG", "/app/logs/captcha_success.log"
        )
    )
    TRAINING_ROBOTS_TXT_PATH: str = field(
        default_factory=lambda: os.getenv(
            "TRAINING_ROBOTS_TXT_PATH", "/app/config/robots.txt"
        )
    )
    FREQUENCY_WINDOW_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("FREQUENCY_WINDOW_SECONDS", 300))
    )
    FINGERPRINT_WINDOW_SECONDS: int = field(
        default_factory=lambda: int(os.getenv("FINGERPRINT_WINDOW_SECONDS", 604800))
    )
    FINGERPRINT_REUSE_THRESHOLD: int = field(
        default_factory=lambda: int(os.getenv("FINGERPRINT_REUSE_THRESHOLD", 3))
    )
    KNOWN_BAD_UAS: str = field(
        default_factory=lambda: os.getenv(
            "KNOWN_BAD_UAS",
            (
                "python-requests,curl,wget,scrapy,java/,ahrefsbot,semrushbot,"
                "mj12bot,dotbot,petalbot,bytespider,gptbot,ccbot,claude-web,"
                "google-extended,dataprovider,purebot,scan,masscan,zgrab,nmap"
            ),
        )
    )
    KNOWN_BENIGN_CRAWLERS_UAS: str = field(
        default_factory=lambda: os.getenv(
            "KNOWN_BENIGN_CRAWLERS_UAS",
            "googlebot,bingbot,slurp,duckduckbot,baiduspider,yandexbot,googlebot-image",
        )
    )

    MODEL_TYPE: Optional[str] = field(default_factory=lambda: os.getenv("MODEL_TYPE"))

    # Tarpit LLM generator configuration
    ENABLE_TARPIT_LLM_GENERATOR: bool = field(
        default_factory=lambda: os.getenv(
            "ENABLE_TARPIT_LLM_GENERATOR", "false"
        ).lower()
        == "true"
    )
    TARPIT_LLM_MODEL_URI: Optional[str] = field(
        default_factory=lambda: os.getenv("TARPIT_LLM_MODEL_URI")
    )
    TARPIT_LLM_MAX_TOKENS: int = field(
        default_factory=lambda: int(os.getenv("TARPIT_LLM_MAX_TOKENS", 400))
    )

    ENABLE_AI_LABYRINTH: bool = field(
        default_factory=lambda: os.getenv("ENABLE_AI_LABYRINTH", "false").lower()
        == "true"
    )
    TARPIT_LABYRINTH_DEPTH: int = field(
        default_factory=lambda: int(os.getenv("TARPIT_LABYRINTH_DEPTH", 5))
    )
    ENABLE_FINGERPRINTING: bool = field(
        default_factory=lambda: os.getenv("ENABLE_FINGERPRINTING", "false").lower()
        == "true"
    )

    # Anomaly Detection
    ANOMALY_MODEL_PATH: Optional[str] = field(
        default_factory=lambda: os.getenv("ANOMALY_MODEL_PATH")
    )

    MODEL_VERSION: Optional[str] = field(
        default_factory=lambda: os.getenv("MODEL_VERSION")
    )
    ANOMALY_THRESHOLD: float = field(
        default_factory=lambda: float(os.getenv("ANOMALY_THRESHOLD", 0.7))
    )

    # Derived attribute: namespace prefix for Redis keys and similar resources
    TENANT_PREFIX: str = field(init=False)

    def as_dict(self) -> Dict[str, Any]:
        """Return configuration values as a dictionary."""
        cfg = asdict(self)
        cfg.update(
            {
                "AI_SERVICE_URL": self.AI_SERVICE_URL,
                "ESCALATION_ENGINE_URL": self.ESCALATION_ENGINE_URL,
                "TARPIT_API_URL": self.TARPIT_API_URL,
                "ADMIN_UI_URL": self.ADMIN_UI_URL,
                "CLOUD_DASHBOARD_URL": self.CLOUD_DASHBOARD_URL,
                "CONFIG_RECOMMENDER_URL": self.CONFIG_RECOMMENDER_URL,
            }
        )
        return cfg

    def __post_init__(self):
        object.__setattr__(
            self,
            "AI_SERVICE_URL",
            f"http://{self.AI_SERVICE_HOST}:{self.AI_SERVICE_PORT}",
        )
        object.__setattr__(
            self,
            "ESCALATION_ENGINE_URL",
            f"http://{self.ESCALATION_ENGINE_HOST}:{self.ESCALATION_ENGINE_PORT}",
        )
        object.__setattr__(
            self,
            "TARPIT_API_URL",
            f"http://{self.TARPIT_API_HOST}:{self.TARPIT_API_PORT}",
        )
        object.__setattr__(
            self, "ADMIN_UI_URL", f"http://{self.ADMIN_UI_HOST}:{self.ADMIN_UI_PORT}"
        )
        object.__setattr__(
            self,
            "CLOUD_DASHBOARD_URL",
            f"http://{self.CLOUD_DASHBOARD_HOST}:{self.CLOUD_DASHBOARD_PORT}",
        )
        object.__setattr__(
            self,
            "CONFIG_RECOMMENDER_URL",
            f"http://{self.CONFIG_RECOMMENDER_HOST}:{self.CONFIG_RECOMMENDER_PORT}",
        )
        object.__setattr__(
            self,
            "PROMPT_ROUTER_URL",
            f"http://{self.PROMPT_ROUTER_HOST}:{self.PROMPT_ROUTER_PORT}",
        )
        object.__setattr__(self, "TENANT_PREFIX", f"{self.TENANT_ID}:")


# Instantiate configuration once
CONFIG = Config()
_CONFIG_CACHE: Dict[str, Config] = {CONFIG.TENANT_ID: CONFIG}

# Populate module level constants for backward compatibility
for _k, _v in CONFIG.as_dict().items():
    globals()[_k] = _v


def get_config(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Return configuration as a dictionary for the given tenant."""
    if tenant_id is None or tenant_id == CONFIG.TENANT_ID:
        return CONFIG.as_dict()

    cfg = _CONFIG_CACHE.get(tenant_id)
    if cfg is None:
        cfg = Config(TENANT_ID=tenant_id)
        _CONFIG_CACHE[tenant_id] = cfg
    return cfg.as_dict()


def tenant_key(base: str, tenant_id: Optional[str] = None) -> str:
    """Prefix a key with the specified tenant ID or the default one."""
    if tenant_id is None:
        return f"{CONFIG.TENANT_PREFIX}{base}"
    return f"{tenant_id}:{base}"

"""Configuration schema with Pydantic for type safety and validation."""

import os
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MASKED_VALUE = "***MASKED***"


class Environment(str, Enum):
    """Deployment environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Logging level options."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ModelProvider(str, Enum):
    """Supported ML model providers."""

    SKLEARN = "sklearn"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    COHERE = "cohere"
    MISTRAL = "mistral"
    OLLAMA = "ollama"
    MCP = "mcp"


class AlertMethod(str, Enum):
    """Alert delivery methods."""

    NONE = "none"
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class PortConfig(BaseModel):
    """Port configuration with validation."""

    value: int = Field(ge=1, le=65535, description="Port number between 1 and 65535")

    @classmethod
    def from_env(cls, key: str, default: int) -> "PortConfig":
        """Load port from environment variable."""
        return cls(value=int(os.getenv(key, default)))


class ServiceEndpoint(BaseModel):
    """Service endpoint configuration."""

    host: str = Field(min_length=1, description="Service hostname or IP")
    port: int = Field(ge=1, le=65535, description="Service port")
    scheme: str = Field(default="http", description="Service URL scheme")

    @property
    def url(self) -> str:
        """Get full service URL."""
        return f"{self.scheme}://{self.host}:{self.port}"

    @field_validator("scheme")
    @classmethod
    def validate_scheme(cls, value: str) -> str:
        scheme = value.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("scheme must be http or https")
        return scheme


class RedisConfig(BaseModel):
    """Redis connection configuration."""

    host: str = Field(default="redis", description="Redis hostname")
    port: int = Field(default=6379, ge=1, le=65535)
    password: Optional[str] = Field(default=None, repr=False)
    db_blocklist: int = Field(default=2, ge=0, le=15)
    db_tar_pit_hops: int = Field(default=4, ge=0, le=15)
    db_frequency: int = Field(default=3, ge=0, le=15)
    db_fingerprints: int = Field(default=5, ge=0, le=15)

    def __repr__(self) -> str:
        """Custom repr to mask password."""
        data = self.model_dump()
        if data.get("password"):
            data["password"] = MASKED_VALUE
        return f"RedisConfig({data})"


class PostgresConfig(BaseModel):
    """PostgreSQL connection configuration."""

    host: str = Field(default="postgres", description="PostgreSQL hostname")
    port: int = Field(default=5432, ge=1, le=65535)
    dbname: str = Field(default="markov_db", min_length=1)
    user: str = Field(default="postgres", min_length=1)
    password: Optional[str] = Field(default=None, repr=False)

    def __repr__(self) -> str:
        """Custom repr to mask password."""
        data = self.model_dump()
        if data.get("password"):
            data["password"] = MASKED_VALUE
        return f"PostgresConfig({data})"


class TarpitConfig(BaseModel):
    """Tarpit service configuration."""

    min_delay_sec: float = Field(default=0.6, ge=0.0, le=10.0)
    max_delay_sec: float = Field(default=1.2, ge=0.0, le=10.0)
    max_stream_seconds: float = Field(default=60.0, ge=1.0, le=3600.0)
    max_hops: int = Field(default=250, ge=1, le=10000)
    hop_window_seconds: int = Field(default=86400, ge=60)
    enable_catch_all: bool = Field(default=True)
    enable_llm_generator: bool = Field(default=False)
    llm_model_uri: Optional[str] = None
    llm_max_tokens: int = Field(default=400, ge=50, le=4000)

    @model_validator(mode="after")
    def validate_delays(self) -> "TarpitConfig":
        """Validate min_delay <= max_delay."""
        if self.min_delay_sec > self.max_delay_sec:
            raise ValueError(
                f"min_delay_sec ({self.min_delay_sec}) must be <= "
                f"max_delay_sec ({self.max_delay_sec})"
            )
        return self


class EscalationConfig(BaseModel):
    """Escalation engine configuration."""

    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    api_key: Optional[str] = Field(default=None, repr=False)
    webhook_url: Optional[str] = None
    webhook_allowed_domains: List[str] = Field(default_factory=list)

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate webhook URL format."""
        if v:
            scheme = urlparse(v).scheme
            if scheme not in {"http", "https"}:
                raise ValueError("webhook_url must start with http or https")
        return v


class CaptchaConfig(BaseModel):
    """CAPTCHA configuration."""

    enable_trigger: bool = Field(default=False)
    score_threshold_low: float = Field(default=0.2, ge=0.0, le=1.0)
    score_threshold_high: float = Field(default=0.5, ge=0.0, le=1.0)
    verification_url: Optional[str] = None
    secret: Optional[str] = Field(default=None, repr=False)
    token_expiry_seconds: int = Field(default=300, ge=60, le=3600)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "CaptchaConfig":
        """Validate low threshold <= high threshold."""
        if self.score_threshold_low > self.score_threshold_high:
            raise ValueError(
                f"score_threshold_low ({self.score_threshold_low}) must be <= "
                f"score_threshold_high ({self.score_threshold_high})"
            )
        return self


class SecurityConfig(BaseModel):
    """Security-related configuration."""

    enable_https: bool = Field(default=False)
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None
    enable_waf: bool = Field(default=True)
    waf_rules_path: Optional[str] = None
    jwt_secret: Optional[str] = Field(default=None, repr=False)
    jwt_secret_file: Optional[str] = None
    jwt_public_key: Optional[str] = Field(default=None, repr=False)
    jwt_public_key_file: Optional[str] = None
    jwt_issuer: Optional[str] = None
    jwt_audience: Optional[str] = None
    admin_ui_username: Optional[str] = None
    admin_ui_password_hash: Optional[str] = Field(default=None, repr=False)
    admin_ui_2fa_secret: Optional[str] = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_https_config(self) -> "SecurityConfig":
        """Validate HTTPS configuration when enabled."""
        if self.enable_https:
            if not self.tls_cert_path or not self.tls_key_path:
                raise ValueError(
                    "tls_cert_path and tls_key_path required when enable_https=True"
                )
        return self


class ConfigMetadata(BaseModel):
    """Configuration metadata for versioning and tracking."""

    version: str = Field(default="1.0.0", description="Configuration version")
    environment: Environment = Field(
        default=Environment.PRODUCTION, description="Deployment environment"
    )
    last_modified: Optional[str] = Field(
        default=None, description="ISO timestamp of last modification"
    )
    last_validated: Optional[str] = Field(
        default=None, description="ISO timestamp of last validation"
    )
    checksum: Optional[str] = Field(
        default=None, description="Configuration checksum for drift detection"
    )


class AppConfig(BaseModel):
    """Complete application configuration schema."""

    # Metadata
    metadata: ConfigMetadata = Field(default_factory=ConfigMetadata)

    # General settings
    log_level: LogLevel = Field(default=LogLevel.INFO)
    debug: bool = Field(default=False)
    tenant_id: str = Field(default="default", min_length=1)
    app_env: Environment = Field(default=Environment.PRODUCTION)

    # Model configuration
    model_uri: str = Field(min_length=1, description="Primary model URI")
    model_type: Optional[str] = None
    model_version: Optional[str] = None

    # Service endpoints
    ai_service: ServiceEndpoint = Field(
        default_factory=lambda: ServiceEndpoint(host="ai_service", port=8000)
    )
    escalation_engine: ServiceEndpoint = Field(
        default_factory=lambda: ServiceEndpoint(host="escalation_engine", port=8003)
    )
    tarpit_api: ServiceEndpoint = Field(
        default_factory=lambda: ServiceEndpoint(host="tarpit_api", port=8001)
    )
    admin_ui: ServiceEndpoint = Field(
        default_factory=lambda: ServiceEndpoint(host="admin_ui", port=5002)
    )

    # Database configurations
    redis: RedisConfig = Field(default_factory=RedisConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)

    # Feature configurations
    tarpit: TarpitConfig = Field(default_factory=TarpitConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    captcha: CaptchaConfig = Field(default_factory=CaptchaConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    # Alert configuration
    alert_method: AlertMethod = Field(default=AlertMethod.NONE)

    # Feature flags (reference to external features.yaml)
    enable_plugins: bool = Field(default=True)
    enable_fingerprinting: bool = Field(default=False)
    enable_ai_labyrinth: bool = Field(default=False)
    enable_ip_reputation: bool = Field(default=False)

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        return self.model_dump(mode="python", exclude_none=True)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables."""
        # This is a factory method that will be implemented
        # to map environment variables to the schema
        raise NotImplementedError("Use ConfigLoader.load_from_env() instead")

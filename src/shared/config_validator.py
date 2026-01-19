"""Configuration validation and loading framework."""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import ValidationError

from .config_schema import (
    AlertMethod,
    AppConfig,
    CaptchaConfig,
    ConfigMetadata,
    Environment,
    EscalationConfig,
    LogLevel,
    PostgresConfig,
    RedisConfig,
    SecurityConfig,
    ServiceEndpoint,
    TarpitConfig,
)

logger = logging.getLogger(__name__)
BCRYPT_PATTERN = re.compile(r"^\$(2[aby])\$(\d\d)\$[./A-Za-z0-9]{53}$")
JWT_ALGORITHMS_ALLOWED = {
    "HS256",
    "HS384",
    "HS512",
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES384",
    "ES512",
    "EdDSA",
}


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


class ConfigLoader:
    """Load and validate configuration from various sources."""

    def __init__(self, strict: bool = True):
        """
        Initialize config loader.

        Args:
            strict: If True, raise errors on validation failure.
                   If False, log warnings and use defaults.
        """
        self.strict = strict
        self.validation_errors: List[str] = []

    def load_from_env(self, env: Optional[Dict[str, str]] = None) -> AppConfig:
        """
        Load configuration from environment variables.

        Args:
            env: Optional dictionary of environment variables.
                If None, uses os.environ.

        Returns:
            Validated AppConfig instance.

        Raises:
            ConfigValidationError: If validation fails in strict mode.
        """
        env = env or dict(os.environ)
        self.validation_errors = []

        try:
            # Load metadata
            metadata = self._load_metadata(env)

            # Load service endpoints
            ai_service = ServiceEndpoint(
                host=env.get("AI_SERVICE_HOST", "ai_service"),
                port=int(env.get("AI_SERVICE_PORT", 8000)),
            )
            escalation_engine = ServiceEndpoint(
                host=env.get("ESCALATION_ENGINE_HOST", "escalation_engine"),
                port=int(env.get("ESCALATION_ENGINE_PORT", 8003)),
            )
            tarpit_api = ServiceEndpoint(
                host=env.get("TARPIT_API_HOST", "tarpit_api"),
                port=int(env.get("TARPIT_API_PORT", 8001)),
            )
            admin_ui = ServiceEndpoint(
                host=env.get("ADMIN_UI_HOST", "admin_ui"),
                port=int(env.get("ADMIN_UI_PORT", 5002)),
            )

            # Load database configs
            redis_config = self._load_redis_config(env)
            postgres_config = self._load_postgres_config(env)

            # Load feature configs
            tarpit_config = self._load_tarpit_config(env)
            escalation_config = self._load_escalation_config(env)
            captcha_config = self._load_captcha_config(env)
            security_config = self._load_security_config(env)

            # Build the complete config
            config = AppConfig(
                metadata=metadata,
                log_level=LogLevel(env.get("LOG_LEVEL", "INFO").upper()),
                debug=env.get("DEBUG", "false").lower() == "true",
                tenant_id=env.get("TENANT_ID", "default"),
                app_env=Environment(env.get("APP_ENV", "production").lower()),
                model_uri=env.get(
                    "MODEL_URI", "sklearn:///app/models/bot_detection_rf_model.joblib"
                ),
                model_type=env.get("MODEL_TYPE"),
                model_version=env.get("MODEL_VERSION"),
                ai_service=ai_service,
                escalation_engine=escalation_engine,
                tarpit_api=tarpit_api,
                admin_ui=admin_ui,
                redis=redis_config,
                postgres=postgres_config,
                tarpit=tarpit_config,
                escalation=escalation_config,
                captcha=captcha_config,
                security=security_config,
                alert_method=AlertMethod(env.get("ALERT_METHOD", "none").lower()),
                enable_plugins=env.get("ENABLE_PLUGINS", "true").lower() == "true",
                enable_fingerprinting=env.get("ENABLE_FINGERPRINTING", "false").lower()
                == "true",
                enable_ai_labyrinth=env.get("ENABLE_AI_LABYRINTH", "false").lower()
                == "true",
                enable_ip_reputation=env.get("ENABLE_IP_REPUTATION", "false").lower()
                == "true",
            )

            logger.info(
                "Configuration loaded successfully for environment: %s",
                config.app_env,
            )
            return config

        except ValidationError as e:
            error_msg = f"Configuration validation failed: {e}"
            if self.strict:
                raise ConfigValidationError(error_msg) from e
            else:
                logger.warning(error_msg)
                # Return a minimal valid config
                return self._get_minimal_config()

        except Exception as e:
            error_msg = f"Failed to load configuration: {e}"
            if self.strict:
                raise ConfigValidationError(error_msg) from e
            else:
                logger.error(error_msg)
                return self._get_minimal_config()

    def _load_metadata(self, env: Dict[str, str]) -> ConfigMetadata:
        """Load configuration metadata."""
        return ConfigMetadata(
            version=env.get("CONFIG_VERSION", "1.0.0"),
            environment=Environment(env.get("APP_ENV", "production").lower()),
            last_validated=datetime.now(timezone.utc).isoformat(),
        )

    def _load_redis_config(self, env: Dict[str, str]) -> RedisConfig:
        """Load Redis configuration."""
        # Load password without masking in validator (masking happens in schema)
        redis_pass = self._load_secret(env.get("REDIS_PASSWORD_FILE"))
        return RedisConfig(
            host=env.get("REDIS_HOST", "redis"),
            port=int(env.get("REDIS_PORT", 6379)),
            password=redis_pass if redis_pass else None,
            db_blocklist=int(env.get("REDIS_DB_BLOCKLIST", 2)),
            db_tar_pit_hops=int(env.get("REDIS_DB_TAR_PIT_HOPS", 4)),
            db_frequency=int(env.get("REDIS_DB_FREQUENCY", 3)),
            db_fingerprints=int(env.get("REDIS_DB_FINGERPRINTS", 5)),
        )

    def _load_postgres_config(self, env: Dict[str, str]) -> PostgresConfig:
        """Load PostgreSQL configuration."""
        pg_pass = self._load_secret(env.get("PG_PASSWORD_FILE"))
        return PostgresConfig(
            host=env.get("PG_HOST", "postgres"),
            port=int(env.get("PG_PORT", 5432)),
            dbname=env.get("PG_DBNAME", "markov_db"),
            user=env.get("PG_USER", "postgres"),
            password=pg_pass if pg_pass else None,
        )

    def _load_tarpit_config(self, env: Dict[str, str]) -> TarpitConfig:
        """Load tarpit configuration."""
        return TarpitConfig(
            min_delay_sec=float(env.get("TAR_PIT_MIN_DELAY_SEC", 0.6)),
            max_delay_sec=float(env.get("TAR_PIT_MAX_DELAY_SEC", 1.2)),
            max_hops=int(env.get("TAR_PIT_MAX_HOPS", 250)),
            hop_window_seconds=int(env.get("TAR_PIT_HOP_WINDOW_SECONDS", 86400)),
            enable_catch_all=env.get("ENABLE_TARPIT_CATCH_ALL", "true").lower()
            == "true",
            enable_llm_generator=env.get("ENABLE_TARPIT_LLM_GENERATOR", "false").lower()
            == "true",
            llm_model_uri=env.get("TARPIT_LLM_MODEL_URI"),
            llm_max_tokens=int(env.get("TARPIT_LLM_MAX_TOKENS", 400)),
        )

    def _load_escalation_config(self, env: Dict[str, str]) -> EscalationConfig:
        """Load escalation engine configuration."""
        allowed_domains = [
            d.strip()
            for d in env.get("ESCALATION_WEBHOOK_ALLOWED_DOMAINS", "").split(",")
            if d.strip()
        ]
        return EscalationConfig(
            threshold=float(env.get("ESCALATION_THRESHOLD", 0.8)),
            api_key=env.get("ESCALATION_API_KEY"),
            webhook_url=env.get("ESCALATION_WEBHOOK_URL"),
            webhook_allowed_domains=allowed_domains,
        )

    def _load_captcha_config(self, env: Dict[str, str]) -> CaptchaConfig:
        """Load CAPTCHA configuration."""
        return CaptchaConfig(
            enable_trigger=env.get("ENABLE_CAPTCHA_TRIGGER", "false").lower() == "true",
            score_threshold_low=float(env.get("CAPTCHA_SCORE_THRESHOLD_LOW", 0.2)),
            score_threshold_high=float(env.get("CAPTCHA_SCORE_THRESHOLD_HIGH", 0.5)),
            verification_url=env.get("CAPTCHA_VERIFICATION_URL"),
            secret=self._load_secret(env.get("CAPTCHA_SECRET_FILE"))
            or env.get("CAPTCHA_SECRET"),
            token_expiry_seconds=int(env.get("CAPTCHA_TOKEN_EXPIRY_SECONDS", 300)),
        )

    def _load_security_config(self, env: Dict[str, str]) -> SecurityConfig:
        """Load security configuration."""
        return SecurityConfig(
            enable_https=env.get("ENABLE_HTTPS", "false").lower() == "true",
            tls_cert_path=env.get("TLS_CERT_PATH"),
            tls_key_path=env.get("TLS_KEY_PATH"),
            enable_waf=env.get("ENABLE_WAF", "true").lower() == "true",
            waf_rules_path=env.get("WAF_RULES_PATH"),
            jwt_secret=env.get("AUTH_JWT_SECRET"),
            jwt_issuer=env.get("AUTH_JWT_ISSUER"),
            jwt_audience=env.get("AUTH_JWT_AUDIENCE"),
            admin_ui_username=env.get("ADMIN_UI_USERNAME"),
            admin_ui_password_hash=env.get("ADMIN_UI_PASSWORD_HASH"),
            admin_ui_2fa_secret=env.get("ADMIN_UI_2FA_SECRET"),
        )

    def _load_secret(self, secret_path: Optional[str]) -> Optional[str]:
        """
        Load secret from file path.

        Args:
            secret_path: Path to secret file.

        Returns:
            Secret content or None if file doesn't exist.
        """
        if not secret_path:
            return None

        try:
            path = Path(secret_path)
            if path.exists():
                return path.read_text().strip()
            else:
                logger.debug("Secret file not found: %s", secret_path)
                return None
        except Exception as e:
            logger.warning("Failed to read secret from %s: %s", secret_path, e)
            return None

    def _get_minimal_config(self) -> AppConfig:
        """Return minimal valid configuration as fallback."""
        return AppConfig(
            model_uri="sklearn:///app/models/bot_detection_rf_model.joblib",
            log_level=LogLevel.INFO,
        )

    def validate_config(self, config: AppConfig) -> Tuple[bool, List[str]]:
        """
        Validate a configuration instance.

        Args:
            config: Configuration to validate.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors: List[str] = []

        # Validate model provider has necessary API keys
        model_uri = config.model_uri
        provider_keys = {
            "openai://": "OPENAI_API_KEY",
            "mistral://": "MISTRAL_API_KEY",
            "anthropic://": "ANTHROPIC_API_KEY",
            "google://": "GOOGLE_API_KEY",
            "cohere://": "COHERE_API_KEY",
        }

        for prefix, key in provider_keys.items():
            if model_uri.startswith(prefix) and not os.getenv(key):
                errors.append(f"{key} required for MODEL_URI {model_uri}")

        # Validate production environment requirements
        if config.app_env == Environment.PRODUCTION:
            if config.debug:
                errors.append("DEBUG mode should not be enabled in production")

            if not config.security.admin_ui_password_hash:
                errors.append(
                    "ADMIN_UI_PASSWORD_HASH must be set in production environment"
                )

            if config.security.enable_https and (
                not config.security.tls_cert_path or not config.security.tls_key_path
            ):
                errors.append("TLS certificate and key required when HTTPS is enabled")
        if config.security.admin_ui_password_hash:
            match = BCRYPT_PATTERN.match(config.security.admin_ui_password_hash)
            if not match:
                errors.append("ADMIN_UI_PASSWORD_HASH must be a bcrypt hash")
            else:
                cost = int(match.group(2))
                if cost < 12:
                    errors.append("ADMIN_UI_PASSWORD_HASH bcrypt cost must be >= 12")

        if config.security.jwt_secret and len(config.security.jwt_secret) < 32:
            errors.append("AUTH_JWT_SECRET must be at least 32 characters")

        # Validate tarpit configuration
        if config.tarpit.enable_llm_generator and not config.tarpit.llm_model_uri:
            errors.append(
                "TARPIT_LLM_MODEL_URI required when ENABLE_TARPIT_LLM_GENERATOR=true"
            )

        # Validate CAPTCHA configuration
        if config.captcha.enable_trigger:
            if not config.captcha.verification_url:
                errors.append(
                    "CAPTCHA_VERIFICATION_URL required when ENABLE_CAPTCHA_TRIGGER=true"
                )
            if not config.captcha.secret:
                errors.append(
                    "CAPTCHA_SECRET required when ENABLE_CAPTCHA_TRIGGER=true"
                )

        # Validate alert configuration
        if config.alert_method == AlertMethod.EMAIL:
            if not os.getenv("ALERT_EMAIL_TO"):
                errors.append("ALERT_EMAIL_TO required when ALERT_METHOD=email")

        if config.alert_method == AlertMethod.SLACK:
            if not os.getenv("ALERT_SLACK_WEBHOOK_URL"):
                errors.append(
                    "ALERT_SLACK_WEBHOOK_URL required when ALERT_METHOD=slack"
                )

        if config.alert_method == AlertMethod.WEBHOOK:
            if not os.getenv("ALERT_GENERIC_WEBHOOK_URL"):
                errors.append(
                    "ALERT_GENERIC_WEBHOOK_URL required when ALERT_METHOD=webhook"
                )

        jwt_algorithms = [
            alg.strip()
            for alg in os.getenv("AUTH_JWT_ALGORITHMS", "HS256").split(",")
            if alg.strip()
        ]
        if jwt_algorithms and any(
            alg not in JWT_ALGORITHMS_ALLOWED for alg in jwt_algorithms
        ):
            errors.append("AUTH_JWT_ALGORITHMS contains unsupported values")

        enable_external_api = (
            os.getenv("ENABLE_EXTERNAL_API_CLASSIFICATION", "true").lower() == "true"
        )
        external_api_url = os.getenv("EXTERNAL_API_URL")
        if enable_external_api and not external_api_url:
            errors.append(
                "EXTERNAL_API_URL required when ENABLE_EXTERNAL_API_CLASSIFICATION=true"
            )
        if external_api_url and not external_api_url.startswith("https://"):
            if os.getenv("ALLOW_INSECURE_EXTERNAL_API_URL", "false").lower() != "true":
                errors.append("EXTERNAL_API_URL must use https://")

        enable_ip_rep = os.getenv("ENABLE_IP_REPUTATION", "false").lower() == "true"
        ip_rep_url = os.getenv("IP_REPUTATION_API_URL")
        if enable_ip_rep and not ip_rep_url:
            errors.append(
                "IP_REPUTATION_API_URL required when ENABLE_IP_REPUTATION=true"
            )
        if ip_rep_url and not ip_rep_url.startswith("https://"):
            if os.getenv("ALLOW_INSECURE_IP_REPUTATION_URL", "false").lower() != "true":
                errors.append("IP_REPUTATION_API_URL must use https://")

        return len(errors) == 0, errors

    def compute_checksum(self, config: AppConfig) -> str:
        """
        Compute checksum of configuration for drift detection.

        Args:
            config: Configuration instance.

        Returns:
            SHA256 hash of configuration.
        """
        # Convert config to JSON string (sorted keys for consistency)
        config_dict = config.to_dict()
        config_json = json.dumps(config_dict, sort_keys=True)
        return hashlib.sha256(config_json.encode()).hexdigest()

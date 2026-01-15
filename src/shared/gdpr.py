"""GDPR Compliance Framework for AI Scraping Defense.

This module implements GDPR compliance features including:
- Consent management
- Right to be forgotten (data deletion)
- Data minimization principles
- Privacy impact assessments
- Automated compliance reporting
- Data protection officer designation
"""

import asyncio
import datetime
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from redis.exceptions import RedisError

from .config import CONFIG, tenant_key
from .redis_client import get_redis_connection

logger = logging.getLogger(__name__)

# GDPR Configuration
GDPR_ENABLED = os.getenv("GDPR_ENABLED", "true").lower() == "true"
GDPR_DPO_NAME = os.getenv("GDPR_DPO_NAME", "Data Protection Officer")
GDPR_DPO_EMAIL = os.getenv("GDPR_DPO_EMAIL", "dpo@example.com")
GDPR_DPO_PHONE = os.getenv("GDPR_DPO_PHONE", "")
GDPR_DATA_RETENTION_DAYS = int(os.getenv("GDPR_DATA_RETENTION_DAYS", "365"))
GDPR_CONSENT_REQUIRED = os.getenv("GDPR_CONSENT_REQUIRED", "true").lower() == "true"
GDPR_AUDIT_LOG_FILE = os.getenv("GDPR_AUDIT_LOG_FILE", "/app/logs/gdpr_audit.log")

# Data minimization constants
USER_AGENT_MAX_LENGTH = 100
IPV6_ANONYMIZATION_LENGTH = 24

# Audit log retention
GDPR_AUDIT_LOG_MAX_ENTRIES = 10000


class ConsentType(str, Enum):
    """Types of consent that can be requested."""

    ESSENTIAL = "essential"  # Required for service operation
    ANALYTICS = "analytics"  # Usage analytics and monitoring
    SECURITY = "security"  # Security monitoring and bot detection
    MARKETING = "marketing"  # Marketing communications
    THIRD_PARTY = "third_party"  # Third-party data sharing


class DataCategory(str, Enum):
    """Categories of personal data collected."""

    IP_ADDRESS = "ip_address"
    USER_AGENT = "user_agent"
    REQUEST_HEADERS = "request_headers"
    ACCESS_LOGS = "access_logs"
    AUTHENTICATION = "authentication"
    PAYMENT_INFO = "payment_info"
    BEHAVIORAL_DATA = "behavioral_data"


@dataclass
class ConsentRecord:
    """Record of user consent."""

    user_id: str
    consent_type: ConsentType
    granted: bool
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class DataDeletionRequest:
    """Request for data deletion (right to be forgotten)."""

    request_id: str
    user_id: str
    email: Optional[str]
    data_categories: List[DataCategory]
    requested_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    status: str = "pending"  # pending, processing, completed, failed
    completed_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class GDPRComplianceManager:
    """Manages GDPR compliance operations."""

    def __init__(self):
        """Initialize GDPR compliance manager."""
        self.redis_conn = get_redis_connection()
        self.consent_key_prefix = tenant_key("gdpr:consent")
        self.deletion_key_prefix = tenant_key("gdpr:deletion")
        self.audit_key = tenant_key("gdpr:audit_log")

    def _log_gdpr_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log GDPR compliance event."""
        try:
            # Log to file using structured logging
            from .utils import log_event as log_event_to_file

            log_event_to_file(GDPR_AUDIT_LOG_FILE, event_type, data)

            # Also store in Redis for quick access
            if self.redis_conn:
                event_data = json.dumps(
                    {
                        "timestamp": datetime.datetime.now(datetime.timezone.utc)
                        .isoformat()
                        .replace("+00:00", "Z"),
                        "event_type": event_type,
                        **data,
                    }
                )
                self.redis_conn.lpush(self.audit_key, event_data)
                self.redis_conn.ltrim(self.audit_key, 0, GDPR_AUDIT_LOG_MAX_ENTRIES - 1)
        except Exception as e:
            logger.error(f"Failed to log GDPR event: {e}")

    def record_consent(
        self,
        user_id: str,
        consent_type: ConsentType,
        granted: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        expires_days: Optional[int] = None,
    ) -> ConsentRecord:
        """Record user consent."""
        expires_at = None
        if expires_days:
            expires_dt = datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(days=expires_days)
            expires_at = expires_dt.isoformat().replace("+00:00", "Z")

        consent = ConsentRecord(
            user_id=user_id,
            consent_type=consent_type,
            granted=granted,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )

        if self.redis_conn:
            try:
                key = f"{self.consent_key_prefix}:{user_id}:{consent_type.value}"
                self.redis_conn.set(key, json.dumps(consent.to_dict()))
                if expires_days:
                    self.redis_conn.expire(key, expires_days * 86400)
            except RedisError as e:
                logger.error(f"Failed to store consent in Redis: {e}")

        self._log_gdpr_event(
            "consent_recorded",
            {
                "user_id": user_id,
                "consent_type": consent_type.value,
                "granted": granted,
                "ip_address": ip_address,
            },
        )

        return consent

    def check_consent(self, user_id: str, consent_type: ConsentType) -> bool:
        """Check if user has granted consent."""
        if not GDPR_ENABLED or not GDPR_CONSENT_REQUIRED:
            return True

        if consent_type == ConsentType.ESSENTIAL:
            return True

        if not self.redis_conn:
            return False

        try:
            key = f"{self.consent_key_prefix}:{user_id}:{consent_type.value}"
            data = self.redis_conn.get(key)
            if not data:
                return False

            consent = json.loads(data)
            if not consent.get("granted"):
                return False

            expires_at = consent.get("expires_at")
            if expires_at:
                expires_dt = datetime.datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                )
                if datetime.datetime.now(datetime.timezone.utc) > expires_dt:
                    return False

            return True
        except Exception as e:
            logger.error(f"Failed to check consent: {e}")
            return False

    def get_user_consents(self, user_id: str) -> Dict[str, ConsentRecord]:
        """Get all consents for a user."""
        consents = {}
        if not self.redis_conn:
            return consents

        try:
            pattern = f"{self.consent_key_prefix}:{user_id}:*"
            for key in self.redis_conn.scan_iter(match=pattern):
                data = self.redis_conn.get(key)
                if data:
                    consent_data = json.loads(data)
                    consent_type = consent_data.get("consent_type")
                    consents[consent_type] = ConsentRecord(**consent_data)
        except Exception as e:
            logger.error(f"Failed to get user consents: {e}")

        return consents

    def request_data_deletion(
        self,
        user_id: str,
        email: Optional[str] = None,
        data_categories: Optional[List[DataCategory]] = None,
    ) -> DataDeletionRequest:
        """Request deletion of user data (right to be forgotten)."""
        import uuid

        request_id = str(uuid.uuid4())
        if data_categories is None:
            data_categories = list(DataCategory)

        deletion_request = DataDeletionRequest(
            request_id=request_id,
            user_id=user_id,
            email=email,
            data_categories=data_categories,
        )

        if self.redis_conn:
            try:
                key = f"{self.deletion_key_prefix}:{request_id}"
                self.redis_conn.set(key, json.dumps(deletion_request.to_dict()))
                self.redis_conn.expire(key, 90 * 86400)  # Keep for 90 days

                # Add to processing queue
                queue_key = f"{self.deletion_key_prefix}:queue"
                self.redis_conn.lpush(queue_key, request_id)
            except RedisError as e:
                logger.error(f"Failed to store deletion request: {e}")

        self._log_gdpr_event(
            "deletion_requested",
            {
                "request_id": request_id,
                "user_id": user_id,
                "email": email,
                "data_categories": [dc.value for dc in data_categories],
            },
        )

        return deletion_request

    def process_deletion_request(self, request_id: str) -> bool:
        """Process a data deletion request."""
        if not self.redis_conn:
            return False

        try:
            key = f"{self.deletion_key_prefix}:{request_id}"
            data = self.redis_conn.get(key)
            if not data:
                logger.warning(f"Deletion request {request_id} not found")
                return False

            request_data = json.loads(data)
            user_id = request_data["user_id"]
            data_categories = request_data["data_categories"]

            # Update status
            request_data["status"] = "processing"
            self.redis_conn.set(key, json.dumps(request_data))

            # Delete data based on categories
            self._delete_user_data(user_id, data_categories)

            # Mark as completed
            request_data["status"] = "completed"
            request_data["completed_at"] = (
                datetime.datetime.now(datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            self.redis_conn.set(key, json.dumps(request_data))

            self._log_gdpr_event(
                "deletion_completed",
                {"request_id": request_id, "user_id": user_id},
            )

            return True
        except Exception as e:
            logger.error(f"Failed to process deletion request {request_id}: {e}")
            # Update status to failed
            try:
                request_data["status"] = "failed"
                request_data["notes"] = str(e)
                self.redis_conn.set(key, json.dumps(request_data))
            except Exception as redis_err:
                logger.error(
                    f"Failed to update deletion request status in Redis: {redis_err}"
                )
            return False

    def _delete_user_data(self, user_id: str, data_categories: List[str]) -> None:
        """Delete user data from Redis."""
        if not self.redis_conn:
            return

        try:
            # Delete consent records
            if (
                "authentication" in data_categories
                or "behavioral_data" in data_categories
            ):
                pattern = f"{self.consent_key_prefix}:{user_id}:*"
                for key in self.redis_conn.scan_iter(match=pattern):
                    self.redis_conn.delete(key)

            # Delete IP-based data
            if "ip_address" in data_categories or "access_logs" in data_categories:
                # Delete rate limit data
                rate_limit_pattern = tenant_key(f"admin_ui:auth:{user_id}")
                for key in self.redis_conn.scan_iter(match=rate_limit_pattern):
                    self.redis_conn.delete(key)

            # Delete behavioral data
            if "behavioral_data" in data_categories:
                behavioral_pattern = tenant_key(f"*:{user_id}:*")
                for key in self.redis_conn.scan_iter(match=behavioral_pattern):
                    self.redis_conn.delete(key)

            logger.info(
                f"Deleted data for user {user_id}, categories: {data_categories}"
            )
        except RedisError as e:
            logger.error(f"Redis error deleting user data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting user data: {e}")
            raise

    def minimize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply data minimization principles to collected data."""
        if not GDPR_ENABLED:
            return data

        minimized = {}
        # Only keep essential fields
        essential_fields = [
            "timestamp",
            "event_type",
            "ip_address",
            "user_agent",
            "path",
            "method",
            "status_code",
        ]

        for field in essential_fields:
            if field in data:
                value = data[field]
                # Anonymize IP address (keep only first 3 octets for IPv4)
                if field == "ip_address" and isinstance(value, str):
                    parts = value.split(".")
                    if len(parts) == 4:
                        minimized[field] = f"{parts[0]}.{parts[1]}.{parts[2]}.0"
                    else:
                        # For IPv6 or other formats, truncate
                        minimized[field] = value[:IPV6_ANONYMIZATION_LENGTH] + "::0"
                # Truncate user agent to reduce fingerprinting
                elif field == "user_agent" and isinstance(value, str):
                    minimized[field] = value[:USER_AGENT_MAX_LENGTH]
                else:
                    minimized[field] = value

        return minimized

    def generate_compliance_report(self) -> Dict[str, Any]:
        """Generate automated GDPR compliance report."""
        report = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "gdpr_enabled": GDPR_ENABLED,
            "dpo_contact": {
                "name": GDPR_DPO_NAME,
                "email": GDPR_DPO_EMAIL,
                "phone": GDPR_DPO_PHONE,
            },
            "data_retention_days": GDPR_DATA_RETENTION_DAYS,
            "consent_required": GDPR_CONSENT_REQUIRED,
            "statistics": {},
        }

        if not self.redis_conn:
            return report

        try:
            # Count consent records
            consent_pattern = f"{self.consent_key_prefix}:*"
            consent_count = sum(
                1 for _ in self.redis_conn.scan_iter(match=consent_pattern)
            )
            report["statistics"]["total_consent_records"] = consent_count

            # Count deletion requests
            deletion_pattern = f"{self.deletion_key_prefix}:*"
            deletion_count = sum(
                1 for _ in self.redis_conn.scan_iter(match=deletion_pattern)
            )
            report["statistics"]["total_deletion_requests"] = deletion_count

            # Get recent audit events
            audit_events = self.redis_conn.lrange(self.audit_key, 0, 99)
            report["recent_events_count"] = len(audit_events)

        except Exception as e:
            logger.error(f"Error generating compliance report: {e}")
            report["error"] = str(e)

        self._log_gdpr_event("compliance_report_generated", report)

        return report

    async def cleanup_expired_data(self) -> int:
        """Clean up data older than retention period.

        This method should be called periodically (e.g., daily) to remove
        data that has exceeded the retention period. The implementation
        scans through stored data and removes records based on timestamps.

        Returns:
            Number of records deleted
        """
        if not GDPR_ENABLED or not self.redis_conn:
            return 0

        deleted_count = 0
        cutoff_timestamp = (
            (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=GDPR_DATA_RETENTION_DAYS)
            )
            .isoformat()
            .replace("+00:00", "Z")
        )

        try:
            logger.info(
                f"Running GDPR data cleanup for data older than {cutoff_timestamp}"
            )

            # Clean up expired consent records
            consent_pattern = f"{self.consent_key_prefix}:*"
            for key in self.redis_conn.scan_iter(match=consent_pattern):
                try:
                    data = self.redis_conn.get(key)
                    if data:
                        consent = json.loads(data)
                        timestamp = consent.get("timestamp", "")
                        if timestamp and timestamp < cutoff_timestamp:
                            self.redis_conn.delete(key)
                            deleted_count += 1
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse consent data for key {key}: {e}")
                    continue

            # Clean up old audit log entries (keep only recent ones)
            # Keep last GDPR_AUDIT_LOG_MAX_ENTRIES as configured in _log_gdpr_event
            current_length = self.redis_conn.llen(self.audit_key)
            if current_length > GDPR_AUDIT_LOG_MAX_ENTRIES:
                self.redis_conn.ltrim(self.audit_key, 0, GDPR_AUDIT_LOG_MAX_ENTRIES - 1)
                deleted_count += current_length - GDPR_AUDIT_LOG_MAX_ENTRIES

            logger.info(f"GDPR cleanup completed: deleted {deleted_count} records")
        except RedisError as e:
            logger.error(f"Redis error during data cleanup: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during data cleanup: {e}")

        self._log_gdpr_event(
            "data_cleanup_completed",
            {"deleted_count": deleted_count, "cutoff_timestamp": cutoff_timestamp},
        )

        return deleted_count


# Global instance
_gdpr_manager: Optional[GDPRComplianceManager] = None


def get_gdpr_manager() -> GDPRComplianceManager:
    """Get or create the global GDPR compliance manager."""
    global _gdpr_manager
    if _gdpr_manager is None:
        _gdpr_manager = GDPRComplianceManager()
    return _gdpr_manager

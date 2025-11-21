"""Insider Threat Detection System.

Detects anomalous user behavior patterns that may indicate insider threats:
- Unusual access patterns
- Privilege escalation attempts
- Data exfiltration indicators
- After-hours access anomalies
- Suspicious authentication patterns
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)

# Configuration from environment
THREAT_WINDOW_HOURS = int(os.getenv("INSIDER_THREAT_WINDOW_HOURS", "24"))
MAX_FAILED_AUTH_ATTEMPTS = int(os.getenv("INSIDER_MAX_FAILED_AUTH", "5"))
SUSPICIOUS_ACCESS_THRESHOLD = float(os.getenv("INSIDER_SUSPICIOUS_THRESHOLD", "0.7"))
WORKING_HOURS_START = int(os.getenv("WORKING_HOURS_START", "8"))
WORKING_HOURS_END = int(os.getenv("WORKING_HOURS_END", "18"))
REDIS_KEY_PREFIX = os.getenv("INSIDER_THREAT_KEY_PREFIX", "insider_threat:")
REDIS_TTL_SECONDS = int(os.getenv("INSIDER_THREAT_TTL", "86400"))  # 24 hours


@dataclass
class UserBehaviorProfile:
    """Profile of user behavior patterns."""

    user_id: str
    access_count: int = 0
    failed_auth_count: int = 0
    after_hours_count: int = 0
    sensitive_resources: Set[str] = field(default_factory=set)
    last_seen: float = field(default_factory=time.time)
    ip_addresses: Set[str] = field(default_factory=set)
    user_agents: Set[str] = field(default_factory=set)
    accessed_endpoints: List[str] = field(default_factory=list)


@dataclass
class InsiderThreatEvent:
    """Represents a detected insider threat event."""

    user_id: str
    timestamp: float
    threat_type: str
    risk_score: float
    details: Dict[str, any]
    indicators: List[str]


class InsiderThreatDetector:
    """Detects and analyzes insider threat patterns."""

    def __init__(self, redis_conn=None):
        """Initialize the insider threat detector."""
        self.redis = redis_conn or get_redis_connection()
        self._profiles: Dict[str, UserBehaviorProfile] = {}
        self._threat_cache: List[InsiderThreatEvent] = []

    def _get_redis_key(self, user_id: str, key_type: str) -> str:
        """Generate Redis key for user data."""
        return f"{REDIS_KEY_PREFIX}{key_type}:{user_id}"

    def _load_profile(self, user_id: str) -> UserBehaviorProfile:
        """Load user behavior profile from Redis or create new."""
        if user_id in self._profiles:
            return self._profiles[user_id]

        profile = UserBehaviorProfile(user_id=user_id)

        if self.redis:
            try:
                key = self._get_redis_key(user_id, "profile")
                data = self.redis.get(key)
                if data:
                    profile_data = json.loads(data)
                    profile.access_count = profile_data.get("access_count", 0)
                    profile.failed_auth_count = profile_data.get("failed_auth_count", 0)
                    profile.after_hours_count = profile_data.get("after_hours_count", 0)
                    profile.sensitive_resources = set(profile_data.get("sensitive_resources", []))
                    profile.last_seen = profile_data.get("last_seen", time.time())
                    profile.ip_addresses = set(profile_data.get("ip_addresses", []))
                    profile.user_agents = set(profile_data.get("user_agents", []))
                    profile.accessed_endpoints = profile_data.get("accessed_endpoints", [])
            except Exception as e:
                logger.error(f"Error loading profile for {user_id}: {e}")

        self._profiles[user_id] = profile
        return profile

    def _save_profile(self, profile: UserBehaviorProfile) -> None:
        """Save user behavior profile to Redis."""
        if not self.redis:
            return

        try:
            key = self._get_redis_key(profile.user_id, "profile")
            data = {
                "access_count": profile.access_count,
                "failed_auth_count": profile.failed_auth_count,
                "after_hours_count": profile.after_hours_count,
                "sensitive_resources": list(profile.sensitive_resources),
                "last_seen": profile.last_seen,
                "ip_addresses": list(profile.ip_addresses),
                "user_agents": list(profile.user_agents),
                "accessed_endpoints": profile.accessed_endpoints[-100:],  # Keep last 100
            }
            self.redis.setex(key, REDIS_TTL_SECONDS, json.dumps(data))
        except Exception as e:
            logger.error(f"Error saving profile for {profile.user_id}: {e}")

    def record_access(
        self,
        user_id: str,
        endpoint: str,
        client_ip: str,
        user_agent: str,
        is_sensitive: bool = False,
    ) -> None:
        """Record a user access event."""
        profile = self._load_profile(user_id)

        profile.access_count += 1
        profile.last_seen = time.time()
        profile.ip_addresses.add(client_ip)
        profile.user_agents.add(user_agent)
        profile.accessed_endpoints.append(endpoint)

        if is_sensitive:
            profile.sensitive_resources.add(endpoint)

        # Check if access is after hours
        now = datetime.now()
        if now.hour < WORKING_HOURS_START or now.hour >= WORKING_HOURS_END:
            profile.after_hours_count += 1

        self._save_profile(profile)

    def record_failed_auth(self, user_id: str, client_ip: str) -> None:
        """Record a failed authentication attempt."""
        profile = self._load_profile(user_id)
        profile.failed_auth_count += 1
        profile.ip_addresses.add(client_ip)
        self._save_profile(profile)

    def _is_after_hours(self) -> bool:
        """Check if current time is outside working hours."""
        now = datetime.now()
        return now.hour < WORKING_HOURS_START or now.hour >= WORKING_HOURS_END

    def _detect_excessive_failed_auth(self, profile: UserBehaviorProfile) -> Optional[Tuple[str, float, List[str]]]:
        """Detect excessive failed authentication attempts."""
        if profile.failed_auth_count >= MAX_FAILED_AUTH_ATTEMPTS:
            risk_score = min(1.0, profile.failed_auth_count / (MAX_FAILED_AUTH_ATTEMPTS * 2))
            indicators = [
                f"Failed authentication attempts: {profile.failed_auth_count}",
                f"Threshold: {MAX_FAILED_AUTH_ATTEMPTS}",
            ]
            return ("excessive_failed_auth", risk_score, indicators)
        return None

    def _detect_unusual_after_hours_access(self, profile: UserBehaviorProfile) -> Optional[Tuple[str, float, List[str]]]:
        """Detect unusual after-hours access patterns."""
        if profile.access_count > 0:
            after_hours_ratio = profile.after_hours_count / profile.access_count
            if after_hours_ratio > 0.5 and profile.after_hours_count > 10:
                risk_score = min(1.0, after_hours_ratio)
                indicators = [
                    f"After-hours access ratio: {after_hours_ratio:.2f}",
                    f"After-hours count: {profile.after_hours_count}",
                ]
                return ("after_hours_access", risk_score, indicators)
        return None

    def _detect_suspicious_ip_behavior(self, profile: UserBehaviorProfile) -> Optional[Tuple[str, float, List[str]]]:
        """Detect suspicious IP address patterns."""
        if len(profile.ip_addresses) > 5:
            # Multiple IPs in short time may indicate account compromise
            risk_score = min(1.0, len(profile.ip_addresses) / 10)
            indicators = [
                f"Multiple IP addresses: {len(profile.ip_addresses)}",
                "Possible account compromise or credential sharing",
            ]
            return ("multiple_ips", risk_score, indicators)
        return None

    def _detect_sensitive_resource_access(self, profile: UserBehaviorProfile) -> Optional[Tuple[str, float, List[str]]]:
        """Detect excessive access to sensitive resources."""
        if len(profile.sensitive_resources) > 10:
            risk_score = min(1.0, len(profile.sensitive_resources) / 20)
            indicators = [
                f"Sensitive resources accessed: {len(profile.sensitive_resources)}",
                "Possible data exfiltration attempt",
            ]
            return ("sensitive_resource_access", risk_score, indicators)
        return None

    def analyze_user(self, user_id: str) -> Optional[InsiderThreatEvent]:
        """Analyze user behavior and detect insider threats."""
        profile = self._load_profile(user_id)

        if profile.access_count == 0:
            return None

        # Run all detection heuristics
        detections = [
            self._detect_excessive_failed_auth(profile),
            self._detect_unusual_after_hours_access(profile),
            self._detect_suspicious_ip_behavior(profile),
            self._detect_sensitive_resource_access(profile),
        ]

        # Filter out None values
        valid_detections = [d for d in detections if d is not None]

        if not valid_detections:
            return None

        # Combine all detections
        threat_types = [d[0] for d in valid_detections]
        max_risk_score = max(d[1] for d in valid_detections)
        all_indicators = []
        for d in valid_detections:
            all_indicators.extend(d[2])

        if max_risk_score >= SUSPICIOUS_ACCESS_THRESHOLD:
            event = InsiderThreatEvent(
                user_id=user_id,
                timestamp=time.time(),
                threat_type=", ".join(threat_types),
                risk_score=max_risk_score,
                details={
                    "access_count": profile.access_count,
                    "failed_auth_count": profile.failed_auth_count,
                    "after_hours_count": profile.after_hours_count,
                    "sensitive_resources_count": len(profile.sensitive_resources),
                    "ip_addresses_count": len(profile.ip_addresses),
                },
                indicators=all_indicators,
            )

            self._threat_cache.append(event)
            self._publish_threat_event(event)
            return event

        return None

    def _publish_threat_event(self, event: InsiderThreatEvent) -> None:
        """Publish insider threat event to Redis pub/sub."""
        if not self.redis:
            return

        try:
            channel = f"{REDIS_KEY_PREFIX}events"
            event_data = {
                "user_id": event.user_id,
                "timestamp": event.timestamp,
                "threat_type": event.threat_type,
                "risk_score": event.risk_score,
                "details": event.details,
                "indicators": event.indicators,
            }
            self.redis.publish(channel, json.dumps(event_data))
            logger.warning(
                f"Insider threat detected for user {event.user_id}: "
                f"{event.threat_type} (risk score: {event.risk_score:.2f})"
            )
        except Exception as e:
            logger.error(f"Error publishing threat event: {e}")

    def get_recent_threats(self, hours: int = 24) -> List[InsiderThreatEvent]:
        """Get recent insider threat events."""
        cutoff = time.time() - (hours * 3600)
        return [event for event in self._threat_cache if event.timestamp >= cutoff]

    def reset_user_profile(self, user_id: str) -> None:
        """Reset user behavior profile (e.g., after investigation)."""
        if self.redis:
            try:
                key = self._get_redis_key(user_id, "profile")
                self.redis.delete(key)
            except Exception as e:
                logger.error(f"Error resetting profile for {user_id}: {e}")

        if user_id in self._profiles:
            del self._profiles[user_id]


# Global instance for convenience
_detector: Optional[InsiderThreatDetector] = None


def get_insider_threat_detector() -> InsiderThreatDetector:
    """Get or create global insider threat detector instance."""
    global _detector
    if _detector is None:
        _detector = InsiderThreatDetector()
    return _detector

"""Mobile API security and threat detection module.

This module provides mobile-specific security controls including:
- Mobile platform detection (iOS, Android, etc.)
- Mobile app attestation validation
- Mobile-specific threat pattern detection
- Mobile bot detection
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MobilePlatform(Enum):
    """Supported mobile platforms."""

    IOS = "ios"
    ANDROID = "android"
    WINDOWS_MOBILE = "windows_mobile"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MobileDeviceInfo:
    """Information about a mobile device extracted from request metadata."""

    platform: MobilePlatform
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    is_emulator: bool = False
    is_rooted: bool = False
    attestation_valid: bool = False


class MobilePlatformDetector:
    """Detect mobile platform from User-Agent and headers."""

    # User-Agent patterns for mobile detection
    IOS_PATTERN = re.compile(
        r"iPhone|iPad|iPod|iOS", re.IGNORECASE
    )
    ANDROID_PATTERN = re.compile(
        r"Android", re.IGNORECASE
    )
    WINDOWS_MOBILE_PATTERN = re.compile(
        r"Windows Phone|Windows Mobile|IEMobile", re.IGNORECASE
    )

    # Known emulator and rooted device indicators in User-Agent
    EMULATOR_INDICATORS = [
        "Emulator",
        "Simulator",
        "GenericAndroid",
        "sdk_gphone",
        "generic_x86",
    ]

    ROOT_INDICATORS = [
        "Magisk",
        "SuperSU",
        "Xposed",
    ]

    @classmethod
    def detect_platform(cls, user_agent: str) -> MobilePlatform:
        """Detect mobile platform from User-Agent string."""
        if not user_agent:
            return MobilePlatform.UNKNOWN

        if cls.IOS_PATTERN.search(user_agent):
            return MobilePlatform.IOS
        elif cls.ANDROID_PATTERN.search(user_agent):
            return MobilePlatform.ANDROID
        elif cls.WINDOWS_MOBILE_PATTERN.search(user_agent):
            return MobilePlatform.WINDOWS_MOBILE

        return MobilePlatform.UNKNOWN

    @classmethod
    def detect_emulator(cls, user_agent: str, headers: dict) -> bool:
        """Detect if request is from an emulator."""
        if not user_agent:
            return False

        # Check User-Agent for emulator indicators
        for indicator in cls.EMULATOR_INDICATORS:
            if indicator.lower() in user_agent.lower():
                return True

        # Check custom headers that may indicate emulator
        x_device_type = headers.get("X-Device-Type", "").lower()
        if "emulator" in x_device_type or "simulator" in x_device_type:
            return True

        return False

    @classmethod
    def detect_rooted(cls, user_agent: str, headers: dict) -> bool:
        """Detect if device appears to be rooted/jailbroken."""
        if not user_agent:
            return False

        # Check User-Agent for root indicators
        for indicator in cls.ROOT_INDICATORS:
            if indicator.lower() in user_agent.lower():
                return True

        # Check custom header indicating root detection
        x_device_security = headers.get("X-Device-Security", "").lower()
        if "rooted" in x_device_security or "jailbroken" in x_device_security:
            return True

        return False

    @classmethod
    def extract_device_info(
        cls, user_agent: str, headers: dict
    ) -> MobileDeviceInfo:
        """Extract mobile device information from request."""
        platform = cls.detect_platform(user_agent)
        is_emulator = cls.detect_emulator(user_agent, headers)
        is_rooted = cls.detect_rooted(user_agent, headers)

        # Extract version information from custom headers
        app_version = headers.get("X-App-Version")
        os_version = headers.get("X-OS-Version")
        device_model = headers.get("X-Device-Model")

        return MobileDeviceInfo(
            platform=platform,
            app_version=app_version,
            os_version=os_version,
            device_model=device_model,
            is_emulator=is_emulator,
            is_rooted=is_rooted,
            attestation_valid=False,
        )


class MobileThreatDetector:
    """Detect mobile-specific threats and suspicious patterns."""

    @staticmethod
    def calculate_mobile_threat_score(device_info: MobileDeviceInfo) -> float:
        """Calculate threat score for mobile device (0.0 to 1.0).

        Higher scores indicate higher risk.
        """
        score = 0.0

        # Unknown platform is suspicious
        if device_info.platform == MobilePlatform.UNKNOWN:
            score += 0.3

        # Emulators are often used by bots
        if device_info.is_emulator:
            score += 0.4

        # Rooted devices have compromised security
        if device_info.is_rooted:
            score += 0.3

        # Missing attestation is suspicious for known platforms
        if device_info.platform in (
            MobilePlatform.IOS,
            MobilePlatform.ANDROID,
        ) and not device_info.attestation_valid:
            score += 0.2

        # Missing version info is suspicious
        if not device_info.app_version and device_info.platform != MobilePlatform.UNKNOWN:
            score += 0.1

        return min(score, 1.0)

    @staticmethod
    def is_mobile_bot(user_agent: str, device_info: MobileDeviceInfo) -> bool:
        """Detect if request appears to be from a mobile bot."""
        # Desktop user agents claiming to be mobile
        desktop_indicators = ["Windows NT", "Macintosh", "X11", "Linux"]
        has_desktop = any(ind in user_agent for ind in desktop_indicators)
        has_mobile = device_info.platform != MobilePlatform.UNKNOWN

        if has_desktop and has_mobile:
            # Mixed signals - likely spoofed
            return True

        # Emulator without valid attestation
        if device_info.is_emulator and not device_info.attestation_valid:
            return True

        return False


class MobileAppAttestationValidator:
    """Validate mobile app attestation tokens.

    This is a basic implementation. In production, integrate with:
    - Apple App Attest for iOS
    - Google Play Integrity API for Android
    """

    @staticmethod
    def validate_ios_attestation(
        attestation_token: str, challenge: str
    ) -> bool:
        """Validate iOS App Attest token.

        Args:
            attestation_token: The attestation token from the mobile app
            challenge: Server-generated challenge

        Returns:
            True if attestation is valid, False otherwise

        Note:
            This is a placeholder. Production implementation should integrate
            with Apple's App Attest API.
        """
        # Placeholder validation - implement actual App Attest validation
        if not attestation_token or not challenge:
            return False

        # In production, validate:
        # 1. Decode and verify attestation statement
        # 2. Verify challenge matches
        # 3. Verify signing certificate chain
        # 4. Verify app ID matches expected value
        # 5. Check attestation freshness

        return len(attestation_token) > 32  # Placeholder

    @staticmethod
    def validate_android_attestation(
        integrity_token: str, nonce: str
    ) -> bool:
        """Validate Android Play Integrity API token.

        Args:
            integrity_token: The integrity token from Play Integrity API
            nonce: Server-generated nonce

        Returns:
            True if integrity check passes, False otherwise

        Note:
            This is a placeholder. Production implementation should integrate
            with Google Play Integrity API.
        """
        # Placeholder validation - implement actual Play Integrity validation
        if not integrity_token or not nonce:
            return False

        # In production:
        # 1. Decrypt and verify integrity token
        # 2. Verify nonce matches
        # 3. Check device integrity verdict
        # 4. Verify app recognition verdict
        # 5. Check account details if needed

        return len(integrity_token) > 32  # Placeholder

    @classmethod
    def validate_attestation(
        cls,
        platform: MobilePlatform,
        attestation_token: str,
        challenge: str,
    ) -> bool:
        """Validate mobile app attestation based on platform.

        Args:
            platform: Mobile platform (iOS or Android)
            attestation_token: Platform-specific attestation token
            challenge: Server-generated challenge/nonce

        Returns:
            True if attestation is valid, False otherwise
        """
        if platform == MobilePlatform.IOS:
            return cls.validate_ios_attestation(attestation_token, challenge)
        elif platform == MobilePlatform.ANDROID:
            return cls.validate_android_attestation(attestation_token, challenge)

        return False

"""
Generic HTTP-based alert sender for webhook and API-based alerts.

This module provides a generic abstraction for sending alerts via HTTP webhooks
and APIs. It handles alert formatting, error handling, retry logic, and logging
specific to alert delivery scenarios.

The module is designed to be extended by specific alert implementations (like Slack,
Discord, Teams, etc.) while providing common functionality for HTTP-based alerting.

Key Features:
- Generic alert payload formatting
- Comprehensive error handling and logging
- Configurable timeouts and retry logic
- Support for different HTTP methods and content types
- Extensible base for specific alert service implementations

Usage Example:
    alert_sender = HttpAlertSender(
        webhook_url="https://hooks.example.com/webhook",
        timeout=10.0
    )

    result = await alert_sender.send_alert({
        "message": "Alert from AI Defense System",
        "severity": "high",
        "details": {"ip": "192.168.1.1"}
    })
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .http_client import AsyncHttpClient, httpx

logger = logging.getLogger(__name__)


def _safe_endpoint_for_logs(url: str) -> str:
    """Return a non-sensitive identifier for an alert endpoint.

    Webhook URLs commonly embed credentials/tokens in their path. Logging the full URL
    leaks secrets to logs and crash reports. We log only the origin plus a short
    stable fingerprint to aid debugging without disclosure.
    """
    try:
        parsed = urlparse(url)
        origin = (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else "<invalid-url>"
        )
    except Exception:  # pragma: no cover - defensive
        origin = "<invalid-url>"
    fp = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{origin} (id={fp})"


class AlertDeliveryError(Exception):
    """Raised when an alert fails to be delivered."""

    def __init__(
        self,
        message: str,
        response_status: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(message)
        self.response_status = response_status
        self.response_body = response_body


class HttpAlertSender:
    """Generic async alert sender for webhook/API-based alerts.

    This class provides a foundation for sending alerts via HTTP webhooks and APIs.
    It handles the common patterns of alert delivery including payload formatting,
    error handling, and logging. Specific alert services can extend this class
    to implement their own formatting and authentication requirements.

    Attributes:
        webhook_url (str): The URL to send alerts to
        timeout (float): Timeout in seconds for HTTP requests
        default_headers (Dict[str, str]): Default headers to include with requests
        max_retry_attempts (int): Maximum number of retry attempts for failed requests
    """

    def __init__(
        self,
        webhook_url: str,
        timeout: float = 10.0,
        default_headers: Optional[Dict[str, str]] = None,
        max_retry_attempts: int = 3,
        verify_ssl: bool = True,
    ):
        """Initialize the HTTP alert sender.

        Args:
            webhook_url: The webhook URL to send alerts to
            timeout: Timeout in seconds for HTTP requests
            default_headers: Default headers to include with all requests
            max_retry_attempts: Maximum number of retry attempts for failed deliveries
            verify_ssl: Whether to verify SSL certificates
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.default_headers = default_headers or {"Content-Type": "application/json"}
        self.max_retry_attempts = max_retry_attempts
        self.verify_ssl = verify_ssl

    def format_alert_payload(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format alert data into a payload suitable for HTTP delivery.

        This method can be overridden by subclasses to implement specific
        formatting requirements for different alert services.

        Args:
            alert_data: Raw alert data containing message, severity, details, etc.

        Returns:
            Dict containing the formatted payload ready for HTTP transmission
        """
        # Default generic payload format
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert_type": alert_data.get("alert_type", "generic_alert"),
            "message": alert_data.get("message", "Alert from AI Defense System"),
            "severity": alert_data.get("severity", "medium"),
            "source": alert_data.get("source", "ai-scraping-defense"),
            "details": alert_data.get("details", {}),
        }

        # Include any additional fields from the original alert data
        for key, value in alert_data.items():
            if key not in payload:
                payload[key] = value

        logger.debug(f"Formatted alert payload: {json.dumps(payload, default=str)}")
        return payload

    def prepare_headers(
        self, additional_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Prepare HTTP headers for the alert request.

        Args:
            additional_headers: Additional headers to include for this specific request

        Returns:
            Dict containing all headers to be sent with the request
        """
        headers = self.default_headers.copy()
        if additional_headers:
            headers.update(additional_headers)
        return headers

    async def send_alert(
        self,
        alert_data: Dict[str, Any],
        additional_headers: Optional[Dict[str, str]] = None,
        retry_attempts: Optional[int] = None,
    ) -> bool:
        """Send an alert via HTTP POST request with error handling and retry logic.

        Args:
            alert_data: Alert data to be formatted and sent
            additional_headers: Optional additional headers for this request
            retry_attempts: Override the default retry attempts for this request

        Returns:
            bool: True if the alert was successfully delivered, False otherwise

        Raises:
            AlertDeliveryError: If all delivery attempts fail
        """
        if not self.webhook_url:
            logger.warning(
                "Alert webhook URL is not configured. Skipping alert delivery."
            )
            return False

        max_attempts = (
            retry_attempts if retry_attempts is not None else self.max_retry_attempts
        )
        payload = self.format_alert_payload(alert_data)
        headers = self.prepare_headers(additional_headers)

        safe_endpoint = _safe_endpoint_for_logs(self.webhook_url)
        logger.info("Sending alert to %s", safe_endpoint)

        max_attempts = max(1, max_attempts)
        max_retries = max_attempts - 1
        try:
            async with AsyncHttpClient(
                timeout=self.timeout,
                verify=self.verify_ssl,
                retry_enabled=True,
                max_retries=max_retries,
            ) as client:
                response = await client.async_post_json(
                    self.webhook_url,
                    payload,
                    headers=headers,
                    timeout=self.timeout,
                    max_retries=max_retries,
                )

            response.raise_for_status()

            logger.info(
                "Alert delivered successfully to %s (Status: %s)",
                safe_endpoint,
                response.status_code,
            )
            return True

        except httpx.TimeoutException:
            logger.error(
                "Timeout delivering alert to %s (attempts %s)",
                safe_endpoint,
                max_attempts,
            )

        except httpx.HTTPStatusError as e:
            response_body = (
                e.response.text[:500] if hasattr(e.response, "text") else None
            )
            logger.error(
                "HTTP error delivering alert to %s (Status: %s, attempts %s). Response: %s",
                safe_endpoint,
                e.response.status_code,
                max_attempts,
                response_body,
            )

        except httpx.RequestError as e:
            logger.error(
                "Request error delivering alert to %s (attempts %s): %s",
                safe_endpoint,
                max_attempts,
                e,
            )

        except Exception as e:
            logger.error(
                "Unexpected error delivering alert to %s (attempts %s): %s",
                safe_endpoint,
                max_attempts,
                e,
            )

        logger.error("Failed to deliver alert after %s attempts", max_attempts)
        return False

    async def send_test_alert(self) -> bool:
        """Send a test alert to verify the webhook configuration.

        Returns:
            bool: True if the test alert was successfully delivered
        """
        test_data = {
            "alert_type": "test_alert",
            "message": "Test alert from AI Defense System",
            "severity": "info",
            "details": {
                "test": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

        logger.info("Sending test alert")
        return await self.send_alert(test_data)


class MultiChannelAlertSender:
    """Manages multiple alert channels and sends alerts to all configured channels.

    This class allows for sending alerts to multiple webhooks or alert services
    simultaneously, providing redundancy and multi-channel notification capabilities.

    Usage Example:
        sender = MultiChannelAlertSender()
        sender.add_channel("slack", HttpAlertSender("https://hooks.example.com/..."))
        sender.add_channel("teams", HttpAlertSender("https://outlook.office.com/..."))

        success_count = await sender.send_alert_to_all({
            "message": "Critical alert",
            "severity": "high"
        })
    """

    def __init__(self):
        """Initialize the multi-channel alert sender."""
        self.channels: Dict[str, HttpAlertSender] = {}

    def add_channel(self, name: str, sender: HttpAlertSender) -> None:
        """Add an alert channel.

        Args:
            name: Unique name for the channel
            sender: HttpAlertSender instance for this channel
        """
        self.channels[name] = sender
        logger.debug(f"Added alert channel: {name}")

    def remove_channel(self, name: str) -> bool:
        """Remove an alert channel.

        Args:
            name: Name of the channel to remove

        Returns:
            bool: True if the channel was removed, False if it didn't exist
        """
        if name in self.channels:
            del self.channels[name]
            logger.debug(f"Removed alert channel: {name}")
            return True
        return False

    def get_channel_names(self) -> List[str]:
        """Get list of configured channel names.

        Returns:
            List of channel names
        """
        return list(self.channels.keys())

    async def send_alert_to_all(self, alert_data: Dict[str, Any]) -> int:
        """Send an alert to all configured channels.

        Args:
            alert_data: Alert data to send to all channels

        Returns:
            int: Number of channels that successfully received the alert
        """
        if not self.channels:
            logger.warning("No alert channels configured")
            return 0

        logger.info(f"Sending alert to {len(self.channels)} channels")
        success_count = 0

        for channel_name, sender in self.channels.items():
            try:
                success = await sender.send_alert(alert_data)
                if success:
                    success_count += 1
                    logger.debug(f"Alert sent successfully to channel: {channel_name}")
                else:
                    logger.warning(f"Failed to send alert to channel: {channel_name}")
            except Exception as e:
                logger.error(f"Error sending alert to channel {channel_name}: {e}")

        logger.info(
            f"Alert delivery completed: {success_count}/{len(self.channels)} channels successful"
        )
        return success_count

    async def send_test_alerts(self) -> Dict[str, bool]:
        """Send test alerts to all configured channels.

        Returns:
            Dict mapping channel names to success status
        """
        results = {}
        for channel_name, sender in self.channels.items():
            try:
                success = await sender.send_test_alert()
                results[channel_name] = success
            except Exception as e:
                logger.error(f"Error sending test alert to channel {channel_name}: {e}")
                results[channel_name] = False

        return results

"""Slack-specific alert formatting and sending functionality.

This module implements Slack-specific alert formatting and delivery using the Slack
webhook API. It extends the generic HTTP alert functionality to provide rich Slack
message formatting with emoji, markdown, and structured attachments.

The module handles Slack-specific requirements including:
- Rich text formatting with Slack markdown
- Emoji integration for visual alert categorization
- Structured message attachments for detailed information
- Color coding for different alert severities
- Proper handling of Slack webhook response formats

Usage Example:
    # Ensure the ALERT_SLACK_WEBHOOK_URL environment variable is set
    slack_sender = SlackAlertSender()

    await slack_sender.send_slack_alert({
        "reason": "High Combined Score (0.95)",
        "ip": "192.168.1.1",
        "user_agent": "suspicious-bot/1.0",
        "timestamp_utc": "2024-01-01T12:00:00Z",
        "details": {"path": "/admin", "method": "POST"}
    })
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import CONFIG
from .http_alert import AlertDeliveryError, HttpAlertSender

logger = logging.getLogger(__name__)


class SlackAlertSender(HttpAlertSender):
    """Slack-specific alert sender with rich message formatting.

    This class extends the generic HttpAlertSender to provide Slack-specific
    formatting including emoji, markdown, colors, and structured attachments.
    It handles the nuances of Slack's webhook API and message format requirements.

    Attributes:
        channel (str): Optional Slack channel override (if not set in webhook URL)
        username (str): Username for the bot sending messages
        icon_emoji (str): Emoji icon for the bot
        color_mapping (Dict[str, str]): Mapping of alert severities to Slack colors
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        timeout: float = 10.0,
        channel: Optional[str] = None,
        username: str = "AI Defense Bot",
        icon_emoji: str = ":shield:",
        verify_ssl: bool = True,
    ):
        """Initialize the Slack alert sender.

        Args:
            webhook_url: Slack webhook URL for sending messages. If omitted,
                the value is read from the ALERT_SLACK_WEBHOOK_URL environment
                variable or the shared configuration.
            timeout: Timeout in seconds for HTTP requests
            channel: Optional channel override (e.g., "#alerts")
            username: Display name for the bot in Slack
            icon_emoji: Emoji icon for the bot (e.g., ":shield:")
            verify_ssl: Whether to verify SSL certificates
        """
        if webhook_url is None:
            webhook_url = (
                os.getenv("ALERT_SLACK_WEBHOOK_URL") or CONFIG.ALERT_SLACK_WEBHOOK_URL
            )
        if not webhook_url:
            raise ValueError(
                "Slack webhook URL not configured. Set ALERT_SLACK_WEBHOOK_URL."
            )

        # Set Slack-specific default headers
        super().__init__(
            webhook_url=webhook_url,
            timeout=timeout,
            default_headers={"Content-Type": "application/json"},
            verify_ssl=verify_ssl,
        )

        self.channel = channel
        self.username = username
        self.icon_emoji = icon_emoji

        # Color mapping for different alert severities
        self.color_mapping = {
            "critical": "#FF0000",  # Red
            "high": "#FF6600",  # Orange
            "medium": "#FFCC00",  # Yellow
            "low": "#00CC00",  # Green
            "info": "#0099FF",  # Blue
            "warning": "#FF9900",  # Orange-yellow
        }

        # Emoji mapping for different alert types and reasons
        self.emoji_mapping = {
            "high_combined": ":rotating_light:",
            "heuristic": ":warning:",
            "llm": ":robot_face:",
            "external_api": ":satellite:",
            "honeypot": ":honey_pot:",
            "ip_reputation": ":globe_with_meridians:",
            "scan": ":mag:",
            "scraping": ":spider:",
            "crawler": ":robot_face:",
            "default": ":shield:",
        }

    def get_alert_emoji(self, reason: str, alert_type: str = "") -> str:
        """Get appropriate emoji for the alert based on reason and type.

        Args:
            reason: Alert reason (e.g., "High Combined Score")
            alert_type: Optional alert type for more specific emoji selection

        Returns:
            str: Emoji code suitable for Slack messages
        """
        reason_lower = reason.lower()

        # Check for specific patterns in the reason
        for key, emoji in self.emoji_mapping.items():
            if key in reason_lower:
                return emoji

        # Default emoji
        return self.emoji_mapping["default"]

    def format_slack_message_text(self, alert_data: Dict[str, Any]) -> str:
        """Format the main message text for Slack with rich formatting.

        Args:
            alert_data: Alert data including reason, IP, user agent, etc.

        Returns:
            str: Formatted Slack message text with markdown
        """
        reason = alert_data.get("reason", "Unknown reason")

        # Extract IP and user agent from either top level or details
        ip = alert_data.get("ip", "N/A")
        user_agent = alert_data.get("user_agent", "N/A")

        # If not found at top level, check in details
        details = alert_data.get("details", {})
        if isinstance(details, dict):
            if ip == "N/A":
                ip = details.get("ip", "N/A")
            if user_agent == "N/A":
                user_agent = details.get("user_agent", "N/A")

        timestamp_utc = alert_data.get(
            "timestamp_utc", datetime.now(timezone.utc).isoformat()
        )

        # Get appropriate emoji for this alert
        emoji = self.get_alert_emoji(reason)

        # Format the main message
        message = (
            f"{emoji} *AI Defense Alert*\n"
            f"> *Reason:* {reason}\n"
            f"> *IP Address:* `{ip}`\n"
            f"> *User Agent:* `{user_agent}`\n"
            f"> *Timestamp (UTC):* {timestamp_utc}"
        )

        # Add additional details if available
        details = alert_data.get("details", {})
        if isinstance(details, dict):
            if details.get("path"):
                message += f"\n> *Path:* `{details['path']}`"
            if details.get("method"):
                message += f"\n> *Method:* `{details['method']}`"
            if details.get("score"):
                message += f"\n> *Score:* `{details['score']}`"

        return message

    def format_slack_attachment(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format a detailed Slack attachment for the alert.

        Args:
            alert_data: Alert data to format into an attachment

        Returns:
            Dict: Slack attachment object with fields and formatting
        """
        reason = alert_data.get("reason", "Unknown reason")
        details = alert_data.get("details", {})

        # Determine color based on alert severity or reason
        color = self.color_mapping.get("medium")  # Default color
        reason_lower = reason.lower()
        if any(keyword in reason_lower for keyword in ["critical", "high combined"]):
            color = self.color_mapping.get("critical")
        elif any(keyword in reason_lower for keyword in ["high", "heuristic"]):
            color = self.color_mapping.get("high")
        elif "honeypot" in reason_lower:
            color = self.color_mapping.get("warning")

        # Build attachment fields
        fields = []

        # Add basic alert information
        if alert_data.get("event_type"):
            fields.append(
                {
                    "title": "Event Type",
                    "value": alert_data["event_type"],
                    "short": True,
                }
            )

        # Add detail fields from the details dictionary
        if isinstance(details, dict):
            for key, value in details.items():
                if (
                    key not in ["ip", "user_agent"] and value
                ):  # Skip already displayed fields
                    # Format field title (convert snake_case to Title Case)
                    title = key.replace("_", " ").title()

                    # Format value appropriately
                    if isinstance(value, (dict, list)):
                        value_str = str(value)
                        if len(value_str) > 100:
                            value_str = value_str[:97] + "..."
                    else:
                        value_str = str(value)

                    fields.append(
                        {
                            "title": title,
                            "value": value_str,
                            "short": len(value_str) < 30,
                        }
                    )

        attachment = {
            "color": color,
            "fields": fields,
            "footer": "AI Scraping Defense System",
            "footer_icon": "https://github.com/rhamenator/ai-scraping-defense/raw/main/docs/ai-defense-icon.png",
            "ts": int(datetime.now(timezone.utc).timestamp()),
        }

        return attachment

    def format_alert_payload(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format alert data into Slack webhook payload.

        Args:
            alert_data: Alert data from the AI Defense System

        Returns:
            Dict: Slack webhook payload with rich formatting
        """
        # Format the main message text
        message_text = self.format_slack_message_text(alert_data)

        # Build the base payload
        payload = {
            "text": message_text,
            "username": self.username,
            "icon_emoji": self.icon_emoji,
        }

        # Add channel if specified
        if self.channel:
            payload["channel"] = self.channel

        # Add detailed attachment for rich formatting
        attachment = self.format_slack_attachment(alert_data)
        if attachment["fields"]:  # Only add attachment if it has content
            payload["attachments"] = [attachment]

        logger.debug(
            f"Formatted Slack payload with {len(attachment.get('fields', []))} detail fields"
        )
        return payload

    async def send_slack_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send a Slack alert with AI Defense System specific formatting.

        This method provides a convenient interface for sending alerts with
        the expected data structure from the AI webhook system.

        Args:
            alert_data: Dict containing:
                - reason (str): Alert reason/trigger
                - details (dict): Request details including ip, user_agent, etc.
                - timestamp_utc (str): UTC timestamp
                - event_type (str, optional): Type of event

        Returns:
            bool: True if alert was sent successfully
        """
        # Extract IP and user agent from details for top-level access
        details = alert_data.get("details", {})
        formatted_data = alert_data.copy()

        if isinstance(details, dict):
            formatted_data["ip"] = details.get("ip", "N/A")
            formatted_data["user_agent"] = details.get("user_agent", "N/A")

        logger.info(f"Sending Slack alert for IP: {formatted_data.get('ip', 'N/A')}")

        try:
            success = await self.send_alert(formatted_data)
            if success:
                logger.info(
                    f"Slack alert sent successfully for IP {formatted_data.get('ip', 'N/A')}"
                )
            return success
        except AlertDeliveryError as e:
            logger.error(f"Failed to deliver Slack alert: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Slack alert: {e}")
            return False

    async def send_test_slack_alert(self) -> bool:
        """Send a test Slack alert to verify configuration.

        Returns:
            bool: True if the test alert was sent successfully
        """
        test_alert_data = {
            "reason": "Test Alert - System Check",
            "event_type": "test_alert",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "details": {
                "ip": "127.0.0.1",
                "user_agent": "AI-Defense-Test/1.0",
                "path": "/test",
                "method": "GET",
                "test_mode": True,
                "score": "0.1",
            },
        }

        logger.info("Sending Slack test alert")
        return await self.send_slack_alert(test_alert_data)


def create_slack_alert_sender(
    webhook_url: Optional[str] = None, **kwargs
) -> SlackAlertSender:
    """Factory function to create a SlackAlertSender instance.

    Args:
        webhook_url: Slack webhook URL. When not provided, the value is
            obtained from the ALERT_SLACK_WEBHOOK_URL environment variable or
            the shared configuration.
        **kwargs: Additional configuration options for SlackAlertSender

    Returns:
        SlackAlertSender: Configured Slack alert sender instance
    """
    if webhook_url is None:
        webhook_url = (
            os.getenv("ALERT_SLACK_WEBHOOK_URL") or CONFIG.ALERT_SLACK_WEBHOOK_URL
        )
    if not webhook_url:
        raise ValueError(
            "Slack webhook URL not configured. Set ALERT_SLACK_WEBHOOK_URL."
        )
    return SlackAlertSender(webhook_url=webhook_url, **kwargs)

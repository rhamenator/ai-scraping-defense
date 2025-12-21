"""Alert notification system for AI scraping detection."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages alert notifications for detected AI scraping activities."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: Optional[str] = None,
        alert_recipients: Optional[List[str]] = None,
    ):
        """
        Initialize the AlertManager.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            smtp_user: SMTP username
            smtp_password: SMTP password
            from_email: Email address to send alerts from
            alert_recipients: List of email addresses to receive alerts
        """
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER", "")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD", "")
        self.from_email = from_email or os.getenv("ALERT_FROM_EMAIL", "alerts@example.com")
        self.alert_recipients = alert_recipients or self._parse_recipients(
            os.getenv("ALERT_RECIPIENTS", "")
        )

    @staticmethod
    def _parse_recipients(recipients_str: str) -> List[str]:
        """Parse comma-separated recipient email addresses."""
        if not recipients_str:
            return []
        return [email.strip() for email in recipients_str.split(",") if email.strip()]

    def send_alert(
        self,
        subject: str,
        body: str,
        alert_level: str = "INFO",
        detection_data: Optional[Dict] = None,
    ) -> bool:
        """
        Send an alert email.

        Args:
            subject: Email subject
            body: Email body content
            alert_level: Alert severity level (INFO, WARNING, CRITICAL)
            detection_data: Optional dictionary containing detection details

        Returns:
            bool: True if alert was sent successfully, False otherwise
        """
        if not self.alert_recipients:
            logger.warning("No alert recipients configured, skipping alert")
            return False

        try:
            message = self._create_message(subject, body, alert_level, detection_data)
            self._send_email(message)
            logger.info("Alert sent successfully: %s", subject)
            return True
        except Exception as e:
            logger.error("Failed to send alert: %s", e, exc_info=True)
            return False

    def _create_message(
        self,
        subject: str,
        body: str,
        alert_level: str,
        detection_data: Optional[Dict],
    ) -> MIMEMultipart:
        """Create the email message."""
        message = MIMEMultipart("alternative")
        message["Subject"] = f"[{alert_level}] {subject}"
        message["From"] = self.from_email
        message["To"] = ", ".join(self.alert_recipients)

        # Create plain text and HTML versions
        text_body = self._format_text_body(body, detection_data)
        html_body = self._format_html_body(body, alert_level, detection_data)

        message.attach(MIMEText(text_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        return message

    def _format_text_body(self, body: str, detection_data: Optional[Dict]) -> str:
        """Format plain text email body."""
        text_parts = [body]

        if detection_data:
            text_parts.append("\n\nDetection Details:")
            text_parts.append("-" * 40)
            for key, value in detection_data.items():
                text_parts.append(f"{key}: {value}")

        text_parts.append(f"\n\nTimestamp: {datetime.utcnow().isoformat()}")
        return "\n".join(text_parts)

    def _format_html_body(
        self, body: str, alert_level: str, detection_data: Optional[Dict]
    ) -> str:
        """Format HTML email body."""
        level_colors = {
            "INFO": "#3498db",
            "WARNING": "#f39c12",
            "CRITICAL": "#e74c3c",
        }
        color = level_colors.get(alert_level, "#3498db")

        html_parts = [
            "<html><body>",
            f'<div style="font-family: Arial, sans-serif; max-width: 600px;">',
            f'<div style="background-color: {color}; color: white; padding: 15px; border-radius: 5px;">',
            f"<h2>{alert_level} Alert</h2>",
            "</div>",
            f'<div style="padding: 20px; background-color: #f8f9fa; margin-top: 10px;">',
            f"<p>{body}</p>",
        ]

        if detection_data:
            html_parts.append("<h3>Detection Details</h3>")
            html_parts.append("<table style='width: 100%; border-collapse: collapse;'>")
            for key, value in detection_data.items():
                html_parts.append(
                    f"<tr style='border-bottom: 1px solid #dee2e6;'>"
                    f"<td style='padding: 8px; font-weight: bold;'>{key}</td>"
                    f"<td style='padding: 8px;'>{value}</td></tr>"
                )
            html_parts.append("</table>")

        html_parts.append(
            f"<p style='margin-top: 20px; color: #6c757d; font-size: 0.9em;'>"
            f"Timestamp: {datetime.utcnow().isoformat()}</p>"
        )
        html_parts.append("</div></div></body></html>")

        return "".join(html_parts)

    def _send_email(self, message: MIMEMultipart) -> None:
        """Send the email message via SMTP."""
        smtp_conn = None
        try:
            # Connect to SMTP server
            if self.smtp_port == 465:
                smtp_conn = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                smtp_conn = smtplib.SMTP(self.smtp_host, self.smtp_port)
                if self.smtp_port == 587:
                    smtp_conn.starttls()

            # Authenticate if credentials are provided
            if self.smtp_user and self.smtp_password:
                smtp_conn.login(self.smtp_user, self.smtp_password)

            # Send the email
            smtp_conn.send_message(message)

        finally:
            # Clean up SMTP connection
            if smtp_conn:
                try:
                    smtp_conn.quit()
                except Exception as e:  # pragma: no cover - cleanup failure
                    logger.debug("Failed to quit SMTP connection: %s", e)

    def send_detection_alert(
        self,
        ip_address: str,
        user_agent: str,
        confidence_score: float,
        request_path: str,
        detection_reason: str,
    ) -> bool:
        """
        Send an alert for AI scraping detection.

        Args:
            ip_address: IP address of the detected scraper
            user_agent: User agent string
            confidence_score: Detection confidence score (0-1)
            request_path: Request path that triggered detection
            detection_reason: Reason for detection

        Returns:
            bool: True if alert was sent successfully
        """
        alert_level = "CRITICAL" if confidence_score >= 0.9 else "WARNING"

        subject = f"AI Scraping Detected from {ip_address}"
        body = (
            f"Potential AI scraping activity has been detected.\n\n"
            f"The system has identified suspicious activity that matches "
            f"known AI scraping patterns with a confidence score of "
            f"{confidence_score:.2%}."
        )

        detection_data = {
            "IP Address": ip_address,
            "User Agent": user_agent,
            "Confidence Score": f"{confidence_score:.2%}",
            "Request Path": request_path,
            "Detection Reason": detection_reason,
        }

        return self.send_alert(subject, body, alert_level, detection_data)

    def send_rate_limit_alert(
        self, ip_address: str, request_count: int, time_window: int
    ) -> bool:
        """
        Send an alert for rate limit violations.

        Args:
            ip_address: IP address exceeding rate limits
            request_count: Number of requests in the time window
            time_window: Time window in seconds

        Returns:
            bool: True if alert was sent successfully
        """
        subject = f"Rate Limit Exceeded by {ip_address}"
        body = (
            f"An IP address has exceeded the configured rate limits.\n\n"
            f"This may indicate aggressive scraping or a denial of service attempt."
        )

        detection_data = {
            "IP Address": ip_address,
            "Request Count": str(request_count),
            "Time Window": f"{time_window} seconds",
            "Average Rate": f"{request_count / time_window:.2f} requests/second",
        }

        return self.send_alert(subject, body, "WARNING", detection_data)

    def send_system_alert(self, message: str, alert_level: str = "INFO") -> bool:
        """
        Send a general system alert.

        Args:
            message: Alert message
            alert_level: Alert severity level

        Returns:
            bool: True if alert was sent successfully
        """
        subject = "AI Scraping Defense System Alert"
        return self.send_alert(subject, message, alert_level)

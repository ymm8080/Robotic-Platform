"""Email Gateway - Send alert notifications via SMTP."""
import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .config import settings
from .models import NotificationRequest

logger = logging.getLogger(__name__)


class EmailGateway:
    """Sends email notifications via SMTP/Exchange."""

    async def send(
        self,
        notification: NotificationRequest,
        recipients: list[str],
        subject: str,
        html_body: str,
    ) -> dict:
        """Send email to recipients asynchronously.

        Returns dict with status and message_id.
        """
        if not settings.SMTP_HOST:
            logger.warning("[Email] SMTP not configured, skipping")
            return {"status": "skipped", "message_id": None, "error": "SMTP not configured"}

        if not recipients:
            logger.warning("[Email] No recipients specified")
            return {"status": "skipped", "message_id": None, "error": "no recipients"}

        return await asyncio.to_thread(
            self._send_sync, notification, recipients, subject, html_body
        )

    def _send_sync(
        self,
        notification: NotificationRequest,
        recipients: list[str],
        subject: str,
        html_body: str,
    ) -> dict:
        """Synchronous SMTP send (runs in thread pool)."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.SMTP_FROM_ADDR or settings.SMTP_USER
            msg["To"] = ", ".join(recipients)

            # Plain text fallback
            text_body = (
                f"{notification.title}\n\n"
                f"Priority: {notification.priority}\n"
                f"Target: {notification.target.target_type.value} {notification.target.target_id}\n"
                f"Detail: {notification.content}\n"
                f"Alert ID: {notification.alert_id}\n"
            )
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))

            # Connect and send
            if settings.SMTP_USE_TLS:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)

            password = settings.smtp_password
            if settings.SMTP_USER and password:
                server.login(settings.SMTP_USER, password)

            server.sendmail(
                settings.SMTP_FROM_ADDR or settings.SMTP_USER,
                recipients,
                msg.as_string(),
            )
            server.quit()

            message_id = f"email_{notification.alert_id}_{int(__import__('time').time())}"
            logger.info("[Email] Sent to %s: %s", recipients, subject)
            return {"status": "sent", "message_id": message_id}

        except smtplib.SMTPException as e:
            logger.error("[Email] SMTP error: %s", e)
            return {"status": "failed", "message_id": None, "error": str(e)}
        except Exception as e:
            logger.error("[Email] Unexpected error: %s", e)
            return {"status": "failed", "message_id": None, "error": str(e)}

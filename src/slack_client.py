"""
Slack webhook client for sending alerts.

Uses incoming webhooks for simplicity. For channel-specific routing,
configure multiple webhook URLs or use the Slack Bot API.
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class SlackMessage:
    """A Slack message to send."""

    channel: str
    text: str
    priority: str = "normal"  # "high", "medium", "normal"


class SlackClient:
    """Client for sending Slack alerts via webhook."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.dry_run = dry_run

        if not self.webhook_url and not self.dry_run:
            logger.warning("SLACK_WEBHOOK_URL not set - alerts will be logged only")

    def send(self, message: SlackMessage) -> bool:
        """
        Send a message to Slack.

        Returns True if successful, False otherwise.
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would send to {message.channel}: {message.text[:100]}...")
            return True

        if not self.webhook_url:
            logger.warning(f"No webhook URL - logging instead: {message.text[:100]}...")
            return False

        try:
            payload = {
                "text": message.text,
                "unfurl_links": False,
                "unfurl_media": False,
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()

            logger.info(f"Sent Slack alert to {message.channel}")
            return True

        except requests.RequestException as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False

    def send_churn_alert(
        self,
        conversation_id: str,
        contact_email: Optional[str],
        issue_type: str,
        source_body_preview: str,
    ) -> bool:
        """Send a churn risk alert."""
        text = (
            f":warning: *Churn Risk Detected*\n"
            f"Customer: {contact_email or 'Unknown'}\n"
            f"Issue Type: {issue_type}\n"
            f"Message: {source_body_preview[:200]}...\n"
            f"<https://app.intercom.com/a/inbox/conversation/{conversation_id}|View in Intercom>"
        )
        return self.send(SlackMessage(
            channel="#churn-alerts",
            text=text,
            priority="high",
        ))

    def send_urgent_alert(
        self,
        conversation_id: str,
        contact_email: Optional[str],
        issue_type: str,
        source_body_preview: str,
    ) -> bool:
        """Send an urgent priority alert."""
        text = (
            f":rotating_light: *Urgent Issue*\n"
            f"Type: {issue_type}\n"
            f"Customer: {contact_email or 'Unknown'}\n"
            f"Message: {source_body_preview[:200]}...\n"
            f"<https://app.intercom.com/a/inbox/conversation/{conversation_id}|View in Intercom>"
        )
        return self.send(SlackMessage(
            channel="#urgent",
            text=text,
            priority="high",
        ))

    def send_frustrated_alert(
        self,
        conversation_id: str,
        contact_email: Optional[str],
        issue_type: str,
        source_body_preview: str,
    ) -> bool:
        """Send a frustrated customer alert."""
        text = (
            f":face_with_symbols_on_mouth: *Frustrated Customer - High Priority*\n"
            f"Type: {issue_type}\n"
            f"Customer: {contact_email or 'Unknown'}\n"
            f"Message: {source_body_preview[:200]}...\n"
            f"<https://app.intercom.com/a/inbox/conversation/{conversation_id}|View in Intercom>"
        )
        return self.send(SlackMessage(
            channel="#support",
            text=text,
            priority="medium",
        ))

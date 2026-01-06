"""
Escalation engine for routing classified conversations.

Evaluates rules against conversations and triggers appropriate actions
(Slack alerts, Shortcut tickets, etc.).
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Load .env file if present
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from .db.models import Conversation
from .db.connection import get_connection
from .slack_client import SlackClient

logger = logging.getLogger(__name__)


@dataclass
class EscalationResult:
    """Result of evaluating escalation rules for a conversation."""

    conversation_id: str
    rules_matched: list[str]
    actions_taken: list[str]
    actions_skipped: list[str]  # Due to deduplication


@dataclass
class Rule:
    """An escalation rule."""

    id: str
    name: str
    priority: int  # Lower = higher priority

    def matches(self, conv: Conversation) -> bool:
        """Check if this rule matches the conversation."""
        raise NotImplementedError

    def action_type(self) -> str:
        """Return the action type for this rule."""
        raise NotImplementedError


class ChurnRiskRule(Rule):
    """R001: Alert on churn risk."""

    def __init__(self):
        super().__init__(id="R001", name="Churn Risk Alert", priority=1)

    def matches(self, conv: Conversation) -> bool:
        return conv.churn_risk is True

    def action_type(self) -> str:
        return "slack_alert"


class UrgentPriorityRule(Rule):
    """R002: Alert on urgent priority."""

    def __init__(self):
        super().__init__(id="R002", name="Urgent Priority", priority=1)

    def matches(self, conv: Conversation) -> bool:
        return conv.priority == "urgent"

    def action_type(self) -> str:
        return "slack_alert"


class FrustratedHighRule(Rule):
    """R003: Alert on frustrated + high priority."""

    def __init__(self):
        super().__init__(id="R003", name="Frustrated + High", priority=1)

    def matches(self, conv: Conversation) -> bool:
        return conv.priority == "high" and conv.sentiment == "frustrated"

    def action_type(self) -> str:
        return "slack_alert"


class BugReportRule(Rule):
    """R004: Create ticket for bug reports."""

    def __init__(self):
        super().__init__(id="R004", name="Bug Report", priority=2)

    def matches(self, conv: Conversation) -> bool:
        return conv.issue_type == "bug_report"

    def action_type(self) -> str:
        return "shortcut_ticket"


class FeatureRequestRule(Rule):
    """R005: Aggregate feature requests."""

    def __init__(self):
        super().__init__(id="R005", name="Feature Request", priority=2)

    def matches(self, conv: Conversation) -> bool:
        return conv.issue_type == "feature_request"

    def action_type(self) -> str:
        return "shortcut_ticket"


# All rules in priority order
ALL_RULES: list[Rule] = [
    ChurnRiskRule(),
    UrgentPriorityRule(),
    FrustratedHighRule(),
    BugReportRule(),
    FeatureRequestRule(),
]


class EscalationEngine:
    """Engine for evaluating and executing escalation rules."""

    def __init__(
        self,
        dry_run: bool = False,
        dedup_window_hours: int = 24,
    ):
        self.dry_run = dry_run
        self.dedup_window = timedelta(hours=dedup_window_hours)
        self.slack = SlackClient(dry_run=dry_run)
        self.rules = ALL_RULES

    def was_already_escalated(self, conversation_id: str, rule_id: str) -> bool:
        """Check if this conversation was already escalated by this rule."""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM escalation_log
                        WHERE conversation_id = %s
                          AND rule_id = %s
                          AND created_at > %s
                        """,
                        (conversation_id, rule_id, datetime.utcnow() - self.dedup_window)
                    )
                    return cur.fetchone() is not None
        except Exception as e:
            logger.warning(f"Failed to check dedup: {e}")
            return False

    def log_escalation(
        self,
        conversation_id: str,
        rule_id: str,
        action_type: str,
        slack_channel: Optional[str] = None,
        shortcut_story_id: Optional[str] = None,
    ) -> None:
        """Log an escalation action."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would log escalation: {conversation_id} -> {rule_id}")
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO escalation_log
                            (conversation_id, rule_id, action_type, slack_channel, shortcut_story_id)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (conversation_id, rule_id) DO NOTHING
                        """,
                        (conversation_id, rule_id, action_type, slack_channel, shortcut_story_id)
                    )
        except Exception as e:
            logger.error(f"Failed to log escalation: {e}")

    def execute_slack_alert(self, conv: Conversation, rule: Rule) -> bool:
        """Execute a Slack alert action."""
        source_preview = (conv.source_body or "")[:200]

        if rule.id == "R001":  # Churn risk
            return self.slack.send_churn_alert(
                conversation_id=conv.id,
                contact_email=conv.contact_email,
                issue_type=conv.issue_type,
                source_body_preview=source_preview,
            )
        elif rule.id == "R002":  # Urgent
            return self.slack.send_urgent_alert(
                conversation_id=conv.id,
                contact_email=conv.contact_email,
                issue_type=conv.issue_type,
                source_body_preview=source_preview,
            )
        elif rule.id == "R003":  # Frustrated + high
            return self.slack.send_frustrated_alert(
                conversation_id=conv.id,
                contact_email=conv.contact_email,
                issue_type=conv.issue_type,
                source_body_preview=source_preview,
            )
        else:
            logger.warning(f"Unknown Slack rule: {rule.id}")
            return False

    def execute_shortcut_ticket(self, conv: Conversation, rule: Rule) -> bool:
        """Execute a Shortcut ticket creation action."""
        # Shortcut integration deferred - log for now
        logger.info(
            f"[SHORTCUT] Would create ticket for {conv.id}: "
            f"type={conv.issue_type}, priority={conv.priority}"
        )
        return True

    def evaluate(self, conv: Conversation) -> EscalationResult:
        """
        Evaluate all rules against a conversation and execute matching actions.

        Returns an EscalationResult with details of what happened.
        """
        result = EscalationResult(
            conversation_id=conv.id,
            rules_matched=[],
            actions_taken=[],
            actions_skipped=[],
        )

        for rule in self.rules:
            if not rule.matches(conv):
                continue

            result.rules_matched.append(rule.id)

            # Check deduplication
            if self.was_already_escalated(conv.id, rule.id):
                result.actions_skipped.append(f"{rule.id} (already escalated)")
                continue

            # Execute action
            action_type = rule.action_type()
            success = False

            if action_type == "slack_alert":
                success = self.execute_slack_alert(conv, rule)
            elif action_type == "shortcut_ticket":
                success = self.execute_shortcut_ticket(conv, rule)

            if success:
                result.actions_taken.append(f"{rule.id}: {action_type}")
                self.log_escalation(
                    conversation_id=conv.id,
                    rule_id=rule.id,
                    action_type=action_type,
                    slack_channel=getattr(rule, 'channel', None),
                )

        return result

    def evaluate_batch(self, conversations: list[Conversation]) -> list[EscalationResult]:
        """Evaluate rules for a batch of conversations."""
        results = []
        for conv in conversations:
            result = self.evaluate(conv)
            results.append(result)

            if result.actions_taken:
                logger.info(
                    f"Conversation {conv.id}: {len(result.actions_taken)} actions taken"
                )

        return results


def get_unescalated_conversations(
    limit: int = 100,
    since_hours: int = 24,
) -> list[Conversation]:
    """
    Fetch conversations that haven't been evaluated for escalation yet.

    Returns conversations from the last N hours that have no escalation log entries.
    """
    from .db.models import Conversation

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.*
                FROM conversations c
                LEFT JOIN escalation_log e ON c.id = e.conversation_id
                WHERE c.classified_at > NOW() - INTERVAL '%s hours'
                  AND e.id IS NULL
                ORDER BY c.classified_at DESC
                LIMIT %s
                """,
                (since_hours, limit)
            )
            rows = cur.fetchall()

            # Get column names
            columns = [desc[0] for desc in cur.description]

            conversations = []
            for row in rows:
                row_dict = dict(zip(columns, row))
                conv = Conversation(
                    id=row_dict['id'],
                    created_at=row_dict['created_at'],
                    source_body=row_dict.get('source_body'),
                    source_type=row_dict.get('source_type'),
                    source_subject=row_dict.get('source_subject'),
                    contact_email=row_dict.get('contact_email'),
                    contact_id=row_dict.get('contact_id'),
                    issue_type=row_dict['issue_type'],
                    sentiment=row_dict['sentiment'],
                    churn_risk=row_dict['churn_risk'],
                    priority=row_dict['priority'],
                    classifier_version=row_dict.get('classifier_version'),
                )
                conversations.append(conv)

            return conversations


def run_escalation(
    dry_run: bool = False,
    limit: int = 100,
) -> dict:
    """
    Run escalation rules on unprocessed conversations.

    Returns a summary of actions taken.
    """
    logger.info("Starting escalation run...")

    conversations = get_unescalated_conversations(limit=limit)
    logger.info(f"Found {len(conversations)} conversations to evaluate")

    if not conversations:
        return {"evaluated": 0, "actions_taken": 0}

    engine = EscalationEngine(dry_run=dry_run)
    results = engine.evaluate_batch(conversations)

    total_actions = sum(len(r.actions_taken) for r in results)
    total_skipped = sum(len(r.actions_skipped) for r in results)

    logger.info("=" * 50)
    logger.info("Escalation run completed!")
    logger.info(f"  Evaluated:      {len(conversations)}")
    logger.info(f"  Actions taken:  {total_actions}")
    logger.info(f"  Actions skipped: {total_skipped} (dedup)")
    logger.info("=" * 50)

    return {
        "evaluated": len(conversations),
        "actions_taken": total_actions,
        "actions_skipped": total_skipped,
    }

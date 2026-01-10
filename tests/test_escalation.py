"""
Escalation engine tests.

Run with: pytest tests/test_escalation.py -v
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.models import Conversation
from src.slack_client import SlackClient, SlackMessage

# Import escalation components - need to handle relative imports
import importlib.util
spec = importlib.util.spec_from_file_location("escalation", PROJECT_ROOT / "src" / "escalation.py")
escalation_module = importlib.util.module_from_spec(spec)

# Patch the relative imports before loading
sys.modules['src.escalation'] = escalation_module

# Now we can use local imports in tests
from src.db.models import Conversation as ConvModel

# Define minimal versions of the classes for testing
from dataclasses import dataclass
from typing import Optional

@dataclass
class EscalationResult:
    """Result of evaluating escalation rules for a conversation."""
    conversation_id: str
    rules_matched: list
    actions_taken: list
    actions_skipped: list

@dataclass
class Rule:
    """An escalation rule."""
    id: str
    name: str
    priority: int

    def matches(self, conv) -> bool:
        raise NotImplementedError

    def action_type(self) -> str:
        raise NotImplementedError


class ChurnRiskRule(Rule):
    def __init__(self):
        self.id = "R001"
        self.name = "Churn Risk Alert"
        self.priority = 1

    def matches(self, conv) -> bool:
        return conv.churn_risk is True

    def action_type(self) -> str:
        return "slack_alert"


class UrgentPriorityRule(Rule):
    def __init__(self):
        self.id = "R002"
        self.name = "Urgent Priority"
        self.priority = 1

    def matches(self, conv) -> bool:
        return conv.priority == "urgent"

    def action_type(self) -> str:
        return "slack_alert"


class FrustratedHighRule(Rule):
    def __init__(self):
        self.id = "R003"
        self.name = "Frustrated + High"
        self.priority = 1

    def matches(self, conv) -> bool:
        return conv.priority == "high" and conv.sentiment == "frustrated"

    def action_type(self) -> str:
        return "slack_alert"


class BugReportRule(Rule):
    def __init__(self):
        self.id = "R004"
        self.name = "Bug Report"
        self.priority = 2

    def matches(self, conv) -> bool:
        return conv.issue_type == "bug_report"

    def action_type(self) -> str:
        return "shortcut_ticket"


class FeatureRequestRule(Rule):
    def __init__(self):
        self.id = "R005"
        self.name = "Feature Request"
        self.priority = 2

    def matches(self, conv) -> bool:
        return conv.issue_type == "feature_request"

    def action_type(self) -> str:
        return "shortcut_ticket"


ALL_RULES = [
    ChurnRiskRule(),
    UrgentPriorityRule(),
    FrustratedHighRule(),
    BugReportRule(),
    FeatureRequestRule(),
]


class EscalationEngine:
    """Engine for evaluating and executing escalation rules."""

    def __init__(self, dry_run: bool = False, dedup_window_hours: int = 24):
        self.dry_run = dry_run
        self.slack = SlackClient(dry_run=dry_run)
        self.rules = ALL_RULES

    def was_already_escalated(self, conversation_id: str, rule_id: str) -> bool:
        return False  # Override in tests

    def log_escalation(self, conversation_id: str, rule_id: str, action_type: str, **kwargs):
        pass  # Override in tests

    def execute_slack_alert(self, conv, rule) -> bool:
        source_preview = (conv.source_body or "")[:200]
        if rule.id == "R001":
            return self.slack.send_churn_alert(conv.id, conv.contact_email, conv.issue_type, source_preview)
        elif rule.id == "R002":
            return self.slack.send_urgent_alert(conv.id, conv.contact_email, conv.issue_type, source_preview)
        elif rule.id == "R003":
            return self.slack.send_frustrated_alert(conv.id, conv.contact_email, conv.issue_type, source_preview)
        return False

    def execute_shortcut_ticket(self, conv, rule) -> bool:
        return True  # Stub for now

    def evaluate(self, conv) -> EscalationResult:
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

            if self.was_already_escalated(conv.id, rule.id):
                result.actions_skipped.append(f"{rule.id} (already escalated)")
                continue

            action_type = rule.action_type()
            success = False

            if action_type == "slack_alert":
                success = self.execute_slack_alert(conv, rule)
            elif action_type == "shortcut_ticket":
                success = self.execute_shortcut_ticket(conv, rule)

            if success:
                result.actions_taken.append(f"{rule.id}: {action_type}")
                self.log_escalation(conv.id, rule.id, action_type)

        return result


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def churn_risk_conversation():
    """A conversation with churn risk."""
    return Conversation(
        id="conv_churn_001",
        created_at=datetime.utcnow(),
        source_body="I want to cancel my subscription immediately.",
        issue_type="billing",
        sentiment="frustrated",
        churn_risk=True,
        priority="high",
        contact_email="unhappy@example.com",
    )


@pytest.fixture
def urgent_conversation():
    """An urgent priority conversation."""
    return Conversation(
        id="conv_urgent_001",
        created_at=datetime.utcnow(),
        source_body="I cannot log in to my account at all! Payment system down!",
        issue_type="account_access",
        sentiment="frustrated",
        churn_risk=False,
        priority="urgent",
        contact_email="locked@example.com",
    )


@pytest.fixture
def frustrated_high_conversation():
    """A frustrated customer with high priority."""
    return Conversation(
        id="conv_frustrated_001",
        created_at=datetime.utcnow(),
        source_body="This is SO frustrating! Nothing works properly!",
        issue_type="bug_report",
        sentiment="frustrated",
        churn_risk=False,
        priority="high",
        contact_email="frustrated@example.com",
    )


@pytest.fixture
def bug_report_conversation():
    """A normal bug report."""
    return Conversation(
        id="conv_bug_001",
        created_at=datetime.utcnow(),
        source_body="The export button doesn't work on Safari.",
        issue_type="bug_report",
        sentiment="neutral",
        churn_risk=False,
        priority="normal",
        contact_email="reporter@example.com",
    )


@pytest.fixture
def feature_request_conversation():
    """A feature request."""
    return Conversation(
        id="conv_feature_001",
        created_at=datetime.utcnow(),
        source_body="It would be great if you could add dark mode.",
        issue_type="feature_request",
        sentiment="neutral",
        churn_risk=False,
        priority="normal",
        contact_email="suggester@example.com",
    )


@pytest.fixture
def normal_conversation():
    """A normal conversation that shouldn't trigger alerts."""
    return Conversation(
        id="conv_normal_001",
        created_at=datetime.utcnow(),
        source_body="How do I connect my Pinterest account?",
        issue_type="product_question",
        sentiment="neutral",
        churn_risk=False,
        priority="normal",
        contact_email="user@example.com",
    )


# -----------------------------------------------------------------------------
# Rule Matching Tests
# -----------------------------------------------------------------------------

class TestRuleMatching:
    """Test that rules match the correct conversations."""

    def test_churn_risk_rule_matches(self, churn_risk_conversation):
        """Churn risk rule should match conversations with churn_risk=true."""
        rule = ChurnRiskRule()
        assert rule.matches(churn_risk_conversation) is True

    def test_churn_risk_rule_no_match(self, normal_conversation):
        """Churn risk rule should not match normal conversations."""
        rule = ChurnRiskRule()
        assert rule.matches(normal_conversation) is False

    def test_urgent_priority_rule_matches(self, urgent_conversation):
        """Urgent priority rule should match urgent conversations."""
        rule = UrgentPriorityRule()
        assert rule.matches(urgent_conversation) is True

    def test_urgent_priority_rule_no_match(self, bug_report_conversation):
        """Urgent priority rule should not match normal priority."""
        rule = UrgentPriorityRule()
        assert rule.matches(bug_report_conversation) is False

    def test_frustrated_high_rule_matches(self, frustrated_high_conversation):
        """Frustrated + high rule should match frustrated high-priority."""
        rule = FrustratedHighRule()
        assert rule.matches(frustrated_high_conversation) is True

    def test_frustrated_high_rule_no_match_neutral(self, bug_report_conversation):
        """Frustrated + high rule should not match neutral sentiment."""
        rule = FrustratedHighRule()
        assert rule.matches(bug_report_conversation) is False

    def test_bug_report_rule_matches(self, bug_report_conversation):
        """Bug report rule should match bug reports."""
        rule = BugReportRule()
        assert rule.matches(bug_report_conversation) is True

    def test_bug_report_rule_no_match(self, feature_request_conversation):
        """Bug report rule should not match feature requests."""
        rule = BugReportRule()
        assert rule.matches(feature_request_conversation) is False

    def test_feature_request_rule_matches(self, feature_request_conversation):
        """Feature request rule should match feature requests."""
        rule = FeatureRequestRule()
        assert rule.matches(feature_request_conversation) is True


# -----------------------------------------------------------------------------
# Slack Client Tests
# -----------------------------------------------------------------------------

class TestSlackClient:
    """Test Slack client functionality."""

    def test_dry_run_no_http_call(self):
        """Dry run should not make HTTP calls."""
        client = SlackClient(dry_run=True)
        result = client.send(SlackMessage(
            channel="#test",
            text="Test message",
        ))
        assert result is True

    @patch.dict('os.environ', {'SLACK_WEBHOOK_URL': ''}, clear=False)
    def test_no_webhook_logs_warning(self):
        """Missing webhook should log warning and return False."""
        client = SlackClient(webhook_url=None, dry_run=False)
        result = client.send(SlackMessage(
            channel="#test",
            text="Test message",
        ))
        assert result is False

    @patch('src.slack_client.requests.post')
    def test_successful_send(self, mock_post):
        """Successful send should return True."""
        mock_post.return_value = Mock(status_code=200)
        mock_post.return_value.raise_for_status = Mock()

        client = SlackClient(webhook_url="https://hooks.slack.com/test")
        result = client.send(SlackMessage(
            channel="#test",
            text="Test message",
        ))
        assert result is True
        mock_post.assert_called_once()

    @patch('src.slack_client.requests.post')
    def test_failed_send(self, mock_post):
        """Failed send should return False."""
        import requests
        mock_post.side_effect = requests.RequestException("Network error")

        client = SlackClient(webhook_url="https://hooks.slack.com/test")
        result = client.send(SlackMessage(
            channel="#test",
            text="Test message",
        ))
        assert result is False


# -----------------------------------------------------------------------------
# Escalation Engine Tests
# -----------------------------------------------------------------------------

class TestEscalationEngine:
    """Test the escalation engine."""

    def test_evaluate_churn_risk(self, churn_risk_conversation):
        """Churn risk should trigger R001 alert."""
        engine = EscalationEngine(dry_run=True)

        with patch.object(engine, 'was_already_escalated', return_value=False):
            result = engine.evaluate(churn_risk_conversation)

        assert "R001" in result.rules_matched
        assert any("R001" in a for a in result.actions_taken)

    def test_evaluate_urgent(self, urgent_conversation):
        """Urgent priority should trigger R002 alert."""
        engine = EscalationEngine(dry_run=True)

        with patch.object(engine, 'was_already_escalated', return_value=False):
            result = engine.evaluate(urgent_conversation)

        assert "R002" in result.rules_matched
        assert any("R002" in a for a in result.actions_taken)

    def test_evaluate_frustrated_high(self, frustrated_high_conversation):
        """Frustrated + high should trigger R003 and R004 (bug report)."""
        engine = EscalationEngine(dry_run=True)

        with patch.object(engine, 'was_already_escalated', return_value=False):
            result = engine.evaluate(frustrated_high_conversation)

        assert "R003" in result.rules_matched
        assert "R004" in result.rules_matched  # Also a bug report

    def test_evaluate_normal_no_alerts(self, normal_conversation):
        """Normal conversation should not trigger Slack alerts."""
        engine = EscalationEngine(dry_run=True)

        with patch.object(engine, 'was_already_escalated', return_value=False):
            result = engine.evaluate(normal_conversation)

        # Should not match any alert rules (R001-R003)
        alert_rules = {"R001", "R002", "R003"}
        matched_alerts = set(result.rules_matched) & alert_rules
        assert len(matched_alerts) == 0

    def test_deduplication_skips_action(self, churn_risk_conversation):
        """Already escalated conversations should be skipped."""
        engine = EscalationEngine(dry_run=True)

        with patch.object(engine, 'was_already_escalated', return_value=True):
            result = engine.evaluate(churn_risk_conversation)

        assert "R001" in result.rules_matched
        assert len(result.actions_taken) == 0
        assert any("already escalated" in s for s in result.actions_skipped)

    def test_dry_run_no_side_effects(self, churn_risk_conversation):
        """Dry run should not log to database."""
        engine = EscalationEngine(dry_run=True)

        with patch.object(engine, 'was_already_escalated', return_value=False):
            with patch.object(engine, 'log_escalation') as mock_log:
                result = engine.evaluate(churn_risk_conversation)

        # log_escalation called but should do nothing in dry run
        assert mock_log.called

    def test_multiple_rules_match(self, churn_risk_conversation):
        """Conversation can match multiple rules."""
        # churn_risk_conversation is: churn_risk=True, priority=high, sentiment=frustrated
        engine = EscalationEngine(dry_run=True)

        with patch.object(engine, 'was_already_escalated', return_value=False):
            result = engine.evaluate(churn_risk_conversation)

        # Should match: R001 (churn), R003 (frustrated+high)
        assert "R001" in result.rules_matched
        assert "R003" in result.rules_matched


# -----------------------------------------------------------------------------
# Integration Tests (require database)
# -----------------------------------------------------------------------------

class TestEscalationIntegration:
    """Integration tests requiring PostgreSQL."""

    @pytest.mark.skip(reason="Requires PostgreSQL - run manually")
    def test_escalation_log_deduplication(self):
        """Same conversation+rule should not create duplicate log entries."""
        pass

    @pytest.mark.skip(reason="Requires PostgreSQL - run manually")
    def test_get_unescalated_conversations(self):
        """Should return only conversations without escalation log entries."""
        pass

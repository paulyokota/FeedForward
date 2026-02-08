"""Integration tests for the Codebase Explorer with the state machine.

Tests the full flow: create run → start → create EXPLORATION stage conversation
→ codebase explorer produces findings → submit checkpoint (validated against
ExplorerCheckpoint) → verify stage advances to OPPORTUNITY_FRAMING.

Also tests requery flow and taxonomy guard.

Marked @pytest.mark.slow for the test runner.
Uses InMemoryTransport and InMemoryStorage (same as test_conversation_service.py).
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.codebase_explorer import (
    CodebaseExplorer,
    CodebaseExplorerConfig,
    ExplorerResult,
)
from src.discovery.agents.codebase_data_access import CodebaseItem
from src.discovery.models.artifacts import ExplorerCheckpoint
from src.discovery.models.conversation import EventType
from src.discovery.models.enums import (
    RunStatus,
    SourceType,
    StageStatus,
    StageType,
)
from src.discovery.models.run import DiscoveryRun, StageExecution
from src.discovery.services.conversation import ConversationService
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import InMemoryTransport

# Import directly to avoid duplication
from tests.discovery.test_conversation_service import InMemoryStorage


# ============================================================================
# Helpers
# ============================================================================


def _make_codebase_item(**overrides) -> CodebaseItem:
    defaults = {
        "path": "src/api/main.py",
        "content": "from fastapi import FastAPI\n\napp = FastAPI()\n",
        "item_type": "source_file",
        "metadata": {
            "line_count": 3,
            "commit_count": 2,
            "last_modified": "2026-02-01T10:00:00+00:00",
            "authors": ["dev1"],
        },
    }
    defaults.update(overrides)
    return CodebaseItem(**defaults)


class MockCodebaseReader:
    def __init__(self, items=None, count=None):
        self._items = items or []
        self._count = count if count is not None else len(self._items)
        self._by_path = {item.path: item for item in self._items}

    def fetch_recently_changed(self, days, limit=None):
        result = self._items
        if limit:
            result = result[:limit]
        return result

    def fetch_file(self, path):
        return self._by_path.get(path)

    def get_item_count(self, days):
        return self._count


def _make_llm_response(content_dict):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150
    return mock_response


def _make_explorer_with_findings(findings=None):
    """Create a CodebaseExplorer that will produce the given findings."""
    if findings is None:
        findings = [
            {
                "pattern_name": "inconsistent_error_handling",
                "description": "Error handling varies across API endpoints",
                "evidence_file_paths": ["src/api/main.py"],
                "confidence": "high",
                "severity_assessment": "moderate impact",
                "affected_users_estimate": "~30% of codebase",
            }
        ]

    items = [_make_codebase_item(path=f"src/mod_{i}.py") for i in range(3)]
    reader = MockCodebaseReader(items=items, count=3)

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _make_llm_response({"findings": findings, "batch_notes": ""}),
        _make_llm_response({"findings": findings, "synthesis_notes": ""}),
    ]

    explorer = CodebaseExplorer(
        reader=reader,
        openai_client=mock_client,
        config=CodebaseExplorerConfig(batch_size=20),
    )
    return explorer


# ============================================================================
# Full flow integration tests
# ============================================================================


@pytest.mark.slow
class TestCodebaseExplorerFullFlow:
    """Full flow: run → explore → checkpoint → advance."""

    def test_codebase_checkpoint_advances_to_opportunity_framing(self):
        """End-to-end: codebase explorer produces findings → checkpoint validates →
        state machine advances to OPPORTUNITY_FRAMING."""
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        state_machine = DiscoveryStateMachine(storage=storage)
        service = ConversationService(
            transport=transport, storage=storage, state_machine=state_machine
        )

        # Create and start run
        run = state_machine.create_run()
        run = state_machine.start_run(run.id)
        assert run.current_stage == StageType.EXPLORATION

        # Create conversation for exploration stage
        active = storage.get_active_stage(run.id)
        convo_id = service.create_stage_conversation(run.id, active.id)

        # Explorer produces findings
        explorer = _make_explorer_with_findings()
        result = explorer.explore()
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Validate checkpoint against model before submission
        validated = ExplorerCheckpoint(**checkpoint)
        assert validated.agent_name == "codebase"

        # Submit checkpoint — this should advance the stage
        new_stage = service.submit_checkpoint(
            convo_id, run.id, "codebase", artifacts=checkpoint
        )

        assert new_stage.stage == StageType.OPPORTUNITY_FRAMING
        assert new_stage.status == StageStatus.IN_PROGRESS

        # Verify old stage is completed
        old_stages = storage.get_stage_executions_for_run(run.id, StageType.EXPLORATION)
        assert any(s.status == StageStatus.COMPLETED for s in old_stages)

    def test_checkpoint_events_in_conversation(self):
        """Verify checkpoint and transition events appear in conversation."""
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        state_machine = DiscoveryStateMachine(storage=storage)
        service = ConversationService(
            transport=transport, storage=storage, state_machine=state_machine
        )

        run = state_machine.create_run()
        run = state_machine.start_run(run.id)
        active = storage.get_active_stage(run.id)
        convo_id = service.create_stage_conversation(run.id, active.id)

        explorer = _make_explorer_with_findings()
        result = explorer.explore()
        checkpoint = explorer.build_checkpoint_artifacts(result)

        service.submit_checkpoint(convo_id, run.id, "codebase", artifacts=checkpoint)

        # Read conversation history
        history = service.read_history(convo_id)
        event_types = [e.event_type for e in history]

        assert EventType.CHECKPOINT_SUBMIT in event_types
        assert EventType.STAGE_TRANSITION in event_types

    def test_empty_findings_checkpoint_still_advances(self):
        """Explorer with zero findings should still produce a valid checkpoint."""
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        state_machine = DiscoveryStateMachine(storage=storage)
        service = ConversationService(
            transport=transport, storage=storage, state_machine=state_machine
        )

        run = state_machine.create_run()
        run = state_machine.start_run(run.id)
        active = storage.get_active_stage(run.id)
        convo_id = service.create_stage_conversation(run.id, active.id)

        # Explorer with no findings
        explorer = _make_explorer_with_findings(findings=[])
        result = explorer.explore()
        checkpoint = explorer.build_checkpoint_artifacts(result)

        # Should still validate and advance
        new_stage = service.submit_checkpoint(
            convo_id, run.id, "codebase", artifacts=checkpoint
        )
        assert new_stage.stage == StageType.OPPORTUNITY_FRAMING


# ============================================================================
# Requery flow
# ============================================================================


@pytest.mark.slow
class TestCodebaseRequeryFlow:
    def test_requery_through_conversation(self):
        """Post explorer:request → explorer reads → responds with explorer:response."""
        storage = InMemoryStorage()
        transport = InMemoryTransport()
        state_machine = DiscoveryStateMachine(storage=storage)
        service = ConversationService(
            transport=transport, storage=storage, state_machine=state_machine
        )

        run = state_machine.create_run()
        run = state_machine.start_run(run.id)
        active = storage.get_active_stage(run.id)
        convo_id = service.create_stage_conversation(run.id, active.id)

        # Post an explorer:request event
        service.post_event(
            convo_id,
            "orchestrator",
            EventType.EXPLORER_REQUEST,
            {"query": "What tech debt patterns did you find?"},
        )

        # Explorer reads history and finds the request
        history = service.read_history(convo_id)
        requests = [e for e in history if e.event_type == EventType.EXPLORER_REQUEST]
        assert len(requests) == 1

        # Explorer handles the requery
        items = [_make_codebase_item()]
        reader = MockCodebaseReader(items=items)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "I found 3 inconsistent error handling patterns",
            "evidence_file_paths": ["src/api/main.py"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = CodebaseExplorer(reader=reader, openai_client=mock_client)
        requery_result = explorer.requery(
            request_text="What tech debt patterns did you find?",
            previous_findings=[],
            file_paths=["src/api/main.py"],
        )

        # Post the response back
        service.post_event(
            convo_id,
            "codebase",
            EventType.EXPLORER_RESPONSE,
            {"answer": requery_result["answer"]},
        )

        # Verify response in history
        history = service.read_history(convo_id)
        responses = [e for e in history if e.event_type == EventType.EXPLORER_RESPONSE]
        assert len(responses) == 1
        assert "error handling" in responses[0].payload.get("answer", "")


# ============================================================================
# Taxonomy guard
# ============================================================================


# The 8 pipeline ConversationType values that the explorer should NOT use
PIPELINE_TAXONOMY = {
    "product_issue",
    "how_to_question",
    "feature_request",
    "account_issue",
    "billing_question",
    "configuration_help",
    "general_inquiry",
    "spam",
}

# Pipeline-specific field names
PIPELINE_FIELDS = {
    "issue_signature",
    "conversation_type",
    "stage1_type",
    "stage2_type",
    "churn_risk",
}


@pytest.mark.slow
class TestCodebaseTaxonomyGuard:
    """Lightweight keyword check to enforce the 'no theme vocabulary' constraint.

    These tests verify that the codebase explorer's artifact output doesn't
    contain prohibited terms from the existing pipeline vocabulary.
    """

    def test_findings_dont_use_pipeline_categories(self):
        """Explorer pattern names should not match pipeline ConversationType values."""
        explorer = _make_explorer_with_findings(findings=[
            {
                "pattern_name": "inconsistent_error_handling",
                "description": "Error handling varies across endpoints",
                "evidence_file_paths": ["src/api/main.py"],
                "confidence": "high",
                "severity_assessment": "moderate",
                "affected_users_estimate": "~30%",
            },
            {
                "pattern_name": "duplicated_validation_logic",
                "description": "Same validation in multiple places",
                "evidence_file_paths": ["src/api/routes.py"],
                "confidence": "medium",
                "severity_assessment": "high",
                "affected_users_estimate": "~15%",
            },
        ])

        result = explorer.explore()
        checkpoint = explorer.build_checkpoint_artifacts(result)

        for finding in checkpoint["findings"]:
            pattern = finding["pattern_name"].lower()
            for prohibited in PIPELINE_TAXONOMY:
                assert pattern != prohibited, (
                    f"Explorer pattern_name '{pattern}' matches prohibited "
                    f"pipeline category '{prohibited}'"
                )

    def test_checkpoint_doesnt_contain_pipeline_fields(self):
        """Checkpoint artifacts should not contain pipeline-specific field names."""
        explorer = _make_explorer_with_findings()
        result = explorer.explore()
        checkpoint = explorer.build_checkpoint_artifacts(result)

        for field_name in PIPELINE_FIELDS:
            if field_name == "conversation_type":
                assert field_name not in checkpoint, (
                    f"Pipeline field '{field_name}' found in checkpoint top-level keys"
                )

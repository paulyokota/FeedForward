"""Integration tests for the Research Explorer with the state machine.

Tests the full flow: create run -> start -> create EXPLORATION stage conversation
-> research explorer produces findings -> submit checkpoint (validated against
ExplorerCheckpoint) -> verify stage advances to OPPORTUNITY_FRAMING.

Also tests requery flow, taxonomy guard, and SourceType.RESEARCH evidence.

Marked @pytest.mark.slow for the test runner.
Uses InMemoryTransport and InMemoryStorage (same as test_conversation_service.py).
"""

import json
from unittest.mock import MagicMock

import pytest

from src.discovery.agents.base import ExplorerResult
from src.discovery.agents.research_data_access import ResearchItem, ResearchReader
from src.discovery.agents.research_explorer import (
    ResearchExplorer,
    ResearchExplorerConfig,
)
from src.discovery.models.artifacts import ExplorerCheckpoint
from src.discovery.models.conversation import EventType
from src.discovery.models.enums import (
    SourceType,
    StageStatus,
    StageType,
)
from src.discovery.services.conversation import ConversationService
from src.discovery.services.state_machine import DiscoveryStateMachine
from src.discovery.services.transport import InMemoryTransport

# Import directly to avoid duplication
from tests.discovery.test_conversation_service import InMemoryStorage


# ============================================================================
# Helpers
# ============================================================================


def _make_llm_response(content_dict):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(content_dict)
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150
    return mock_response


def _make_research_item(path="docs/test.md", content="# Test\nContent", bucket="general"):
    return ResearchItem(
        path=path,
        content=content,
        bucket=bucket,
        metadata={
            "char_count": len(content),
            "line_count": content.count("\n") + 1,
            "title": "Test",
        },
    )


def _make_explorer_with_findings(findings=None):
    """Create a ResearchExplorer that will produce the given findings."""
    if findings is None:
        findings = [
            {
                "pattern_name": "unresolved_migration_decision",
                "description": "Architecture docs reference unresolved DB migration strategy",
                "evidence_doc_paths": ["docs/architecture.md"],
                "confidence": "high",
                "severity_assessment": "moderate impact on velocity",
                "affected_users_estimate": "engineering team",
            }
        ]

    items = [
        _make_research_item("docs/architecture.md", "# Arch\nContent", bucket="architecture"),
        _make_research_item("docs/plans/roadmap.md", "# Roadmap\nPlan", bucket="strategy"),
    ]

    reader = MagicMock(spec=ResearchReader)
    reader.fetch_docs.return_value = items
    reader.get_doc_count.return_value = len(items)
    reader.fetch_doc.return_value = None

    mock_client = MagicMock()
    # 2 buckets = 2 batch calls + 1 synthesis
    mock_client.chat.completions.create.side_effect = [
        _make_llm_response({"findings": findings, "batch_notes": ""}),
        _make_llm_response({"findings": findings, "batch_notes": ""}),
        _make_llm_response({"findings": findings, "synthesis_notes": ""}),
    ]

    explorer = ResearchExplorer(
        reader=reader,
        openai_client=mock_client,
    )
    return explorer


# ============================================================================
# Full flow integration tests
# ============================================================================


@pytest.mark.slow
class TestResearchExplorerFullFlow:
    """Full flow: run -> explore -> checkpoint -> advance."""

    def test_research_checkpoint_advances_to_opportunity_framing(self):
        """End-to-end: research explorer produces findings -> checkpoint validates ->
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
        assert validated.agent_name == "research"

        # Submit checkpoint — this should advance the stage
        new_stage = service.submit_checkpoint(
            convo_id, run.id, "research", artifacts=checkpoint
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

        service.submit_checkpoint(convo_id, run.id, "research", artifacts=checkpoint)

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
            convo_id, run.id, "research", artifacts=checkpoint
        )
        assert new_stage.stage == StageType.OPPORTUNITY_FRAMING


# ============================================================================
# Requery flow
# ============================================================================


@pytest.mark.slow
class TestResearchRequeryFlow:
    def test_requery_through_conversation(self):
        """Post explorer:request -> explorer reads -> responds with explorer:response."""
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
            {"query": "What unresolved decisions did you find?"},
        )

        # Explorer reads history and finds the request
        history = service.read_history(convo_id)
        requests = [e for e in history if e.event_type == EventType.EXPLORER_REQUEST]
        assert len(requests) == 1

        # Explorer handles the requery
        reader = MagicMock(spec=ResearchReader)
        reader.fetch_doc.return_value = _make_research_item(
            "docs/architecture.md", "# Architecture\nDesign decisions here"
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_llm_response({
            "answer": "I found 3 unresolved migration decisions",
            "evidence_doc_paths": ["docs/architecture.md"],
            "confidence": "high",
            "additional_findings": [],
        })

        explorer = ResearchExplorer(reader=reader, openai_client=mock_client)
        requery_result = explorer.requery(
            request_text="What unresolved decisions did you find?",
            previous_findings=[],
            doc_paths=["docs/architecture.md"],
        )

        # Post the response back
        service.post_event(
            convo_id,
            "research",
            EventType.EXPLORER_RESPONSE,
            {"answer": requery_result["answer"]},
        )

        # Verify response in history
        history = service.read_history(convo_id)
        responses = [e for e in history if e.event_type == EventType.EXPLORER_RESPONSE]
        assert len(responses) == 1
        assert "unresolved" in responses[0].payload.get("answer", "")


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
class TestResearchTaxonomyGuard:
    """Lightweight keyword check to enforce the 'no theme vocabulary' constraint."""

    def test_findings_dont_use_pipeline_categories(self):
        """Explorer pattern names should not match pipeline ConversationType values."""
        explorer = _make_explorer_with_findings(findings=[
            {
                "pattern_name": "unresolved_migration_decision",
                "description": "Docs reference undecided strategy",
                "evidence_doc_paths": ["docs/architecture.md"],
                "confidence": "high",
                "severity_assessment": "moderate",
                "affected_users_estimate": "engineering team",
            },
            {
                "pattern_name": "doc_reality_gap",
                "description": "Status docs don't match codebase state",
                "evidence_doc_paths": ["docs/status.md"],
                "confidence": "medium",
                "severity_assessment": "high",
                "affected_users_estimate": "all developers",
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


# ============================================================================
# Evidence source type
# ============================================================================


@pytest.mark.slow
class TestResearchEvidenceSourceType:
    def test_evidence_uses_research_source_type(self):
        """All evidence pointers should use SourceType.RESEARCH."""
        explorer = _make_explorer_with_findings()
        result = explorer.explore()
        checkpoint = explorer.build_checkpoint_artifacts(result)

        for finding in checkpoint["findings"]:
            for evidence in finding["evidence"]:
                assert evidence["source_type"] == SourceType.RESEARCH.value, (
                    f"Expected source_type 'research' but got '{evidence['source_type']}'"
                )

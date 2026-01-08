#!/usr/bin/env python3
"""
Database storage for two-stage classification results.

Stores Stage 1 and Stage 2 classification data in PostgreSQL.
"""
from typing import Dict, Any, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import Json

try:
    from .connection import get_connection
except ImportError:
    # Running as script
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db.connection import get_connection


def store_classification_result(
    conversation_id: str,
    created_at: datetime,
    source_body: str,
    source_type: Optional[str],
    source_url: Optional[str],
    contact_email: Optional[str],
    contact_id: Optional[str],
    stage1_result: Dict[str, Any],
    stage2_result: Optional[Dict[str, Any]] = None,
    support_messages: Optional[list] = None,
    resolution_signal: Optional[Dict[str, Any]] = None,
    story_id: Optional[str] = None
) -> None:
    """
    Store complete two-stage classification result in database.

    Args:
        conversation_id: Intercom conversation ID
        created_at: When conversation was created
        source_body: Customer message text
        source_type: Conversation source type
        source_url: Source URL for context
        contact_email: Customer email
        contact_id: Intercom contact ID
        stage1_result: Stage 1 classification output
        stage2_result: Stage 2 classification output (if available)
        support_messages: List of support responses
        resolution_signal: Resolution pattern detection result
        story_id: Shortcut story/ticket ID (for ground truth clustering analysis)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Extract Stage 1 fields
            stage1_type = stage1_result.get("conversation_type")
            stage1_confidence = stage1_result.get("confidence")
            stage1_routing_priority = stage1_result.get("routing_priority")
            stage1_urgency = stage1_result.get("urgency")
            stage1_auto_response = stage1_result.get("auto_response_eligible", False)
            stage1_routing_team = stage1_result.get("routing_team")

            # Extract Stage 2 fields (if present)
            stage2_type = None
            stage2_confidence = None
            classification_changed = False
            disambiguation_level = None
            stage2_reasoning = None
            support_insights_json = None

            if stage2_result:
                stage2_type = stage2_result.get("conversation_type")
                stage2_confidence = stage2_result.get("confidence")
                classification_changed = stage2_result.get("changed_from_stage_1", False)
                disambiguation_level = stage2_result.get("disambiguation_level")
                stage2_reasoning = stage2_result.get("reasoning")

                # Extract support insights
                support_insights = stage2_result.get("support_insights", {})
                if support_insights:
                    support_insights_json = Json(support_insights)

            # Support context
            has_support_response = bool(support_messages)
            support_response_count = len(support_messages) if support_messages else 0

            # Resolution analysis
            resolution_action = None
            resolution_detected = False
            if resolution_signal and isinstance(resolution_signal, dict):
                resolution_action = resolution_signal.get("action")
                resolution_detected = bool(resolution_action)

            # Legacy fields (set defaults for now - can be populated from existing classifier)
            issue_type = "other"  # Default
            sentiment = "neutral"  # Default
            churn_risk = False
            priority = "normal"  # Default

            # Insert or update conversation
            cur.execute("""
            INSERT INTO conversations (
                id, created_at, classified_at,
                source_body, source_type, source_url,
                contact_email, contact_id,
                issue_type, sentiment, churn_risk, priority,
                stage1_type, stage1_confidence, stage1_routing_priority,
                stage1_urgency, stage1_auto_response_eligible, stage1_routing_team,
                stage2_type, stage2_confidence, classification_changed,
                disambiguation_level, stage2_reasoning,
                has_support_response, support_response_count,
                resolution_action, resolution_detected,
                support_insights,
                story_id,
                classifier_version
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (id) DO UPDATE SET
                classified_at = EXCLUDED.classified_at,
                stage1_type = EXCLUDED.stage1_type,
                stage1_confidence = EXCLUDED.stage1_confidence,
                stage1_routing_priority = EXCLUDED.stage1_routing_priority,
                stage1_urgency = EXCLUDED.stage1_urgency,
                stage1_auto_response_eligible = EXCLUDED.stage1_auto_response_eligible,
                stage1_routing_team = EXCLUDED.stage1_routing_team,
                stage2_type = EXCLUDED.stage2_type,
                stage2_confidence = EXCLUDED.stage2_confidence,
                classification_changed = EXCLUDED.classification_changed,
                disambiguation_level = EXCLUDED.disambiguation_level,
                stage2_reasoning = EXCLUDED.stage2_reasoning,
                has_support_response = EXCLUDED.has_support_response,
                support_response_count = EXCLUDED.support_response_count,
                resolution_action = EXCLUDED.resolution_action,
                resolution_detected = EXCLUDED.resolution_detected,
                support_insights = EXCLUDED.support_insights,
                story_id = EXCLUDED.story_id
            """, (
                conversation_id, created_at, datetime.utcnow(),
                source_body, source_type, source_url,
                contact_email, contact_id,
                issue_type, sentiment, churn_risk, priority,
                stage1_type, stage1_confidence, stage1_routing_priority,
                stage1_urgency, stage1_auto_response, stage1_routing_team,
                stage2_type, stage2_confidence, classification_changed,
                disambiguation_level, stage2_reasoning,
                has_support_response, support_response_count,
                resolution_action, resolution_detected,
                support_insights_json,
                story_id,
                "v2.0-two-stage"
                ))

            conn.commit()



def get_classification_stats(days: int = 30) -> Dict[str, Any]:
    """
    Get classification statistics for the last N days.

    Args:
        days: Number of days to look back

    Returns:
        Dictionary with statistics:
        - total_conversations
        - stage1_confidence_distribution
        - stage2_confidence_distribution
        - classification_changes
        - disambiguation_high_count
        - resolution_detected_count
        - top_stage1_types
        - top_stage2_types
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Total conversations
            cur.execute("""
                SELECT COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND stage1_type IS NOT NULL
            """, (days,))
            total = cur.fetchone()[0]

            # Stage 1 confidence distribution
            cur.execute("""
                SELECT stage1_confidence, COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND stage1_type IS NOT NULL
                GROUP BY stage1_confidence
            """, (days,))
            stage1_confidence = dict(cur.fetchall())

            # Stage 2 confidence distribution
            cur.execute("""
                SELECT stage2_confidence, COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND stage2_type IS NOT NULL
                GROUP BY stage2_confidence
            """, (days,))
            stage2_confidence = dict(cur.fetchall())

            # Classification changes
            cur.execute("""
                SELECT COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND classification_changed = TRUE
            """, (days,))
            classification_changes = cur.fetchone()[0]

            # High disambiguation count
            cur.execute("""
                SELECT COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND disambiguation_level = 'high'
            """, (days,))
            disambiguation_high = cur.fetchone()[0]

            # Resolution detected count
            cur.execute("""
                SELECT COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND resolution_detected = TRUE
            """, (days,))
            resolution_count = cur.fetchone()[0]

            # Top Stage 1 types
            cur.execute("""
                SELECT stage1_type, COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND stage1_type IS NOT NULL
                GROUP BY stage1_type
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, (days,))
            top_stage1 = dict(cur.fetchall())

            # Top Stage 2 types
            cur.execute("""
                SELECT stage2_type, COUNT(*)
                FROM conversations
                WHERE created_at > NOW() - INTERVAL '%s days'
                    AND stage2_type IS NOT NULL
                GROUP BY stage2_type
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, (days,))
            top_stage2 = dict(cur.fetchall())

            return {
                "total_conversations": total,
                "stage1_confidence_distribution": stage1_confidence,
                "stage2_confidence_distribution": stage2_confidence,
                "classification_changes": classification_changes,
                "disambiguation_high_count": disambiguation_high,
                "resolution_detected_count": resolution_count,
                "top_stage1_types": top_stage1,
                "top_stage2_types": top_stage2
            }


def main():
    """Test database storage."""
    from datetime import datetime

    # Test data
    test_id = "test_conversation_001"
    test_stage1 = {
        "conversation_type": "billing_question",
        "confidence": "high",
        "routing_priority": "normal",
        "urgency": "normal",
        "auto_response_eligible": False,
        "routing_team": "billing_team"
    }

    test_stage2 = {
        "conversation_type": "billing_question",
        "confidence": "high",
        "changed_from_stage_1": False,
        "disambiguation_level": "high",
        "reasoning": "Customer wants to cancel subscription",
        "support_insights": {
            "issue_confirmed": "customer wants to cancel",
            "root_cause": "cost reduction",
            "solution_type": "retention conversation",
            "products_mentioned": [],
            "features_mentioned": []
        }
    }

    print("Testing database storage...")
    store_classification_result(
        conversation_id=test_id,
        created_at=datetime.utcnow(),
        source_body="I want to cancel my subscription",
        source_type="conversation",
        source_url=None,
        contact_email="test@example.com",
        contact_id="test_contact_001",
        stage1_result=test_stage1,
        stage2_result=test_stage2,
        support_messages=["I can help with that. Could you share why?"]
    )
    print(f"✓ Stored conversation {test_id}")

    print("\nGetting statistics...")
    stats = get_classification_stats(days=30)
    print(f"Total conversations: {stats['total_conversations']}")
    print(f"Stage 1 confidence: {stats['stage1_confidence_distribution']}")
    print(f"Classification changes: {stats['classification_changes']}")
    print(f"High disambiguation: {stats['disambiguation_high_count']}")


if __name__ == "__main__":
    main()

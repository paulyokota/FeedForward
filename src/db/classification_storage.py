#!/usr/bin/env python3
"""
Database storage for two-stage classification results.

Stores Stage 1 and Stage 2 classification data in PostgreSQL.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import psycopg2
from psycopg2.extras import Json, execute_values

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
    story_id: Optional[str] = None,
    pipeline_run_id: Optional[int] = None
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
        pipeline_run_id: Pipeline run ID that classified this conversation (for run scoping)
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

            if stage2_result:
                stage2_type = stage2_result.get("conversation_type")
                stage2_confidence = stage2_result.get("confidence")
                classification_changed = stage2_result.get("changed_from_stage_1", False)
                disambiguation_level = stage2_result.get("disambiguation_level")
                stage2_reasoning = stage2_result.get("reasoning")

            # Extract support_insights (from stage2_result for backward compatibility)
            # NOTE: This function doesn't receive support_insights as a top-level parameter.
            # The batch function correctly extracts from result dict's top level.
            # Single-insert is used only for tests; batch insert is used in production.
            support_insights_json = None
            if stage2_result and stage2_result.get("support_insights"):
                support_insights_json = Json(stage2_result.get("support_insights"))

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
                classifier_version,
                pipeline_run_id
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
                story_id = EXCLUDED.story_id,
                pipeline_run_id = EXCLUDED.pipeline_run_id
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
                "v2.0-two-stage",
                pipeline_run_id
                ))

            conn.commit()


def store_classification_results_batch(
    results: List[Dict[str, Any]],
    pipeline_run_id: Optional[int] = None
) -> int:
    """
    Store multiple classification results in a single batch operation.

    ~50x faster than individual inserts for large batches.

    Args:
        results: List of dictionaries with keys matching store_classification_result params
        pipeline_run_id: Pipeline run ID that classified these conversations (for run scoping)

    Returns:
        Number of rows inserted/updated
    """
    if not results:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Prepare all rows
            rows = []
            for r in results:
                # Extract Stage 1 fields
                stage1_result = r.get("stage1_result", {})
                stage1_type = stage1_result.get("conversation_type")
                stage1_confidence = stage1_result.get("confidence")
                stage1_routing_priority = stage1_result.get("routing_priority")
                stage1_urgency = stage1_result.get("urgency")
                stage1_auto_response = stage1_result.get("auto_response_eligible", False)
                stage1_routing_team = stage1_result.get("routing_team")

                # Extract Stage 2 fields
                stage2_result = r.get("stage2_result")
                stage2_type = None
                stage2_confidence = None
                classification_changed = False
                disambiguation_level = None
                stage2_reasoning = None

                if stage2_result:
                    stage2_type = stage2_result.get("conversation_type")
                    stage2_confidence = stage2_result.get("confidence")
                    classification_changed = stage2_result.get("changed_from_stage_1", False)
                    disambiguation_level = stage2_result.get("disambiguation_level")
                    stage2_reasoning = stage2_result.get("reasoning")

                # Extract support_insights (from top-level result, not stage2_result)
                support_insights = r.get("support_insights")
                support_insights_json = None
                if support_insights:
                    support_insights_json = Json(support_insights)

                # Support context
                support_messages = r.get("support_messages", [])
                has_support_response = bool(support_messages)
                support_response_count = len(support_messages) if support_messages else 0

                # Resolution analysis
                resolution_signal = r.get("resolution_signal")
                resolution_action = None
                resolution_detected = False
                if resolution_signal and isinstance(resolution_signal, dict):
                    resolution_action = resolution_signal.get("action")
                    resolution_detected = bool(resolution_action)

                rows.append((
                    r["conversation_id"],
                    r["created_at"],
                    datetime.utcnow(),  # classified_at
                    r.get("source_body"),
                    r.get("source_type"),
                    r.get("source_url"),
                    r.get("contact_email"),
                    r.get("contact_id"),
                    "other",  # issue_type default
                    "neutral",  # sentiment default
                    False,  # churn_risk
                    "normal",  # priority default
                    stage1_type,
                    stage1_confidence,
                    stage1_routing_priority,
                    stage1_urgency,
                    stage1_auto_response,
                    stage1_routing_team,
                    stage2_type,
                    stage2_confidence,
                    classification_changed,
                    disambiguation_level,
                    stage2_reasoning,
                    has_support_response,
                    support_response_count,
                    resolution_action,
                    resolution_detected,
                    support_insights_json,
                    r.get("story_id"),
                    "v2.0-two-stage",
                    pipeline_run_id,
                ))

            # Batch upsert using execute_values
            sql = """
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
                classifier_version,
                pipeline_run_id
            ) VALUES %s
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
                story_id = EXCLUDED.story_id,
                pipeline_run_id = EXCLUDED.pipeline_run_id
            """
            execute_values(cur, sql, rows)
            conn.commit()
            return len(rows)


def get_classification_stats(days: int = 30) -> Dict[str, Any]:
    """
    Get classification statistics for the last N days.

    Uses a single CTE query instead of 8 separate queries (~8x faster).

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
            # Single query with CTEs for all aggregations
            cur.execute("""
                WITH filtered AS (
                    SELECT *
                    FROM conversations
                    WHERE created_at > NOW() - INTERVAL '%s days'
                ),
                base_stats AS (
                    SELECT
                        COUNT(*) FILTER (WHERE stage1_type IS NOT NULL) as total,
                        COUNT(*) FILTER (WHERE classification_changed = TRUE) as changes,
                        COUNT(*) FILTER (WHERE disambiguation_level = 'high') as disambiguation_high,
                        COUNT(*) FILTER (WHERE resolution_detected = TRUE) as resolution_count
                    FROM filtered
                ),
                s1_conf AS (
                    SELECT stage1_confidence as conf, COUNT(*) as cnt
                    FROM filtered
                    WHERE stage1_type IS NOT NULL
                    GROUP BY stage1_confidence
                ),
                s2_conf AS (
                    SELECT stage2_confidence as conf, COUNT(*) as cnt
                    FROM filtered
                    WHERE stage2_type IS NOT NULL
                    GROUP BY stage2_confidence
                ),
                top_s1 AS (
                    SELECT stage1_type as typ, COUNT(*) as cnt
                    FROM filtered
                    WHERE stage1_type IS NOT NULL
                    GROUP BY stage1_type
                    ORDER BY cnt DESC
                    LIMIT 5
                ),
                top_s2 AS (
                    SELECT stage2_type as typ, COUNT(*) as cnt
                    FROM filtered
                    WHERE stage2_type IS NOT NULL
                    GROUP BY stage2_type
                    ORDER BY cnt DESC
                    LIMIT 5
                )
                SELECT
                    'base' as query_type,
                    (SELECT total FROM base_stats)::text as val1,
                    (SELECT changes FROM base_stats)::text as val2,
                    (SELECT disambiguation_high FROM base_stats)::text as val3,
                    (SELECT resolution_count FROM base_stats)::text as val4
                UNION ALL
                SELECT 's1_conf', conf, cnt::text, NULL, NULL FROM s1_conf
                UNION ALL
                SELECT 's2_conf', conf, cnt::text, NULL, NULL FROM s2_conf
                UNION ALL
                SELECT 'top_s1', typ, cnt::text, NULL, NULL FROM top_s1
                UNION ALL
                SELECT 'top_s2', typ, cnt::text, NULL, NULL FROM top_s2
            """, (days,))

            # Parse unified result set
            rows = cur.fetchall()

            total = 0
            classification_changes = 0
            disambiguation_high = 0
            resolution_count = 0
            stage1_confidence = {}
            stage2_confidence = {}
            top_stage1 = {}
            top_stage2 = {}

            for row in rows:
                query_type = row[0]
                if query_type == 'base':
                    total = int(row[1]) if row[1] else 0
                    classification_changes = int(row[2]) if row[2] else 0
                    disambiguation_high = int(row[3]) if row[3] else 0
                    resolution_count = int(row[4]) if row[4] else 0
                elif query_type == 's1_conf' and row[1]:
                    stage1_confidence[row[1]] = int(row[2])
                elif query_type == 's2_conf' and row[1]:
                    stage2_confidence[row[1]] = int(row[2])
                elif query_type == 'top_s1' and row[1]:
                    top_stage1[row[1]] = int(row[2])
                elif query_type == 'top_s2' and row[1]:
                    top_stage2[row[1]] = int(row[2])

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

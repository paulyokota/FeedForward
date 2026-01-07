#!/usr/bin/env python3
"""
Stage 1: Quick Routing Classifier

Purpose: Fast classification for immediate routing and auto-responses
Input: Customer's initial message only
Speed: <1 second
Confidence: Medium-High acceptable
Use: Route to support team, priority assignment, auto-response triggers

STUB IMPLEMENTATION - Will be built in Phase 1
"""
from typing import Dict, Any


def classify_stage1(
    customer_message: str,
    source_url: str | None = None,
    source_type: str | None = None
) -> Dict[str, Any]:
    """
    Fast customer-only classification for routing.

    Args:
        customer_message: The customer's initial message
        source_url: Optional source URL for context
        source_type: Optional source type (email, chat, etc.)

    Returns:
        {
            "conversation_type": str,
            "confidence": "high" | "medium" | "low",
            "routing_priority": "urgent" | "high" | "normal" | "low",
            "auto_response_eligible": bool,
            "stage": 1,
            "url_context": str | None,
            "key_signals": list[str]
        }
    """
    # STUB: Always return medium confidence "general_inquiry"
    return {
        "conversation_type": "general_inquiry",
        "confidence": "medium",
        "routing_priority": "normal",
        "auto_response_eligible": False,
        "stage": 1,
        "url_context": source_url,
        "key_signals": ["customer message", "no support context yet"]
    }


def should_auto_respond(stage1_result: Dict[str, Any]) -> bool:
    """
    Determine if conversation is eligible for auto-response.

    Args:
        stage1_result: Result from classify_stage1

    Returns:
        True if auto-response should be sent
    """
    # STUB: Never auto-respond
    return False


def get_routing_team(conversation_type: str) -> str:
    """
    Map conversation type to support team.

    Args:
        conversation_type: Classified type from Stage 1

    Returns:
        Team name to route to
    """
    # STUB: Always route to general support
    return "general_support"

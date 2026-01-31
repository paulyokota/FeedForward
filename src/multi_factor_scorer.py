#!/usr/bin/env python3
"""
Multi-Factor Scorer for Stories.

Computes actionability, fix_size, severity, and churn_risk scores (0-100)
for story prioritization and sorting.

Issue #188: Add sortable multi-factor story scoring

Usage:
    from multi_factor_scorer import MultiFactorScorer, StoryScoreInput

    scorer = MultiFactorScorer()
    scores = scorer.score(StoryScoreInput(
        conversations=[...],
        implementation_context={...},
        code_context={...},
        evidence_count=5,
    ))
    # Returns MultiFactorScores with all scores + metadata breakdown
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ============================================================================
# SCORING WEIGHTS - Hardcoded for now, tune via code changes (YAGNI)
# ============================================================================

# Actionability weights (max 100)
ACTIONABILITY_IMPL_CONTEXT = 30
ACTIONABILITY_RESOLUTION_ACTION = 20
ACTIONABILITY_RESOLUTION_CATEGORY = 15
ACTIONABILITY_KEY_EXCERPTS = 15
ACTIONABILITY_DIAGNOSTIC_SUMMARY = 10
ACTIONABILITY_EVIDENCE_THRESHOLD = 3
ACTIONABILITY_EVIDENCE_BONUS = 10

# Fix size weights
FIX_SIZE_PER_FILE = 5
FIX_SIZE_FILE_CAP = 40
FIX_SIZE_PER_EXCERPT = 2
FIX_SIZE_EXCERPT_CAP = 20
FIX_SIZE_CODE_CONTEXT = 10
FIX_SIZE_SYMPTOMS_THRESHOLD = 5
FIX_SIZE_SYMPTOMS_BONUS = 10

# Severity weights
SEVERITY_PRIORITY_MAP = {
    "urgent": 100,
    "high": 80,
    "medium": 50,
    "normal": 50,  # Alias for medium
    "low": 20,
    None: 0,
}
SEVERITY_FOCUSED_IMPACT_BONUS = 10
SEVERITY_ERROR_KEYWORDS_BONUS = 10
SEVERITY_MAX = 100

# Error keywords that indicate severity
ERROR_KEYWORDS = [
    "crash", "failure", "timeout", "error", "exception", "broken",
    "down", "outage", "critical", "urgent", "emergency", "blocked",
    "cannot", "unable", "failed", "failing", "breaks", "broke",
]

# Churn risk weights
CHURN_RISK_TRUE_BASE = 80
CHURN_RISK_FALSE_BASE = 20
CHURN_RISK_UNKNOWN_DEFAULT = 40
CHURN_RISK_ORG_BREADTH_MAX = 20

# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ConversationScoreData:
    """Minimal conversation data needed for scoring."""

    id: str
    priority: Optional[str] = None
    churn_risk: Optional[bool] = None
    org_id: Optional[str] = None
    diagnostic_summary: Optional[str] = None
    key_excerpts: List[Dict] = field(default_factory=list)
    symptoms: List[str] = field(default_factory=list)
    resolution_action: Optional[str] = None
    resolution_category: Optional[str] = None


@dataclass
class StoryScoreInput:
    """Input data for multi-factor scoring."""

    # List of conversations in the story group
    conversations: List[ConversationScoreData] = field(default_factory=list)

    # Story-level context (may be None for new stories)
    implementation_context: Optional[Dict[str, Any]] = None
    code_context: Optional[Dict[str, Any]] = None
    evidence_count: int = 0

    # Pre-aggregated values (optional, computed from conversations if not provided)
    platform_uniformity: Optional[float] = None
    product_area_match: Optional[bool] = None

    @classmethod
    def from_conversation_dicts(
        cls,
        conv_dicts: List[Dict[str, Any]],
        implementation_context: Optional[Dict[str, Any]] = None,
        code_context: Optional[Dict[str, Any]] = None,
        evidence_count: int = 0,
        platform_uniformity: Optional[float] = None,
        product_area_match: Optional[bool] = None,
    ) -> "StoryScoreInput":
        """Create from raw conversation dicts (pipeline format)."""
        conversations = []
        for d in conv_dicts:
            conversations.append(ConversationScoreData(
                id=d.get("id", ""),
                priority=d.get("priority"),
                churn_risk=d.get("churn_risk"),
                org_id=d.get("org_id"),
                diagnostic_summary=d.get("diagnostic_summary"),
                key_excerpts=d.get("key_excerpts", []),
                symptoms=d.get("symptoms", []),
                resolution_action=d.get("resolution_action"),
                resolution_category=d.get("resolution_category"),
            ))
        return cls(
            conversations=conversations,
            implementation_context=implementation_context,
            code_context=code_context,
            evidence_count=evidence_count,
            platform_uniformity=platform_uniformity,
            product_area_match=product_area_match,
        )


@dataclass
class MultiFactorScores:
    """Output from multi-factor scoring."""

    actionability_score: float
    fix_size_score: float
    severity_score: float
    churn_risk_score: float
    metadata: Dict[str, Any]


# ============================================================================
# SCORER CLASS
# ============================================================================


class MultiFactorScorer:
    """Computes multi-factor scores for story prioritization."""

    def score(self, input_data: StoryScoreInput) -> MultiFactorScores:
        """
        Compute all scores for a story.

        Args:
            input_data: StoryScoreInput with conversations and context

        Returns:
            MultiFactorScores with all scores and metadata breakdown
        """
        # Compute each score with breakdown
        actionability, action_breakdown = self._compute_actionability(input_data)
        fix_size, fix_breakdown = self._compute_fix_size(input_data)
        severity, severity_breakdown = self._compute_severity(input_data)
        churn_risk, churn_breakdown = self._compute_churn_risk(input_data)

        # Build metadata
        metadata = {
            "schema_version": "1.0",
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "conversation_count": len(input_data.conversations),
            "actionability": action_breakdown,
            "fix_size": fix_breakdown,
            "severity": severity_breakdown,
            "churn_risk": churn_breakdown,
        }

        return MultiFactorScores(
            actionability_score=round(actionability, 2),
            fix_size_score=round(fix_size, 2),
            severity_score=round(severity, 2),
            churn_risk_score=round(churn_risk, 2),
            metadata=metadata,
        )

    def _compute_actionability(
        self, input_data: StoryScoreInput
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute actionability score (0-100).

        Higher = more ready to implement.
        Based on presence of implementation context, resolution data, evidence quality.
        """
        breakdown = {}
        total = 0.0

        # +30 if implementation_context present
        has_impl = bool(
            input_data.implementation_context
            and input_data.implementation_context.get("summary")
        )
        breakdown["implementation_context_present"] = ACTIONABILITY_IMPL_CONTEXT if has_impl else 0
        total += breakdown["implementation_context_present"]

        # Aggregate from conversations
        has_resolution_action = any(
            c.resolution_action for c in input_data.conversations
        )
        has_resolution_category = any(
            c.resolution_category for c in input_data.conversations
        )
        has_key_excerpts = any(
            c.key_excerpts and len(c.key_excerpts) >= 1 for c in input_data.conversations
        )
        has_diagnostic_summary = any(
            c.diagnostic_summary for c in input_data.conversations
        )

        # +20 if resolution_action present
        breakdown["resolution_action_present"] = ACTIONABILITY_RESOLUTION_ACTION if has_resolution_action else 0
        total += breakdown["resolution_action_present"]

        # +15 if resolution_category present
        breakdown["resolution_category_present"] = ACTIONABILITY_RESOLUTION_CATEGORY if has_resolution_category else 0
        total += breakdown["resolution_category_present"]

        # +15 if key_excerpts >= 1
        breakdown["key_excerpts_present"] = ACTIONABILITY_KEY_EXCERPTS if has_key_excerpts else 0
        total += breakdown["key_excerpts_present"]

        # +10 if diagnostic_summary present
        breakdown["diagnostic_summary_present"] = ACTIONABILITY_DIAGNOSTIC_SUMMARY if has_diagnostic_summary else 0
        total += breakdown["diagnostic_summary_present"]

        # +10 if evidence_count >= 3
        has_enough_evidence = input_data.evidence_count >= ACTIONABILITY_EVIDENCE_THRESHOLD
        breakdown["evidence_count_bonus"] = ACTIONABILITY_EVIDENCE_BONUS if has_enough_evidence else 0
        breakdown["evidence_count"] = input_data.evidence_count
        total += breakdown["evidence_count_bonus"]

        breakdown["total"] = total
        return total, breakdown

    def _compute_fix_size(
        self, input_data: StoryScoreInput
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute fix size score (0-100).

        Higher = larger/more complex fix.
        Based on file count, excerpt count, code context, symptoms.
        """
        breakdown = {}
        raw_total = 0.0

        # +5 per relevant file in implementation_context (cap 40)
        file_count = 0
        if input_data.implementation_context:
            relevant_files = input_data.implementation_context.get("relevant_files", [])
            file_count = len(relevant_files) if isinstance(relevant_files, list) else 0
        file_score = min(file_count * FIX_SIZE_PER_FILE, FIX_SIZE_FILE_CAP)
        breakdown["relevant_files_count"] = file_count
        breakdown["relevant_files_score"] = file_score
        raw_total += file_score

        # +2 per evidence excerpt (cap 20)
        # Count total key_excerpts across conversations
        excerpt_count = sum(
            len(c.key_excerpts or []) for c in input_data.conversations
        )
        excerpt_score = min(excerpt_count * FIX_SIZE_PER_EXCERPT, FIX_SIZE_EXCERPT_CAP)
        breakdown["evidence_excerpts_count"] = excerpt_count
        breakdown["evidence_excerpts_score"] = excerpt_score
        raw_total += excerpt_score

        # +10 if code_context exists
        has_code_context = bool(
            input_data.code_context
            and (
                input_data.code_context.get("relevant_files")
                or input_data.code_context.get("code_snippets")
            )
        )
        breakdown["code_context_present"] = FIX_SIZE_CODE_CONTEXT if has_code_context else 0
        raw_total += breakdown["code_context_present"]

        # +10 if symptoms count >= 5 (dedupe across conversations)
        unique_symptoms = set()
        for c in input_data.conversations:
            if c.symptoms:
                unique_symptoms.update(c.symptoms)
        symptom_count = len(unique_symptoms)
        has_many_symptoms = symptom_count >= FIX_SIZE_SYMPTOMS_THRESHOLD
        breakdown["symptoms_count"] = symptom_count
        breakdown["symptoms_bonus"] = FIX_SIZE_SYMPTOMS_BONUS if has_many_symptoms else 0
        raw_total += breakdown["symptoms_bonus"]

        breakdown["raw_total"] = raw_total

        # Normalize to 0-100
        # Max possible raw = 40 + 20 + 10 + 10 = 80, so scale by 100/80 = 1.25
        max_raw = FIX_SIZE_FILE_CAP + FIX_SIZE_EXCERPT_CAP + FIX_SIZE_CODE_CONTEXT + FIX_SIZE_SYMPTOMS_BONUS
        normalized = (raw_total / max_raw) * 100 if max_raw > 0 else 0
        normalized = min(normalized, 100)  # Cap at 100

        breakdown["total"] = normalized
        breakdown["normalized"] = True

        return normalized, breakdown

    def _compute_severity(
        self, input_data: StoryScoreInput
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute severity score (0-100).

        Higher = more urgent/impactful.
        Based on priority mapping, focused impact, error keywords.
        """
        breakdown = {}
        total = 0.0

        # Base: max priority across conversations
        priorities = [c.priority for c in input_data.conversations if c.priority]
        if priorities:
            # Get highest priority (urgent > high > medium > low)
            # Use tuple comparison to find both max score and its priority together
            max_priority, base_score = max(
                ((p, SEVERITY_PRIORITY_MAP.get(p, 0)) for p in priorities),
                key=lambda x: x[1]
            )
        else:
            base_score = 0
            max_priority = None

        breakdown["priority_base"] = base_score
        breakdown["max_priority"] = max_priority
        total += base_score

        # +10 if focused impact (platform_uniformity == 1.0 and product_area_match)
        focused_impact = (
            input_data.platform_uniformity == 1.0
            and input_data.product_area_match is True
        )
        breakdown["focused_impact"] = focused_impact
        breakdown["focused_impact_bonus"] = SEVERITY_FOCUSED_IMPACT_BONUS if focused_impact else 0
        total += breakdown["focused_impact_bonus"]

        # +10 if error keywords in diagnostic_summary
        has_error_keywords = False
        matched_keywords = []
        for c in input_data.conversations:
            if c.diagnostic_summary:
                summary_lower = c.diagnostic_summary.lower()
                for keyword in ERROR_KEYWORDS:
                    if keyword in summary_lower:
                        has_error_keywords = True
                        if keyword not in matched_keywords:
                            matched_keywords.append(keyword)

        breakdown["error_keywords_found"] = matched_keywords
        breakdown["error_keywords_bonus"] = SEVERITY_ERROR_KEYWORDS_BONUS if has_error_keywords else 0
        total += breakdown["error_keywords_bonus"]

        # Cap at 100
        capped = total > SEVERITY_MAX
        total = min(total, SEVERITY_MAX)

        breakdown["total"] = total
        breakdown["capped"] = capped

        return total, breakdown

    def _compute_churn_risk(
        self, input_data: StoryScoreInput
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute churn risk score (0-100).

        Higher = higher risk of customer churn.
        Based on churn_risk flag and org breadth.
        """
        breakdown = {}

        # Check if any conversation has churn_risk data
        churn_flags = [c.churn_risk for c in input_data.conversations if c.churn_risk is not None]

        if not churn_flags:
            # No churn data - default to neutral
            base_score = CHURN_RISK_UNKNOWN_DEFAULT
            breakdown["churn_risk_source"] = "unknown"
        elif any(churn_flags):
            # At least one conversation flagged as churn risk
            base_score = CHURN_RISK_TRUE_BASE
            breakdown["churn_risk_source"] = "flagged"
        else:
            # All conversations explicitly not churn risk
            base_score = CHURN_RISK_FALSE_BASE
            breakdown["churn_risk_source"] = "not_flagged"

        breakdown["base_score"] = base_score

        # Org breadth bonus: (0-20) scaled by unique org count
        org_ids = set(c.org_id for c in input_data.conversations if c.org_id)
        org_count = len(org_ids)

        # Scale: 1 org = 0, 5+ orgs = max bonus
        # Linear scale: bonus = min(org_count - 1, 4) * 5
        org_bonus = min(max(org_count - 1, 0), 4) * (CHURN_RISK_ORG_BREADTH_MAX / 4)

        breakdown["unique_org_count"] = org_count
        breakdown["org_breadth_bonus"] = org_bonus

        total = base_score + org_bonus
        breakdown["total"] = total

        return total, breakdown


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def create_default_scores() -> MultiFactorScores:
    """Create default scores for stories with missing data."""
    return MultiFactorScores(
        actionability_score=0.0,
        fix_size_score=0.0,
        severity_score=40.0,  # Neutral midpoint
        churn_risk_score=40.0,  # Neutral midpoint
        metadata={
            "schema_version": "1.0",
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "conversation_count": 0,
            "note": "Default scores - insufficient data for calculation",
        },
    )

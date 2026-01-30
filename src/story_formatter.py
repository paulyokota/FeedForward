"""
Shortcut story formatting - single source of truth.

All story creation should use these functions to ensure consistent formatting.

Format spec:
- Excerpts link to Intercom conversation, Jarvis org page, Jarvis user page
- Description includes category, count, percentage, samples, review checklist
- Footer identifies FeedForward as the generator
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import ExplorationResult and related types from codebase context provider
try:
    from src.story_tracking.services.codebase_context_provider import (
        ExplorationResult,
        FileReference,
        CodeSnippet,
    )
except ImportError:
    # Graceful degradation if codebase context provider not available
    ExplorationResult = None
    FileReference = None
    CodeSnippet = None

# Import GeneratedStoryContent for LLM-generated story fields
try:
    from src.story_tracking.services.story_content_generator import GeneratedStoryContent
except ImportError:
    # Graceful degradation if story content generator not available
    GeneratedStoryContent = None

# Production Intercom app ID for URL generation
INTERCOM_APP_ID = os.getenv("INTERCOM_APP_ID", "2t3d8az2")
# Coda document ID for deep links to research data
CODA_DOC_ID = os.getenv("CODA_DOC_ID", "")
# Maximum characters for excerpt text in formatted output
EXCERPT_MAX_LENGTH = 300


def format_excerpt(
    conversation_id: str,
    email: Optional[str] = None,
    excerpt: str = "",
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
    intercom_url: Optional[str] = None,
    jarvis_org_url: Optional[str] = None,
    jarvis_user_url: Optional[str] = None,
) -> str:
    """
    Format a conversation excerpt with linked metadata.

    Format: [email](intercom_url) | [Org](jarvis_org_url) | [User](jarvis_user_url)
    > excerpt text...

    Args:
        conversation_id: Intercom conversation ID
        email: Customer email address
        excerpt: Conversation excerpt text
        org_id: Tailwind org ID (for Jarvis URL)
        user_id: Tailwind user ID (for Jarvis URL)
        intercom_url: Pre-built Intercom URL (optional, will build if not provided)
        jarvis_org_url: Pre-built Jarvis org URL (optional)
        jarvis_user_url: Pre-built Jarvis user URL (optional)

    Returns:
        Formatted markdown string
    """
    parts = []

    # Build URLs if not provided
    if not intercom_url:
        intercom_url = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/conversation/{conversation_id}"

    if not jarvis_org_url and org_id:
        jarvis_org_url = f"https://jarvis.tailwind.ai/organizations/{org_id}"

    if not jarvis_user_url and org_id and user_id:
        jarvis_user_url = f"https://jarvis.tailwind.ai/organizations/{org_id}/users/{user_id}"

    # Email linked to Intercom conversation
    display_email = email or f"Conversation {conversation_id}"
    parts.append(f"[{display_email}]({intercom_url})")

    # Org linked to Jarvis
    if jarvis_org_url:
        parts.append(f"[Org]({jarvis_org_url})")

    # User linked to Jarvis
    if jarvis_user_url:
        parts.append(f"[User]({jarvis_user_url})")

    user_info = " | ".join(parts)
    excerpt_text = excerpt[:EXCERPT_MAX_LENGTH] if excerpt else ""

    return f"{user_info}\n> {excerpt_text}"


def build_story_description(
    category: str,
    count: int,
    total: int,
    samples: list[dict],
    pipeline_name: str = "FeedForward Classification Pipeline",
    time_period: str = "Last 30 Days",
) -> str:
    """
    Build Shortcut story description with formatted excerpts.

    Args:
        category: Classification category name
        count: Number of conversations in this category
        total: Total conversations analyzed
        samples: List of sample conversation dicts with keys:
            - id: conversation ID
            - email: customer email (optional)
            - excerpt: conversation text
            - org_id: Tailwind org ID (optional)
            - user_id: Tailwind user ID (optional)
            - intercom_url: pre-built URL (optional)
            - jarvis_org_url: pre-built URL (optional)
            - jarvis_user_url: pre-built URL (optional)
        pipeline_name: Name of the generating pipeline
        time_period: Description of time period analyzed

    Returns:
        Formatted markdown description
    """
    pct = count / total * 100 if total > 0 else 0

    description = f"""## Classification Results ({time_period})

**Category**: {category}
**Count**: {count} ({pct:.1f}% of total)
**Total Conversations Analyzed**: {total}

---

## Sample Conversations

"""
    for i, sample in enumerate(samples[:5], 1):
        formatted = format_excerpt(
            conversation_id=sample.get("id", "unknown"),
            email=sample.get("email"),
            excerpt=sample.get("excerpt", ""),
            org_id=sample.get("org_id"),
            user_id=sample.get("user_id"),
            intercom_url=sample.get("intercom_url"),
            jarvis_org_url=sample.get("jarvis_org_url"),
            jarvis_user_url=sample.get("jarvis_user_url"),
        )
        description += f"### Sample {i}\n{formatted}\n\n"

    description += f"""---

## Review Checklist
- [ ] Classification accuracy looks correct
- [ ] Sample excerpts match the category
- [ ] No obvious misclassifications

---
*Generated by {pipeline_name}*
"""
    return description


def get_story_type(category: str) -> str:
    """
    Get Shortcut story type based on classification category.

    Args:
        category: Classification category name

    Returns:
        "bug", "feature", or "chore"
    """
    if category == "product_issue":
        return "bug"
    elif category == "feature_request":
        return "feature"
    else:
        return "chore"


def build_story_name(category: str, count: int, suffix: str = "Review") -> str:
    """
    Build consistent story name.

    Format: [count] Category Name - suffix

    Args:
        category: Classification category (snake_case)
        count: Number of conversations
        suffix: Story name suffix (default: "Review")

    Returns:
        Formatted story name
    """
    title = category.replace("_", " ").title()
    return f"[{count}] {title} - {suffix}"


def format_multi_source_evidence(
    intercom_samples: list[dict],
    coda_samples: list[dict],
    source_counts: dict,
) -> str:
    """
    Format evidence from multiple sources for story description.

    Creates a structured evidence section with quotes from both
    Intercom support conversations and Coda research.

    Args:
        intercom_samples: List of Intercom conversation samples
            - id: conversation ID
            - email: customer email
            - excerpt: conversation text
            - created_at: timestamp
        coda_samples: List of Coda research samples
            - page_name: source page name
            - participant: participant email
            - excerpt: research quote
            - theme_type: pain_point, feature_request, etc.
        source_counts: Dict of counts per source {"intercom": N, "coda": M}

    Returns:
        Formatted markdown evidence section
    """
    lines = ["## Evidence\n"]

    # Intercom section
    intercom_count = source_counts.get("intercom", 0)
    if intercom_count > 0 and intercom_samples:
        lines.append(f"### From Support (Intercom) - {intercom_count} conversations\n")
        for sample in intercom_samples[:5]:
            email = sample.get("email", "Customer")
            excerpt = sample.get("excerpt", "")[:200]
            conv_id = sample.get("id", "")
            intercom_url = f"https://app.intercom.com/a/apps/{INTERCOM_APP_ID}/inbox/inbox/conversation/{conv_id}"
            lines.append(f"- [{email}]({intercom_url}): \"{excerpt}...\"")
        lines.append("")

    # Coda section
    coda_count = source_counts.get("coda", 0)
    if coda_count > 0 and coda_samples:
        lines.append(f"### From Research (Coda) - {coda_count} interviews\n")
        for sample in coda_samples[:5]:
            participant = sample.get("participant", "Research participant")
            excerpt = sample.get("excerpt", "")[:200]
            theme_type = sample.get("theme_type", "insight")
            page_name = sample.get("page_name", "")

            # Format theme type as label
            type_label = theme_type.replace("_", " ").title()
            lines.append(f"- **{type_label}**: \"{excerpt}...\"")
            if participant:
                lines.append(f"  - From: {participant}")
        lines.append("")

    # Priority signal
    if intercom_count > 0 and coda_count > 0:
        lines.append("### Priority Signal\n")
        lines.append("✅ **High Confidence** - Theme confirmed in both research interviews and support volume\n")
    elif coda_count > 0:
        lines.append("### Priority Signal\n")
        lines.append("📊 **Strategic** - Theme from research interviews (proactive insight)\n")
    elif intercom_count > 0:
        lines.append("### Priority Signal\n")
        lines.append("🎯 **Tactical** - Theme from support volume (reactive signal)\n")

    return "\n".join(lines)


def build_multi_source_description(
    issue_signature: str,
    product_area: str,
    component: str,
    total_count: int,
    source_counts: dict,
    intercom_samples: list[dict] = None,
    coda_samples: list[dict] = None,
    root_cause_hypothesis: str = None,
    pipeline_name: str = "FeedForward Multi-Source Pipeline",
) -> str:
    """
    Build story description with multi-source evidence.

    Args:
        issue_signature: Theme signature
        product_area: Product area affected
        component: Component affected
        total_count: Total occurrences across all sources
        source_counts: Dict of counts per source
        intercom_samples: Intercom conversation samples
        coda_samples: Coda research samples
        root_cause_hypothesis: Analysis of root cause
        pipeline_name: Name of generating pipeline

    Returns:
        Formatted markdown description
    """
    intercom_count = source_counts.get("intercom", 0)
    coda_count = source_counts.get("coda", 0)

    # Determine confidence level
    if intercom_count > 0 and coda_count > 0:
        confidence = "✅ High Confidence (Both Sources)"
    elif coda_count > 0:
        confidence = "📊 Strategic (Research Only)"
    else:
        confidence = "🎯 Tactical (Support Only)"

    description = f"""## Theme Summary

**Issue**: {issue_signature.replace('_', ' ').title()}
**Product Area**: {product_area}
**Component**: {component}
**Total Reports**: {total_count}
**Confidence**: {confidence}

### Source Breakdown
- Intercom (Support): {intercom_count} conversations
- Coda (Research): {coda_count} interviews

---

"""

    # Add multi-source evidence
    evidence = format_multi_source_evidence(
        intercom_samples=intercom_samples or [],
        coda_samples=coda_samples or [],
        source_counts=source_counts,
    )
    description += evidence

    # Add root cause if available
    if root_cause_hypothesis:
        description += f"""
---

## Technical Context

**Root Cause Hypothesis**: {root_cause_hypothesis}
"""

    description += f"""
---

## Acceptance Criteria

- [ ] Root cause confirmed or updated
- [ ] Fix addresses both support and research feedback
- [ ] Regression testing on {product_area} functionality

---
*Generated by {pipeline_name}*
"""
    return description


def get_priority_label(source_counts: dict) -> str:
    """
    Get priority label based on source presence.

    Args:
        source_counts: Dict of counts per source

    Returns:
        Priority label string
    """
    has_coda = source_counts.get("coda", 0) > 0
    has_intercom = source_counts.get("intercom", 0) > 0

    if has_coda and has_intercom:
        return "high_confidence"
    elif has_coda:
        return "strategic"
    else:
        return "tactical"


def format_coda_excerpt(
    text: str,
    table_name: Optional[str] = None,
    participant: Optional[str] = None,
    page_id: Optional[str] = None,
    row_id: Optional[str] = None,
    coda_doc_id: Optional[str] = None,
) -> str:
    """
    Format Coda research excerpt with links.

    Format: [Participant or Table](Coda URL)
    > "Quote from research..."

    Link generation strategy:
    - For table rows: https://coda.io/d/{doc_id}#row-{row_id}
    - For pages: https://coda.io/d/{doc_id}/_/{page_id}
    - Fallback: https://coda.io/d/{doc_id} (doc root)

    Args:
        text: Excerpt text
        table_name: Table name (for display)
        participant: Participant identifier (for display)
        page_id: Coda page ID
        row_id: Coda row ID
        coda_doc_id: Coda doc ID (optional, defaults to env)

    Returns:
        Formatted markdown string
    """
    doc_id = coda_doc_id or CODA_DOC_ID

    # Build URL based on available identifiers
    if row_id and doc_id:
        url = f"https://coda.io/d/{doc_id}#row-{row_id}"
    elif page_id and doc_id:
        url = f"https://coda.io/d/{doc_id}/_/{page_id}"
    elif doc_id:
        url = f"https://coda.io/d/{doc_id}"
    else:
        url = "https://coda.io"

    # Display label priority: participant > table_name > "Research"
    if participant:
        display = participant
    elif table_name:
        display = table_name
    else:
        display = "Research"

    excerpt_text = text[:300] if text else ""
    return f"[{display}]({url})\n> {excerpt_text}"


def format_excerpt_multi_source(
    source: str,
    text: str,
    conversation_id: Optional[str] = None,
    source_metadata: Optional[Dict] = None,
) -> str:
    """
    Route to source-specific formatting.

    For Intercom: Uses existing format_excerpt() with Jarvis links
    For Coda: Uses format_coda_excerpt() with Coda doc links

    Args:
        source: "intercom" or "coda"
        text: Excerpt text
        conversation_id: Intercom conversation ID (for intercom source)
        source_metadata: Dict with source-specific fields:
            For Intercom: email, org_id, user_id, urls
            For Coda: table_name, participant, page_id, row_id

    Returns:
        Formatted markdown string
    """
    metadata = source_metadata or {}

    if source == "intercom":
        return format_excerpt(
            conversation_id=conversation_id or "unknown",
            email=metadata.get("email"),
            excerpt=text,
            org_id=metadata.get("org_id"),
            user_id=metadata.get("user_id"),
            intercom_url=metadata.get("intercom_url"),
            jarvis_org_url=metadata.get("jarvis_org_url"),
            jarvis_user_url=metadata.get("jarvis_user_url"),
        )
    elif source == "coda":
        return format_coda_excerpt(
            text=text,
            table_name=metadata.get("table_name"),
            participant=metadata.get("participant"),
            page_id=metadata.get("page_id"),
            row_id=metadata.get("row_id"),
            coda_doc_id=metadata.get("coda_doc_id"),
        )
    else:
        # Unknown source: return plain text
        return f"> {text[:300]}"


def build_research_story_description(
    theme_name: str,
    excerpts: List[Dict],
    participant_count: int,
    theme_type: str,
    source_breakdown: Dict[str, int],
) -> str:
    """
    Build description optimized for research-sourced stories.

    Structure (different from bug reports):
    1. Theme Summary (what users are saying)
    2. Research Context (participant count, sources)
    3. Representative Quotes (with links)
    4. Suggested Investigation (product questions)
    5. Acceptance Criteria (validation approach)

    Args:
        theme_name: Theme name
        excerpts: List of excerpt dicts with keys:
            - source: "intercom" or "coda"
            - text: excerpt text
            - source_metadata: source-specific metadata
        participant_count: Number of research participants
        theme_type: pain_point, feature_request, or insight
        source_breakdown: Dict of counts per source

    Returns:
        Formatted markdown description
    """
    # Theme type label
    type_label = theme_type.replace("_", " ").title()

    # Build description header
    description = f"""## Theme Summary

**Theme**: {theme_name.replace('_', ' ').title()}
**Type**: {type_label}
**Participants**: {participant_count}

### Source Breakdown
"""

    # Add source breakdown
    for source, count in source_breakdown.items():
        source_label = source.title()
        description += f"- {source_label}: {count}\n"

    description += "\n---\n\n## Representative Quotes\n\n"

    # Add formatted excerpts
    for i, excerpt in enumerate(excerpts[:5], 1):
        source = excerpt.get("source", "unknown")
        text = excerpt.get("text", "")
        metadata = excerpt.get("source_metadata", {})
        conversation_id = excerpt.get("conversation_id")

        formatted = format_excerpt_multi_source(
            source=source,
            text=text,
            conversation_id=conversation_id,
            source_metadata=metadata,
        )
        description += f"### Quote {i}\n{formatted}\n\n"

    # Add investigation section
    description += """---

## Suggested Investigation

- What user needs does this theme reveal?
- How does this align with product strategy?
- What additional validation is needed?
- What are the potential solutions?

---

## Acceptance Criteria

- [ ] Theme validated with additional user research
- [ ] Product opportunity sized and prioritized
- [ ] Solution approach defined
- [ ] Next steps identified

---
*Generated by FeedForward Research Pipeline*
"""
    return description


# Dual-Format Story Output (Phase 3.1)


@dataclass
class DualFormatOutput:
    """
    Output from dual-format story generation.

    Contains separate human-readable and AI agent sections plus combined output.
    """

    human_section: str
    ai_section: str
    combined: str
    format_version: str = "v2"
    codebase_context: Optional[Dict] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)


class DualStoryFormatter:
    """
    Formats stories with dual human/AI sections and codebase context.

    This formatter generates two distinct sections:
    1. Human Section: Engineering story with user story, acceptance criteria,
       symptoms, and investigation guidance
    2. AI Section: Agent task specification with third-person framing,
       codebase context, step-by-step instructions, and guardrails

    Usage:
        formatter = DualStoryFormatter()
        result = formatter.format_story(
            theme_data=theme,
            exploration_result=exploration,
            evidence_data=evidence
        )
        # Returns DualFormatOutput with human_section, ai_section, combined
    """

    def format_story(
        self,
        theme_data: Dict,
        exploration_result: Optional["ExplorationResult"] = None,
        evidence_data: Optional[Dict] = None,
        generated_content: Optional["GeneratedStoryContent"] = None,
        code_context: Optional[Dict[str, Any]] = None,
    ) -> DualFormatOutput:
        """
        Generate complete dual-format story.

        Args:
            theme_data: Theme metadata dict with keys:
                - title: Story title
                - issue_signature: Theme signature
                - product_area: Product area affected
                - component: Technical component
                - user_intent: What user is trying to do
                - symptoms: List of reported symptoms
                - root_cause_hypothesis: Analysis of root cause
                - occurrences: Number of reports
                - first_seen: First report date
                - last_seen: Last report date
                - user_type: (optional) Persona for user story "As a" clause
                - benefit: (optional) Benefit for user story "So that" clause
            exploration_result: Optional codebase exploration results
            evidence_data: Optional evidence dict with:
                - samples: List of conversation samples
                - customer_messages: List of customer messages
            generated_content: Optional LLM-generated content for user story and AI goal.
                             If provided, uses generated user_type, user_story_want,
                             user_story_benefit for user story, and ai_agent_goal for
                             AI section.
            code_context: Optional dict with pre-explored codebase context.
                         If provided and success=True, used instead of exploration_result.
                         This avoids redundant exploration when context already exists.

        Returns:
            DualFormatOutput with human_section, ai_section, and combined text
        """
        human_section = self.format_human_section(theme_data, evidence_data, generated_content)
        ai_section = self.format_ai_section(
            theme_data, exploration_result, generated_content, code_context
        )

        # Combine sections with separator
        combined = f"{human_section}\n\n---\n\n{ai_section}"

        # Serialize codebase context for metadata
        codebase_context = None
        if exploration_result:
            codebase_context = {
                "relevant_files": [
                    {
                        "path": f.path,
                        "line_start": f.line_start,
                        "line_end": f.line_end,
                        "relevance": f.relevance,
                    }
                    for f in exploration_result.relevant_files
                ],
                "code_snippets": [
                    {
                        "file_path": s.file_path,
                        "line_start": s.line_start,
                        "line_end": s.line_end,
                        "language": s.language,
                        "context": s.context,
                    }
                    for s in exploration_result.code_snippets
                ],
                "investigation_queries": exploration_result.investigation_queries,
            }

        return DualFormatOutput(
            human_section=human_section,
            ai_section=ai_section,
            combined=combined,
            format_version="v2",
            codebase_context=codebase_context,
        )

    def format_human_section(
        self,
        theme_data: Dict,
        evidence_data: Optional[Dict] = None,
        generated_content: Optional["GeneratedStoryContent"] = None,
    ) -> str:
        """
        Generate human-readable engineering story section.

        Args:
            theme_data: Theme metadata dict
            evidence_data: Optional evidence dict with samples and messages
            generated_content: Optional LLM-generated content for user story fields

        Returns:
            Formatted markdown for human section
        """
        title = theme_data.get("title", theme_data.get("issue_signature", "Untitled Story"))
        product_area = theme_data.get("product_area", "Unknown")
        component = theme_data.get("component", "Unknown")
        user_intent = theme_data.get("user_intent", "")
        symptoms = theme_data.get("symptoms", [])
        root_cause = theme_data.get("root_cause_hypothesis", "")
        occurrences = theme_data.get("occurrences", 0)
        first_seen = theme_data.get("first_seen", "")
        last_seen = theme_data.get("last_seen", "")

        # Format title
        display_title = title.replace("_", " ").title()

        # Build user story with generated content if available
        user_story = self._format_user_story(theme_data, generated_content)

        # Build context section
        context = f"""## Context

- **Product Area**: {product_area}
- **Component**: {component}
- **User Journey Step**: {theme_data.get('user_journey_step', 'Unknown')}
- **Dependencies**: {theme_data.get('dependencies', 'To be determined')}
- **Related Conversations**: {occurrences} customer reports ({first_seen} - {last_seen})"""

        # Build acceptance criteria (with generated content if available)
        acceptance_criteria = self._format_acceptance_criteria(theme_data, generated_content)

        # Build symptoms section
        symptoms_section = self._format_symptoms(symptoms)

        # Build root cause section
        root_cause_section = ""
        if root_cause:
            root_cause_section = f"""## Root Cause Hypothesis

{root_cause}"""

        # Build technical notes (with generated content if available)
        technical_notes = self._format_technical_notes(theme_data, generated_content)

        # Build sample messages
        sample_messages = self._format_sample_messages(evidence_data)

        # Build suggested investigation (with generated content if available)
        suggested_investigation = self._format_suggested_investigation(theme_data, generated_content)

        # Assemble human section
        # NOTE: INVEST Check removed per issue #133 - pre-checked boxes provide false confidence
        sections = [
            f"## SECTION 1: Human-Facing Story\n",
            f"# Story: {display_title}\n",
            user_story,
            context,
            acceptance_criteria,
            symptoms_section,
            root_cause_section,
            technical_notes,
            sample_messages,
            suggested_investigation,
        ]

        return "\n\n".join([s for s in sections if s])

    def format_ai_section(
        self,
        theme_data: Dict,
        exploration_result: Optional["ExplorationResult"] = None,
        generated_content: Optional["GeneratedStoryContent"] = None,
        code_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate AI agent task specification section.

        Uses third-person framing ("This card is for..." instead of "You are...").

        Args:
            theme_data: Theme metadata dict
            exploration_result: Optional codebase exploration results
            generated_content: Optional LLM-generated content for AI goal
            code_context: Optional dict with pre-explored codebase context.
                         Preferred over exploration_result when success=True.

        Returns:
            Formatted markdown for AI section
        """
        title = theme_data.get("title", theme_data.get("issue_signature", "Untitled Task"))
        display_title = title.replace("_", " ").title()
        component = theme_data.get("component", "Unknown")
        product_area = theme_data.get("product_area", "Unknown")
        occurrences = theme_data.get("occurrences", 0)

        # Role & Context (third-person)
        # Repository comes from theme_data or defaults to "TBD"
        target_repo = theme_data.get("target_repo", "TBD (requires codebase mapping)")
        engineer_type = theme_data.get("engineer_type", "senior backend engineer")

        role_section = f"""## Role & Context

This card is for a **{engineer_type}** working in the target codebase.
Follow project conventions in `CLAUDE.md` and established patterns.

**Repository**: {target_repo}
**Task Type**: {theme_data.get('task_type', 'bug-fix')}
**Related Story**: See Human-Facing Section above
**Priority**: {self._determine_priority(occurrences)}"""

        # Goal - use generated ai_agent_goal if available, otherwise fall back to user_intent
        goal_text = theme_data.get('user_intent', 'Fix the reported issue and restore expected functionality.')
        if generated_content and generated_content.ai_agent_goal:
            goal_text = generated_content.ai_agent_goal

        goal_section = f"""## Goal (Single Responsibility)

{goal_text}"""

        # Context & Architecture (with codebase context)
        # Priority: code_context (pre-explored dict) > exploration_result (dataclass)
        if code_context and code_context.get("success"):
            architecture_section = self.format_codebase_context_from_dict(code_context)
        elif exploration_result:
            architecture_section = self.format_codebase_context(exploration_result)
        else:
            architecture_section = """## Context & Architecture

### Architecture Notes:

- Investigation needed to identify relevant files
- Review codebase for components related to this issue

### Business Rules:

- Follow established patterns in the codebase
- Maintain backward compatibility"""

        # Success Criteria (with generated content if available)
        success_criteria = self._format_success_criteria(theme_data, generated_content)

        # Extended Thinking
        extended_thinking = self._format_extended_thinking(theme_data)

        # Metadata footer
        metadata = self._format_metadata(theme_data)

        # Assemble AI section
        # NOTE: Instructions and Guardrails removed per issue #133 - generic workflow
        # steps that AI agents already know from CLAUDE.md
        sections = [
            f"## SECTION 2: AI Agent Task Specification\n",
            f"# Agent Task: {display_title}\n",
            role_section,
            goal_section,
            architecture_section,
            success_criteria,
            extended_thinking,
            metadata,
        ]

        return "\n\n".join([s for s in sections if s])

    def format_codebase_context(
        self,
        exploration_result: "ExplorationResult",
    ) -> str:
        """
        Format codebase exploration results for AI section.

        Args:
            exploration_result: ExplorationResult from codebase exploration

        Returns:
            Formatted markdown with file references, snippets, and queries
        """
        if not exploration_result or not exploration_result.success:
            return """## Context & Architecture

### Architecture Notes:

- Codebase exploration unavailable
- Manual investigation required"""

        sections = ["## Context & Architecture"]

        # Relevant Files
        if exploration_result.relevant_files:
            sections.append("### Relevant Files:\n")
            for ref in exploration_result.relevant_files[:10]:  # Top 10
                line_info = ""
                if ref.line_start:
                    if ref.line_end:
                        line_info = f" (lines {ref.line_start}-{ref.line_end})"
                    else:
                        line_info = f" (line {ref.line_start})"

                relevance = f" - {ref.relevance}" if ref.relevance else ""
                sections.append(f"- `{ref.path}`{line_info}{relevance}")

        # Code Snippets
        if exploration_result.code_snippets:
            sections.append("\n### Code Snippets:\n")
            for i, snippet in enumerate(exploration_result.code_snippets[:3], 1):  # Top 3
                sections.append(f"**{i}. {snippet.file_path}** (lines {snippet.line_start}-{snippet.line_end})")
                if snippet.context:
                    sections.append(f"Context: {snippet.context}\n")
                sections.append(f"```{snippet.language}\n{snippet.content}\n```\n")

        # Investigation Queries
        if exploration_result.investigation_queries:
            sections.append("### Suggested Investigation:\n")
            for query in exploration_result.investigation_queries:
                sections.append(f"```\n{query}\n```")

        return "\n".join(sections)

    def format_codebase_context_from_dict(
        self,
        code_context: Dict[str, Any],
    ) -> str:
        """
        Format codebase context directly from stored dict.

        This method consumes the code_context dict stored in the database,
        avoiding the need to reconstruct an ExplorationResult dataclass.

        Args:
            code_context: Dict with keys:
                - success: bool
                - relevant_files: List[Dict] with path, line_start, line_end, relevance
                - code_snippets: List[Dict] with file_path, line_start, line_end,
                                 content, language, context

        Returns:
            Formatted markdown with file references and snippets
        """
        if not code_context or not code_context.get("success"):
            return """## Context & Architecture

### Architecture Notes:

- Codebase exploration unavailable
- Manual investigation required"""

        sections = ["## Context & Architecture"]

        # Relevant Files (handle missing/empty gracefully)
        relevant_files = code_context.get("relevant_files") or []
        if relevant_files:
            sections.append("### Relevant Files:\n")
            for ref in relevant_files[:10]:  # Top 10
                if not isinstance(ref, dict) or not ref.get("path"):
                    continue
                line_info = ""
                if ref.get("line_start"):
                    if ref.get("line_end"):
                        line_info = f" (lines {ref['line_start']}-{ref['line_end']})"
                    else:
                        line_info = f" (line {ref['line_start']})"
                relevance = f" - {ref['relevance']}" if ref.get("relevance") else ""
                sections.append(f"- `{ref['path']}`{line_info}{relevance}")

        # Code Snippets (handle missing/empty gracefully)
        code_snippets = code_context.get("code_snippets") or []
        if code_snippets:
            sections.append("\n### Code Snippets:\n")
            for i, snippet in enumerate(code_snippets[:3], 1):  # Top 3
                if not isinstance(snippet, dict) or not snippet.get("file_path"):
                    continue
                line_start = snippet.get("line_start")
                line_end = snippet.get("line_end")
                # Only show line info if we have valid values
                if line_start and line_end:
                    line_info = f" (lines {line_start}-{line_end})"
                elif line_start:
                    line_info = f" (line {line_start})"
                else:
                    line_info = ""
                sections.append(
                    f"**{i}. {snippet['file_path']}**{line_info}"
                )
                if snippet.get("context"):
                    sections.append(f"Context: {snippet['context']}\n")
                language = snippet.get("language", "python")
                content = snippet.get("content", "")
                sections.append(f"```{language}\n{content}\n```\n")

        return "\n".join(sections)

    def _format_user_story(
        self,
        theme_data: Dict,
        generated_content: Optional["GeneratedStoryContent"] = None,
    ) -> str:
        """
        Format user story in As a.../I want.../So that... format.

        Args:
            theme_data: Theme metadata dict with optional user_type and benefit keys
            generated_content: Optional LLM-generated content with user_type,
                             user_story_want, and user_story_benefit

        Returns:
            Formatted user story markdown
        """
        # Start with theme_data defaults (which may already include generated values)
        user_type = theme_data.get("user_type", "Tailwind user")
        user_intent = theme_data.get("user_intent", "use the product successfully")
        benefit = theme_data.get("benefit", "achieve my goals without friction")

        # Override with generated content if available (higher priority)
        if generated_content:
            if generated_content.user_type:
                user_type = generated_content.user_type
            if generated_content.user_story_want:
                user_intent = generated_content.user_story_want
            if generated_content.user_story_benefit:
                benefit = generated_content.user_story_benefit

        return f"""## User Story

As a **{user_type}**
I want **{user_intent}**
So that **{benefit}**"""

    def _format_acceptance_criteria(
        self,
        theme_data: Dict,
        generated_content: Optional["GeneratedStoryContent"] = None,
    ) -> str:
        """Format acceptance criteria - prefer generated over defaults."""
        # Use generated criteria if available
        if generated_content and generated_content.acceptance_criteria:
            criteria = generated_content.acceptance_criteria
        else:
            # Fallback to theme_data or defaults (for backward compatibility)
            criteria = theme_data.get("acceptance_criteria", [
                "Given the reported conditions, When the user performs the action, Then the expected behavior occurs",
            ])

        formatted_criteria = []
        for criterion in criteria:
            # Add checkbox if not already present
            if not criterion.strip().startswith("- ["):
                formatted_criteria.append(f"- [ ] {criterion}")
            else:
                formatted_criteria.append(criterion)

        return f"""## Acceptance Criteria

{chr(10).join(formatted_criteria)}"""

    def _format_symptoms(self, symptoms: List[str]) -> str:
        """Format symptoms section."""
        if not symptoms:
            return ""

        formatted_symptoms = []
        for symptom in symptoms:
            # Use markdown checkbox syntax for consistent rendering
            # Negative symptoms get unchecked box, positive get checked
            if any(word in symptom.lower() for word in ["does not", "do not", "don't", "fails", "missing", "incorrect", "not working"]):
                formatted_symptoms.append(f"- [ ] {symptom}")
            elif any(word in symptom.lower() for word in ["works", "successful", "correct"]):
                formatted_symptoms.append(f"- [x] {symptom}")
            else:
                formatted_symptoms.append(f"- {symptom}")

        return f"""## Symptoms (Customer Reported)

{chr(10).join(formatted_symptoms)}"""

    def _format_sample_messages(self, evidence_data: Optional[Dict]) -> str:
        """Format sample customer messages."""
        if not evidence_data or "customer_messages" not in evidence_data:
            return ""

        messages = evidence_data.get("customer_messages", [])[:3]  # Top 3
        if not messages:
            return ""

        formatted_messages = []
        for msg in messages:
            # Extract text from message dict or use string directly
            text = msg.get("text", msg) if isinstance(msg, dict) else msg
            formatted_messages.append(f'> "{text}"')

        return f"""## Sample Customer Messages

{chr(10).join(formatted_messages)}"""

    def _format_suggested_investigation(
        self,
        theme_data: Dict,
        generated_content: Optional["GeneratedStoryContent"] = None,
    ) -> str:
        """Format investigation steps - prefer generated over defaults."""
        if generated_content and generated_content.investigation_steps:
            steps = generated_content.investigation_steps
        else:
            component = theme_data.get("component", "the relevant component")
            product_area = theme_data.get("product_area", "this area")
            steps = [
                f"Review `{component}` code for issues matching symptoms",
                f"Check logs for errors in {product_area} flow",
            ]

        formatted_steps = [f"{i}. {step}" for i, step in enumerate(steps, 1)]

        return f"""## Suggested Investigation

{chr(10).join(formatted_steps)}"""

    def _format_technical_notes(
        self,
        theme_data: Dict,
        generated_content: Optional["GeneratedStoryContent"] = None,
    ) -> str:
        """Format technical notes - prefer generated over defaults."""
        if generated_content and generated_content.technical_notes:
            return f"""## Technical Notes

{generated_content.technical_notes}"""
        else:
            component = theme_data.get("component", "Unknown")
            return f"""## Technical Notes

- **Target Components**: `{component}` module
- **Testing Expectations**: Integration test covering the relevant flow
- **Vertical Slice**: {theme_data.get('vertical_slice', 'Backend -> Frontend')}"""

    def _format_instructions(self, theme_data: Dict) -> str:
        """Format step-by-step instructions for AI agent."""
        component = theme_data.get("component", "the component")

        default_steps = [
            f"**Analyze** the {component} code",
            "**Reproduce** using test data",
            "**Identify** the root cause",
            "**Implement** the fix with minimal changes",
            "**Add/Update Tests** covering the fix",
            "**Verify** by running the full test suite",
        ]

        steps = theme_data.get("implementation_steps", default_steps)
        formatted_steps = [f"{i}. {step}" for i, step in enumerate(steps, 1)]

        return f"""## Instructions (Step-by-Step)

{chr(10).join(formatted_steps)}"""

    def _format_success_criteria(
        self,
        theme_data: Dict,
        generated_content: Optional["GeneratedStoryContent"] = None,
    ) -> str:
        """Format success criteria - prefer generated over defaults."""
        if generated_content and generated_content.success_criteria:
            criteria = generated_content.success_criteria
        else:
            criteria = [
                "Issue is resolved and functionality works as expected",
                "All existing tests pass (no regressions)",
            ]

        formatted = [f"- [ ] {c}" for c in criteria]

        return f"""## Success Criteria (Explicit & Observable)

{chr(10).join(formatted)}"""

    def _format_guardrails(self, theme_data: Dict) -> str:
        """Format guardrails and constraints for AI agent."""
        component = theme_data.get("component", "components")

        do_not = theme_data.get("do_not", [
            "Make changes without tests",
            "Modify database schema without migration",
            "Deploy without testing in staging",
            f"Make changes affecting unrelated {component}",
        ])

        always = theme_data.get("always", [
            "Write tests before/with the fix",
            "Preserve existing functionality",
            "Log key state transitions",
            "Consider edge cases and error handling",
        ])

        do_not_formatted = [f"- {item}" for item in do_not]
        always_formatted = [f"- {item}" for item in always]

        return f"""## Guardrails & Constraints

### DO NOT:

{chr(10).join(do_not_formatted)}

### ALWAYS:

{chr(10).join(always_formatted)}"""

    def _format_extended_thinking(self, theme_data: Dict) -> str:
        """Format extended thinking guidance."""
        occurrences = theme_data.get("occurrences", 0)
        duration_days = self._calculate_duration_days(
            theme_data.get("first_seen"), theme_data.get("last_seen")
        )

        context_notes = []

        if duration_days and duration_days > 30:
            context_notes.append(
                f"This issue has persisted for {duration_days} days affecting {occurrences} customers."
            )
            context_notes.append(
                "**Why didn't previous investigations catch it?** - May be timing-dependent or data-dependent"
            )

        if occurrences > 5:
            context_notes.append(
                f"**High volume** - {occurrences} reports suggest widespread impact"
            )

        context_notes.append("Take time to understand the full data flow before implementing a fix.")

        return f"""## Extended Thinking Guidance

{chr(10).join(f'- {note}' if not note.startswith('**') else note for note in context_notes)}"""

    def _format_metadata(self, theme_data: Dict) -> str:
        """Format metadata footer."""
        issue_signature = theme_data.get("issue_signature", "unknown")
        occurrences = theme_data.get("occurrences", 0)
        first_seen = theme_data.get("first_seen", "")
        last_seen = theme_data.get("last_seen", "")

        return f"""---

## Metadata

| Field               | Value                       |
| ------------------- | --------------------------- |
| **Issue Signature** | `{issue_signature}`         |
| **Occurrences**     | {occurrences}               |
| **First Seen**      | {first_seen}                |
| **Last Seen**       | {last_seen}                 |
| **Generated By**    | FeedForward Pipeline v2.0   |

---

_Generated by FeedForward Dual-Format Story Generator_"""

    def _determine_priority(self, occurrences: int) -> str:
        """Determine priority label based on occurrences."""
        if occurrences >= 10:
            return "High (10+ customer reports)"
        elif occurrences >= 5:
            return "Medium (5-9 customer reports)"
        elif occurrences >= 2:
            return "Low-Medium (2-4 customer reports)"
        else:
            return "Low (1 customer report)"

    def _calculate_duration_days(
        self, first_seen: Optional[str], last_seen: Optional[str]
    ) -> Optional[int]:
        """Calculate duration in days between first and last seen."""
        if not first_seen or not last_seen:
            return None

        try:
            # Try parsing ISO format dates
            from datetime import datetime as dt

            first = dt.fromisoformat(first_seen.replace("Z", "+00:00"))
            last = dt.fromisoformat(last_seen.replace("Z", "+00:00"))
            return (last - first).days
        except (ValueError, AttributeError):
            return None

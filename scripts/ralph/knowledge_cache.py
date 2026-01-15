#!/usr/bin/env python3
"""
Knowledge Cache - Learning system for story generation.

This module manages the Tailwind codebase knowledge that feeds into story generation.
It captures patterns from scoping validation and makes them available for future runs.

Usage:
    # Update knowledge with scoping results
    from knowledge_cache import update_knowledge_from_scoping
    update_knowledge_from_scoping(scoping_results)

    # Load knowledge for story generation
    from knowledge_cache import load_knowledge_for_generation
    context = load_knowledge_for_generation(feedback_text)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CODEBASE_MAP_PATH = PROJECT_ROOT / "docs" / "tailwind-codebase-map.md"
LEARNED_PATTERNS_PATH = SCRIPT_DIR / "learned_patterns.json"

# Configuration constants
MAX_PATTERN_PREVIEW_LENGTH = 60  # Characters to show in console preview
MAX_FINDING_LENGTH = 200  # Max chars for service findings
SIMILARITY_THRESHOLD = 0.7  # Jaccard similarity for duplicate detection
MAX_RELEVANT_LINES = 200  # Max lines to extract from codebase map
MAX_PATTERNS_TO_DISPLAY = 5  # Max patterns per category (good/bad)
MAX_SCOPING_RULES = 10  # Max scoping rules to include
MAX_INSIGHTS_PER_SERVICE = 50  # Max insights to keep per service
CHARS_PER_TOKEN = 4  # Rough estimate for token calculation


def load_learned_patterns() -> Dict[str, Any]:
    """Load previously learned patterns from JSON file."""
    if LEARNED_PATTERNS_PATH.exists():
        try:
            with open(LEARNED_PATTERNS_PATH) as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load learned patterns from {LEARNED_PATTERNS_PATH}: {e}")
            # Fall through to return empty structure
    return {
        "version": "1.0",
        "last_updated": None,
        "patterns": [],
        "service_insights": {},
        "scoping_rules": []
    }


def save_learned_patterns(patterns: Dict[str, Any]) -> None:
    """Save learned patterns to JSON file."""
    patterns["last_updated"] = datetime.now().isoformat()
    try:
        with open(LEARNED_PATTERNS_PATH, "w") as f:
            json.dump(patterns, f, indent=2, default=str)
        print(f"  Saved learned patterns to {LEARNED_PATTERNS_PATH}")
    except IOError as e:
        print(f"  Error: Could not save learned patterns to {LEARNED_PATTERNS_PATH}: {e}")
        raise


def update_knowledge_from_scoping(scoping_results: Dict[str, Any]) -> None:
    """
    Update the knowledge cache with patterns discovered during scoping validation.

    Args:
        scoping_results: Output from validate_scoping.py containing:
            - discovered_patterns: List of good/bad patterns
            - results: Per-story evaluation with code_evidence
    """
    patterns = load_learned_patterns()

    # Extract discovered patterns
    discovered = scoping_results.get("discovered_patterns", [])
    new_patterns_count = 0

    for pattern in discovered:
        pattern_desc = pattern.get("description", "")

        # Check if we already have this pattern (fuzzy match)
        is_duplicate = any(
            _similar_patterns(pattern_desc, existing.get("description", ""))
            for existing in patterns["patterns"]
        )

        if not is_duplicate and pattern_desc:
            patterns["patterns"].append({
                "type": pattern.get("pattern_type", "unknown"),
                "description": pattern_desc,
                "example": pattern.get("example", ""),
                "discovered_at": datetime.now().isoformat(),
                "source": "scoping_validation"
            })
            new_patterns_count += 1
            print(f"  + New pattern: {pattern_desc[:MAX_PATTERN_PREVIEW_LENGTH]}...")

    # Extract service insights from code_evidence
    for result in scoping_results.get("results", []):
        code_evidence = result.get("code_evidence", {})
        key_findings = code_evidence.get("key_findings", "")

        if key_findings and len(key_findings) > 20:
            # Extract service mentions
            services = _extract_service_mentions(key_findings)
            for service in services:
                if service not in patterns["service_insights"]:
                    patterns["service_insights"][service] = []

                insights = patterns["service_insights"][service]
                insights.append({
                    "finding": key_findings[:MAX_FINDING_LENGTH],
                    "discovered_at": datetime.now().isoformat()
                })

                # Keep only the most recent N insights to prevent unbounded growth
                if len(insights) > MAX_INSIGHTS_PER_SERVICE:
                    patterns["service_insights"][service] = insights[-MAX_INSIGHTS_PER_SERVICE:]

    # Extract scoping rules from recommendations
    for result in scoping_results.get("results", []):
        recommendation = result.get("recommendation", "")
        detail = result.get("recommendation_detail", "")

        if recommendation in ["SPLIT", "MERGE"] and detail:
            rule = {
                "action": recommendation,
                "detail": detail,
                "root_cause": result.get("root_cause_analysis", {}).get("shared_root_cause", ""),
                "discovered_at": datetime.now().isoformat()
            }

            # Check for duplicate rules
            is_duplicate = any(
                _similar_patterns(detail, r.get("detail", ""))
                for r in patterns["scoping_rules"]
            )

            if not is_duplicate:
                patterns["scoping_rules"].append(rule)
                print(f"  + New scoping rule: {recommendation} - {detail[:50]}...")

    if new_patterns_count > 0:
        save_learned_patterns(patterns)
        print(f"  Updated knowledge cache with {new_patterns_count} new patterns")
    else:
        print("  No new patterns to add to knowledge cache")


def load_knowledge_for_generation(
    feedback_text: str,
    max_chars: int = 32000  # ~8000 tokens at 4 chars/token
) -> str:
    """
    Load relevant knowledge for story generation based on the feedback content.

    Args:
        feedback_text: The feedback being processed (used for relevance filtering)
        max_chars: Approximate max characters for the knowledge context (~4 chars/token)

    Returns:
        Formatted knowledge string to include in story generation prompt
    """
    sections = []

    # 1. Load the core codebase map (truncated if needed)
    if CODEBASE_MAP_PATH.exists():
        try:
            codebase_map = CODEBASE_MAP_PATH.read_text()
        except IOError as e:
            print(f"Warning: Could not read codebase map from {CODEBASE_MAP_PATH}: {e}")
            codebase_map = ""

        # Extract most relevant sections based on feedback keywords
        keywords = _extract_keywords(feedback_text)
        relevant_sections = _extract_relevant_sections(codebase_map, keywords) if codebase_map else ""

        if relevant_sections:
            sections.append("## Relevant Codebase Knowledge\n\n" + relevant_sections)
        else:
            # If no specific matches, include the summary sections
            sections.append(_extract_summary_sections(codebase_map))

    # 2. Load learned patterns
    patterns = load_learned_patterns()

    if patterns["patterns"]:
        pattern_section = "## Learned Patterns (from validation)\n\n"

        # Prioritize bad patterns (things to avoid)
        bad_patterns = [p for p in patterns["patterns"] if p.get("type") == "bad_pattern"]
        good_patterns = [p for p in patterns["patterns"] if p.get("type") == "good_pattern"]

        if bad_patterns:
            pattern_section += "### Avoid These Patterns\n\n"
            for p in bad_patterns[:5]:  # Limit to top 5
                pattern_section += f"- **DON'T**: {p.get('description', '')}\n"
                if p.get("example"):
                    pattern_section += f"  - Example: {p.get('example')}\n"

        if good_patterns:
            pattern_section += "\n### Follow These Patterns\n\n"
            for p in good_patterns[:5]:  # Limit to top 5
                pattern_section += f"- **DO**: {p.get('description', '')}\n"

        sections.append(pattern_section)

    # 3. Load scoping rules
    if patterns.get("scoping_rules"):
        rules_section = "## Story Scoping Rules\n\n"
        for rule in patterns["scoping_rules"][:10]:  # Limit to top 10
            action = rule.get("action", "")
            detail = rule.get("detail", "")
            if action == "SPLIT":
                rules_section += f"- **SPLIT stories when**: {detail}\n"
            elif action == "MERGE":
                rules_section += f"- **MERGE stories when**: {detail}\n"
        sections.append(rules_section)

    # 4. Load service-specific insights if relevant
    if patterns.get("service_insights"):
        # Check which services are mentioned in the feedback
        services_mentioned = _extract_service_mentions(feedback_text)
        relevant_insights = []

        for service in services_mentioned:
            if service in patterns["service_insights"]:
                insights = patterns["service_insights"][service]
                if insights:
                    latest = insights[-1]  # Get most recent
                    relevant_insights.append(f"- **{service}**: {latest.get('finding', '')}")

        if relevant_insights:
            sections.append("## Service-Specific Insights\n\n" + "\n".join(relevant_insights))

    # Combine and truncate if needed
    combined = "\n\n".join(sections)

    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n[... truncated for length]"

    return combined


def _extract_keywords(text: str) -> List[str]:
    """Extract relevant keywords from feedback text."""
    # Common Tailwind-related keywords
    keyword_patterns = [
        r'\b(pinterest|pin|board|schedule|publish)\b',
        r'\b(facebook|instagram|meta|oauth)\b',
        r'\b(ghostwriter|ai|generate|text)\b',
        r'\b(login|auth|token|access)\b',
        r'\b(billing|subscription|cancel|plan)\b',
        r'\b(image|upload|photo|video)\b',
        r'\b(template|design|create)\b',
        r'\b(product|shop|store|ecommerce)\b',
        r'\b(turbo|community|tribe)\b',
        r'\b(scheduler|draft|queue)\b',
        r'\b(smartbio|link|bio)\b',
    ]

    keywords = []
    text_lower = text.lower()

    for pattern in keyword_patterns:
        matches = re.findall(pattern, text_lower)
        keywords.extend(matches)

    return list(set(keywords))


def _extract_service_mentions(text: str) -> List[str]:
    """Extract Tailwind service names mentioned in text."""
    services = [
        "tack", "zuck", "gandalf", "ghostwriter", "pablo",
        "scooby", "dolly", "charlotte", "brandy2", "swanson",
        "aero", "bach", "bachv2", "bachv3", "roundabout"
    ]

    mentioned = []
    text_lower = text.lower()

    for service in services:
        if service in text_lower:
            mentioned.append(service)

    return mentioned


def _extract_relevant_sections(codebase_map: str, keywords: List[str]) -> str:
    """Extract sections from codebase map relevant to the keywords."""
    relevant_lines = []
    lines = codebase_map.split("\n")

    # Track section headers
    current_section = ""
    section_included = False

    for i, line in enumerate(lines):
        # Check if this is a section header
        if line.startswith("##"):
            current_section = line
            section_included = False

        # Check if line contains any keywords
        line_lower = line.lower()
        for keyword in keywords:
            if keyword.lower() in line_lower:
                # Include section header if not already
                if not section_included and current_section:
                    relevant_lines.append(current_section)
                    section_included = True

                # Include context (line before and after if available)
                if i > 0 and lines[i-1] not in relevant_lines:
                    relevant_lines.append(lines[i-1])
                relevant_lines.append(line)
                if i < len(lines) - 1:
                    relevant_lines.append(lines[i+1])
                break

    return "\n".join(relevant_lines[:200])  # Limit output


def _extract_summary_sections(codebase_map: str) -> str:
    """Extract just the summary sections from codebase map."""
    summary = "## Tailwind Codebase Summary\n\n"

    # Try to find and include key sections
    sections_to_include = [
        "Executive Summary",
        "API Domain to Repository Mapping",
        "Feature to Repository Mapping"
    ]

    for section_name in sections_to_include:
        start = codebase_map.find(f"## {section_name}")
        if start >= 0:
            # Find next section
            next_section = codebase_map.find("\n## ", start + 1)
            if next_section > start:
                summary += codebase_map[start:next_section] + "\n\n"
            else:
                summary += codebase_map[start:start+1000] + "\n\n"

    return summary[:6000]  # Limit to ~1500 tokens


def _similar_patterns(pattern1: str, pattern2: str) -> bool:
    """Check if two patterns are similar (to avoid duplicates)."""
    if not pattern1 or not pattern2:
        return False

    # Normalize and compare
    p1_normalized = pattern1.lower().strip()
    p2_normalized = pattern2.lower().strip()

    # Exact match
    if p1_normalized == p2_normalized:
        return True

    # High overlap (Jaccard similarity)
    words1 = set(p1_normalized.split())
    words2 = set(p2_normalized.split())

    if not words1 or not words2:
        return False

    intersection = len(words1 & words2)
    union = len(words1 | words2)
    similarity = intersection / union

    return similarity > 0.7  # 70% word overlap considered similar


def get_knowledge_stats() -> Dict[str, Any]:
    """Get statistics about the knowledge cache."""
    patterns = load_learned_patterns()

    return {
        "last_updated": patterns.get("last_updated"),
        "total_patterns": len(patterns.get("patterns", [])),
        "bad_patterns": len([p for p in patterns.get("patterns", []) if p.get("type") == "bad_pattern"]),
        "good_patterns": len([p for p in patterns.get("patterns", []) if p.get("type") == "good_pattern"]),
        "scoping_rules": len(patterns.get("scoping_rules", [])),
        "services_with_insights": len(patterns.get("service_insights", {})),
        "codebase_map_exists": CODEBASE_MAP_PATH.exists()
    }


if __name__ == "__main__":
    # Print knowledge cache stats
    stats = get_knowledge_stats()
    print("Knowledge Cache Statistics:")
    print(f"  Last updated: {stats['last_updated'] or 'Never'}")
    print(f"  Total patterns: {stats['total_patterns']}")
    print(f"    - Bad patterns (avoid): {stats['bad_patterns']}")
    print(f"    - Good patterns (follow): {stats['good_patterns']}")
    print(f"  Scoping rules: {stats['scoping_rules']}")
    print(f"  Services with insights: {stats['services_with_insights']}")
    print(f"  Codebase map exists: {stats['codebase_map_exists']}")

#!/usr/bin/env python3
"""
Ralph V2 Pipeline Test Harness

Runs the Feed Forward pipeline against test data and evaluates output quality.

Supports two modes:
1. Static mode (default): Uses static test fixtures from manifest.json
2. Live mode (--live): Pulls real data from Intercom, Coda tables, and Coda pages

Usage:
    python3 run_pipeline_test.py [--manifest PATH] [--output PATH]
    python3 run_pipeline_test.py --live [--intercom N] [--coda-tables N] [--coda-pages N]

Example:
    python3 run_pipeline_test.py                          # Static test data
    python3 run_pipeline_test.py --live                   # Live data with defaults
    python3 run_pipeline_test.py --live --intercom 5      # 5 live Intercom conversations
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from openai import OpenAI

# Import live data loader
try:
    from live_data_loader import load_live_test_data
    LIVE_DATA_AVAILABLE = True
except ImportError:
    LIVE_DATA_AVAILABLE = False

# Import knowledge cache for story generation
try:
    from knowledge_cache import load_knowledge_for_generation, update_knowledge_from_scoping
    KNOWLEDGE_CACHE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_CACHE_AVAILABLE = False

# Import cheap mode evaluator for dual-mode evaluation
try:
    from models import Story, DualModeResult, ExpensiveModeResult, CheapModeResult
    from cheap_mode_evaluator import CheapModeEvaluator, compute_cheap_metrics
    CHEAP_MODE_AVAILABLE = True
except ImportError:
    CHEAP_MODE_AVAILABLE = False

# Import pattern learner for learning loop
try:
    from pattern_learner import PatternLearner, run_learning_iteration
    PATTERN_LEARNER_AVAILABLE = True
except ImportError:
    PATTERN_LEARNER_AVAILABLE = False

# Import convergence monitor for self-healing
try:
    from convergence_monitor import ConvergenceMonitor
    CONVERGENCE_MONITOR_AVAILABLE = True
except ImportError:
    CONVERGENCE_MONITOR_AVAILABLE = False


# Constants
SCRIPT_DIR = Path(__file__).parent
DEFAULT_MANIFEST = SCRIPT_DIR / "test_data" / "manifest.json"
GOLD_STANDARD_PATH = PROJECT_ROOT / "docs" / "story_knowledge_base.md"

# Dual-mode evaluation constants
PATTERNS_V1_PATH = SCRIPT_DIR / "learned_patterns.json"
PATTERNS_V2_PATH = SCRIPT_DIR / "learned_patterns_v2.json"
CONVERGENCE_HISTORY_PATH = SCRIPT_DIR / "convergence_history.json"

# Import shared configuration
from ralph_config import GAP_TARGET


def ensure_patterns_v2() -> Path:
    """
    Ensure v2 patterns file exists, migrating from v1 if needed.

    Returns path to v2 patterns file.
    """
    if PATTERNS_V2_PATH.exists():
        return PATTERNS_V2_PATH

    if not PATTERNS_V1_PATH.exists():
        # No patterns at all - create empty v2 file
        from models import LearnedPatternsV2
        empty_v2 = LearnedPatternsV2(
            version="2.0",
            last_updated=datetime.now(),
            patterns=[],
            calibration_history=[]
        )
        with open(PATTERNS_V2_PATH, "w") as f:
            json.dump(empty_v2.model_dump(mode="json"), f, indent=2, default=str)
        return PATTERNS_V2_PATH

    # Migrate v1 to v2
    from pattern_migrator import migrate_patterns_file
    result = migrate_patterns_file(PATTERNS_V1_PATH, PATTERNS_V2_PATH, backup=True)
    print(f"  Migrated patterns: {result}")
    return PATTERNS_V2_PATH


def story_dict_to_model(story_dict: Dict[str, Any], source_id: str) -> Optional["Story"]:
    """
    Convert a story dict (pipeline output) to Story model for cheap mode evaluation.

    Extracts structured fields from the story content markdown.
    """
    if not CHEAP_MODE_AVAILABLE:
        return None

    content = story_dict.get("content", "")
    if not content:
        return None

    # Extract title (first # heading)
    import re
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1) if title_match else "Untitled Story"

    # Extract acceptance criteria (lines starting with - [ ] or numbered under AC section)
    ac_section = re.search(
        r"##\s+Acceptance Criteria\s*([\s\S]*?)(?=##|\Z)",
        content,
        re.IGNORECASE
    )
    acceptance_criteria = []
    if ac_section:
        ac_text = ac_section.group(1)
        # Match checkbox items or numbered items
        ac_matches = re.findall(r"[-*]\s*\[.\]\s*(.+)|^\d+\.\s+(.+)", ac_text, re.MULTILINE)
        acceptance_criteria = [m[0] or m[1] for m in ac_matches if m[0] or m[1]]

    # Extract technical area (from Technical Context section)
    tech_match = re.search(
        r"##\s+Technical Context\s*([\s\S]*?)(?=##|\Z)",
        content,
        re.IGNORECASE
    )
    technical_area = ""
    if tech_match:
        technical_area = tech_match.group(1).strip()[:500]

    # Use full content as description (truncated)
    description = content[:5000]

    return Story(
        id=source_id,
        title=title[:200],
        description=description,
        acceptance_criteria=acceptance_criteria[:50],
        technical_area=technical_area if technical_area else None,
    )


def evaluate_cheap_mode(
    story_dict: Dict[str, Any],
    source_id: str,
    evaluator: Optional["CheapModeEvaluator"] = None
) -> Dict[str, Any]:
    """
    Evaluate a story using cheap (pattern-based) mode.

    Returns dict with cheap_score and details.
    """
    if not CHEAP_MODE_AVAILABLE or evaluator is None:
        return {
            "cheap_score": 0,
            "cheap_available": False,
            "reasons": ["cheap_mode_not_available"]
        }

    story_model = story_dict_to_model(story_dict, source_id)
    if story_model is None:
        return {
            "cheap_score": 0,
            "cheap_available": True,
            "reasons": ["story_conversion_failed"]
        }

    result = evaluator.evaluate_story(story_model)

    return {
        "cheap_score": result.gestalt,
        "cheap_raw_score": result.raw_score,
        "cheap_available": True,
        "reasons": result.reasons,
        "patterns_matched": result.patterns_matched,
        "patterns_violated": result.patterns_violated,
    }


def build_dual_mode_result(
    story_id: str,
    expensive_eval: Dict[str, Any],
    cheap_result: Dict[str, Any],
) -> Optional["DualModeResult"]:
    """
    Build a DualModeResult from raw evaluation dicts.

    Required for pattern learning loop integration.
    """
    if not CHEAP_MODE_AVAILABLE:
        return None

    gestalt = expensive_eval.get("gestalt_score", 0)
    cheap_score = cheap_result.get("cheap_score", 0)

    if gestalt == 0 or cheap_score == 0:
        return None

    expensive = ExpensiveModeResult(
        story_id=story_id,
        gestalt=gestalt,
        reasoning=expensive_eval.get("explanation", ""),
        strengths=expensive_eval.get("strengths", []),
        weaknesses=expensive_eval.get("improvements", []),
    )

    cheap = CheapModeResult(
        story_id=story_id,
        gestalt=cheap_score,
        raw_score=cheap_result.get("cheap_raw_score", 0),
        reasons=cheap_result.get("reasons", []),
        patterns_matched=cheap_result.get("patterns_matched", []),
        patterns_violated=cheap_result.get("patterns_violated", []),
    )

    return DualModeResult(
        story_id=story_id,
        expensive=expensive,
        cheap=cheap,
        gap=round(gestalt - cheap_score, 2),
    )


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load test data manifest."""
    with open(manifest_path) as f:
        return json.load(f)


def load_test_data(source: Dict[str, Any], test_data_dir: Path) -> Dict[str, Any]:
    """
    Load a single test data source.

    Supports two formats:
    1. Static format: Has 'path' key pointing to file in test_data_dir
    2. Live format: Has 'content' key with data inline
    """
    # Live data format - content is inline
    if "content" in source and "path" not in source:
        return {
            "type": source.get("source_type", "unknown"),
            "source_body": source["content"],
            "source_subject": source.get("description", ""),
            "metadata": source.get("metadata", {})
        }

    # Static file format - validate path doesn't escape test_data_dir
    if "path" not in source:
        raise ValueError(f"Source must have either 'content' or 'path': {source.get('id', 'unknown')}")

    path = (test_data_dir / source["path"]).resolve()
    if not path.is_relative_to(test_data_dir.resolve()):
        raise ValueError(f"Path traversal detected: {source['path']}")

    if path.suffix == ".json":
        with open(path) as f:
            return json.load(f)
    elif path.suffix == ".md":
        return {
            "type": "markdown",
            "content": path.read_text(),
            "metadata": source
        }
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")


def load_gold_standard() -> str:
    """Load the gold standard story format documentation."""
    if GOLD_STANDARD_PATH.exists():
        return GOLD_STANDARD_PATH.read_text()
    return "Gold standard not found"


def run_pipeline_on_source(source_data: Dict[str, Any], source_type: str) -> Optional[Dict[str, Any]]:
    """
    Run the Feed Forward pipeline on a single source.

    This is a simplified version that generates stories directly.
    The full pipeline would use theme_extractor.py and story_formatter.py.
    """
    client = OpenAI()

    # Prepare content based on source type
    # Handle both static format (rows/content) and live format (source_body)
    if source_type == "intercom":
        content = f"""
Subject: {source_data.get('source_subject', 'N/A')}

{source_data.get('source_body', '')}
"""
    elif source_type == "coda_table":
        # Static format has 'rows', live format has 'source_body'
        if "rows" in source_data:
            rows = source_data.get("rows", [])
            content = "\n\n".join([
                f"Theme: {row.get('theme_name')}\nParticipants: {row.get('participant_count')}\nVerbatims: {row.get('verbatims')}\nSynthesis: {row.get('synthesis_notes')}"
                for row in rows
            ])
        else:
            content = source_data.get('source_body', source_data.get('content', ''))
    elif source_type == "coda_page":
        content = source_data.get('source_body', source_data.get("content", ""))
    else:
        # Fallback: try source_body first, then content, then stringify
        content = source_data.get('source_body') or source_data.get('content') or str(source_data)

    # Load knowledge context from the learning system
    knowledge_context = ""
    if KNOWLEDGE_CACHE_AVAILABLE:
        try:
            knowledge_context = load_knowledge_for_generation(content, max_chars=16000)  # ~4000 tokens
            if knowledge_context:
                print(f"  Loaded knowledge context ({len(knowledge_context)} chars)")
        except FileNotFoundError as e:
            print(f"  Warning: Knowledge cache file not found (first run?): {e}")
        except json.JSONDecodeError as e:
            print(f"  Warning: Knowledge cache file corrupted, ignoring: {e}")
        except Exception as e:
            print(f"  Warning: Unexpected error loading knowledge context: {type(e).__name__}: {e}")

    # Generate story using the pipeline (improved for quality)
    # Key improvements from gold standard analysis:
    # - Explicit INVEST criteria
    # - Measurable/testable acceptance criteria
    # - Expected outcomes for investigation subtasks
    # - User persona context
    # - Specific technical service mapping for Tailwind
    # - Knowledge from previous scoping validations (learning system)
    prompt = f"""You are a senior product analyst creating an INVEST-compliant engineering story from user feedback.

## User Feedback Content

{content}

## Learned Knowledge (from codebase analysis and validation)

{knowledge_context if knowledge_context else "No cached knowledge available - using built-in architecture knowledge."}

## INVEST Quality Criteria (Your story MUST follow these)

- **I**ndependent: Story can be worked on without blocking on other work
- **N**egotiable: Details can be refined during implementation
- **V**aluable: Clearly delivers value to the user
- **E**stimable: Engineer can estimate effort within a sprint
- **S**mall: Completable in 1-5 days (if larger, split it)
- **T**estable: Every acceptance criterion has a measurable verification method

## Story Format Requirements

Generate a story in this EXACT format:

# [Priority 1-5] [Action Verb] [Specific Feature/Issue]

## Problem Statement

**User Persona:** [Role, e.g., "Pinterest marketer with 10K+ followers"]
**Goal:** What the user is trying to accomplish
**Blocker:** What's preventing them (be specific about error messages, behaviors)
**Impact:** Business/user impact if not fixed (quantify if possible)

## Technical Context

For Tailwind products, map to these services with their dependencies:

**🚨 BEFORE WRITING DEPENDENCY CHAINS, READ THIS 🚨**

If your story is about Pinterest OAuth, Facebook OAuth, or content generation:
- **DO NOT include gandalf** - gandalf is ONLY for internal employee SSO
- Pinterest OAuth chain: `aero → tack → Pinterest API` (NO gandalf)
- Facebook OAuth chain: `aero → zuck → Meta API` (NO gandalf)
- Content generation: `aero (ghostwriter-labs) → ghostwriter` (NO gandalf)

**Service Architecture (VERIFIED against actual codebase):**

IMPORTANT: Verify service responsibilities before referencing them!
- **gandalf**: Handles INTERNAL Tailwind authentication (Google OAuth for employees), NOT Pinterest/Facebook
- **tack**: Pinterest integration - handles Pinterest OAuth, token storage, scheduling
- **zuck**: Facebook/Instagram integration - handles Meta OAuth, token storage
- **aero**: Main monorepo - frontend UI, API routes, AND ALL Ghostwriter generation logic (ghostwriter-labs module + ChatbotGenerator)
- **ghostwriter**: AI text generation backend - ONLY receives prompts from aero and calls LLM. Contains NO business logic.
- **brandy2**: Brand voice/settings data provider - called by AERO, not ghostwriter

**🚨 CRITICAL PRIMARY SERVICE RULE 🚨**

For stories about AI content generation (Ghostwriter chat, pin descriptions, etc.):
- **Primary Service is ALWAYS: tailwind/aero**
- NEVER use "tailwind/ghostwriter" as Primary Service for chat/generation issues
- ghostwriter is just the LLM backend - it doesn't own generation configs or brand voice
- All generation logic lives in aero/packages/core/src/ghostwriter-labs/ and aero/packages/core/src/ghostwriter/

**⚠️ CRITICAL: Brand Voice Architecture (Often Misunderstood):**
- Brand voice injection happens in AERO, not ghostwriter
- Code path: aero/packages/core/src/ghostwriter-labs/generations/*.ts (NOTE: "generations" NOT "generators")
- The `injectPersonalization()` function in aero fetches brand data from brandy2
- Ghostwriter receives the ALREADY-PERSONALIZED prompt from aero
- If a feature "lacks brand voice", the fix is in AERO (add injectPersonalization), NOT ghostwriter

**Dependency chains:**
- **Pinterest OAuth:** aero UI → tack (OAuth handlers) → Pinterest API
- **Facebook OAuth:** aero UI → zuck (OAuth handlers) → Meta Graph API
- **AI/Content Generation:** aero (fetches brand from brandy2, builds prompt) → ghostwriter (LLM call) → returns to aero
- **Scheduling:** aero UI → aero/bachv2 (scheduler client) → tack (pin publishing) → Pinterest API
- **Timezone handling:** aero ONLY (useTimezone hook, TimezoneDate utility, UI components)

**⚠️ NOTE: Timezone code lives in AERO, not tack:**
- Timezone hooks: aero/packages/tailwindapp/client/hooks/use-time-zone.ts
- Timezone utility: aero/packages/tailwindapp/client/utils/timezone-date.ts
- Timezone selector: aero/packages/tailwindapp/client/domains/smart-schedule/components/select-time-zone-section.tsx ⚠️ NOTE: This is in SMART-SCHEDULE domain, NOT scheduler domain!
- **Scheduler toast messages**: aero/packages/tailwindapp/client/domains/scheduler/hooks/use-scheduler-toasts.ts
- **Timeslot display**: aero/packages/tailwindapp/client/domains/scheduler/components/timeslot-radio-group/timeslot-radio-group.tsx
- **Date picker with timeslots**: aero/packages/tailwindapp/client/domains/scheduler/components/date-time-picker-with-timeslots/date-time-picker-with-timeslots.tsx
- tack has ZERO timezone-related code - do NOT reference tack for timezone issues

**🚨 CRITICAL: DOMAIN PATHS IN AERO (VERIFIED) 🚨**

The aero/packages/tailwindapp/client/domains/ directory has SPECIFIC domains. Do NOT invent domain paths:
- ✅ scheduler/ - Pin scheduling UI components (date pickers, timeslots, scheduler toasts)
- ✅ smart-schedule/ - SmartSchedule feature (timezone selector, queue management)
- ✅ pinteresto-auth/ - Pinterest OAuth UI components (connect flow, error pages)
- ❌ timezone/ - DOES NOT EXIST as a domain
- ❌ oauth/ - DOES NOT EXIST as a domain

**COMMON MISTAKE**: select-time-zone-section.tsx is in SMART-SCHEDULE domain, NOT scheduler domain!
- ❌ WRONG: aero/packages/tailwindapp/client/domains/scheduler/components/select-time-zone-section.tsx
- ✅ RIGHT: aero/packages/tailwindapp/client/domains/smart-schedule/components/select-time-zone-section.tsx

**⚠️ FILES THAT DO NOT EXIST (verified against codebase):**
- ❌ `timezone-display.tsx` - DOES NOT EXIST. Use timeslot-radio-group.tsx instead.
- ❌ `timezone-handler.ts` - DOES NOT EXIST. Timezone is frontend-only.
- ❌ `timezone.controller.ts` - DOES NOT EXIST. No backend timezone code.
- tack stores `sendAt` as Unix timestamp (seconds since epoch) - inherently timezone-agnostic

**EXAMPLE EDGE CASES FOR TIMEZONE STORIES (USE THESE AS TEMPLATES):**
```
- [ ] **[Edge]** Given user travels from New York to Los Angeles (3hr time difference), when they open the scheduler, then the displayed times update to reflect their current browser timezone within 500ms
  - **Verify**: E2E test - Change browser timezone during test, assert `[data-testid="schedule-time"]` text changes - Expected: Time shows PST instead of EST

- [ ] **[Edge]** Given a pin is scheduled for 2:30 AM on DST spring-forward day, when DST occurs (2 AM becomes 3 AM), then the pin still publishes at the intended moment (what was "2:30 AM" becomes "3:30 AM")
  - **Verify**: Integration test with mocked clock - Assert publish timestamp is correct Unix epoch - Expected: No drift from user's intended posting moment
```

**NOTE**: ghostwriter DOES NOT call brandy2. The flow is: aero → brandy2 (get brand), aero → ghostwriter (with personalized prompt)

**CRITICAL: Distinguish Greenfield vs Existing Code**

You MUST explicitly classify this story as one of:

1. **BUG FIX** - Issue in existing code
   - Reference ONLY endpoints/files that exist today
   - Investigation subtasks point to specific existing code paths
   - Example: "Bug in existing `/api/v1/pinterest/oauth/callback` - token refresh fails silently"

2. **ENHANCEMENT** - Improving existing functionality
   - Reference existing code that will be modified
   - Clearly mark any NEW endpoints/files needed
   - Example: "Enhance existing `/api/v1/scheduler` to add timezone support (NEW: `timezone_handler.py`)"

3. **NEW FEATURE (Greenfield)** - Building something that doesn't exist
   - Explicitly state "TO BE CREATED" for all new endpoints/files
   - Do NOT write as if they already exist
   - Example: "NEW endpoint needed: `/api/v1/support/availability` (TO BE CREATED in tack/support/)"

**Add this line at the top of Technical Context:**
> **Story Type:** [BUG FIX | ENHANCEMENT | NEW FEATURE]

**Provide ALL of the following (be EXTREMELY specific - an engineer should know EXACTLY where to look):**

- **Primary Service:** [specific service from list above, e.g., "tailwind/tack"]
- **Dependency Chain:** [upstream service] → [this service] → [downstream service]
  - Example: "aero UI → tack (Pinterest OAuth handlers) → Pinterest API"
- **Affected Endpoints/URLs:** [specific API paths or UI routes - mark NEW ones as "TO BE CREATED"]
  - Example (bug): "/api/v1/pinterest/oauth/callback" (EXISTING)
  - Example (new): "/api/v1/support/availability" (TO BE CREATED)
- **Related Components:** [specific .ts/.tsx files - mark NEW ones as "TO BE CREATED"]
  - Example (bug): "aero/src/pages/api/pinterest/oauth/callback.ts (EXISTING - token handling)"
  - Example (new): "tack/src/services/timezone-handler.ts (TO BE CREATED)"
- **Inter-Service Communication:** [how services talk to each other]
  - Example: "REST API call from aero to tack via internal endpoint /api/internal/oauth/finalize"
  - Example: "aero's ghostwriter-labs calls brandy2 client to get brand settings, then calls ghostwriter with personalized prompt"
  - NOTE: ghostwriter does NOT call brandy2 directly - aero mediates all brand voice data
- **Error Patterns to Search:** [specific error codes, log patterns, exceptions]
  - Example: "Look for 'invalid_grant' in tack logs, 'ECONNREFUSED' in tack→Pinterest API calls"

**STORY SCOPING RULES (CRITICAL - Validated Against Codebase)**

When grouping themes into a story, follow these rules:

DO bundle themes that:
- Share the same root cause (would be fixed by same code change)
- Operate in the same request lifecycle within one service
- Are variations of the same user flow (edge cases of happy path)

DO NOT bundle:
- **MISSING FEATURES with BUG FIXES** - If a feature doesn't exist (e.g., brandy2 integration in ghostwriter), DON'T claim it's "broken". Instead, classify as NEW FEATURE
- Different data flows (REST integration vs state management)
- Unrelated user symptoms that LOOK similar but have different technical roots
- Issues requiring different engineers (frontend vs backend specialists)

**🚨 GHOSTWRITER SCOPING (CRITICAL - These are ALWAYS separate stories):**

If user feedback mentions Ghostwriter/AI content issues, these are DIFFERENT stories:

1. **"Content is generic/robotic"** = Brand voice issue
   - Root cause: Missing `injectPersonalization()` call in aero
   - Fix location: aero/packages/core/src/ghostwriter-labs/generations/chat.ts (NOTE: "generations" NOT "generators")
   - Primary Service: **tailwind/aero** (NOT tailwind/ghostwriter - the code lives in aero!)
   - Effort: ~1 day (add function call, same pattern as pinterest-title-and-description.ts)

   **EXAMPLE ROOT CAUSE HYPOTHESIS FOR BRAND VOICE (USE THIS AS TEMPLATE):**
   ```
   **Likely Root Cause Hypothesis:** The chat.ts file at line 21 is missing the `.preprocess((input) => injectPersonalization(input))` call that exists in all 39 other generation files.
   - Evidence: User feedback mentions "It writes like a robot" - this is consistent with missing brand voice data
   - Counter-evidence: If brand data isn't being fetched at all, we'd see brandy2 API errors - check logs
   - Confidence: HIGH - verified by comparing chat.ts to pinterest-title-and-description.ts
   - Specific code path: aero/packages/core/src/ghostwriter-labs/generations/chat.ts:21
   ```

2. **"AI forgets what I said"** = Context retention issue
   - Root cause: Token limit trimming (BY DESIGN - 4096 token limit in getMessagesWithinLimit())
   - Fix location: Multiple files, architectural decision needed
   - Primary Service: **tailwind/aero** (ChatbotGenerator lives in aero, not ghostwriter service)
   - Effort: ~1-2 weeks (database/cache design, multi-tab sync)

**THESE ARE NOT THE SAME BUG.** If user mentions both, you MUST write 2 SEPARATE stories.

**🛑 FORBIDDEN LANGUAGE IN BRAND VOICE STORIES (NEVER USE THESE PHRASES) 🛑**

If your story is about brand voice (missing injectPersonalization), do NOT use these phrases:

- ❌ "context retention" - this is a DIFFERENT issue (session memory)
- ❌ "remembers context" - this is session memory, not brand voice
- ❌ "conversation history" - this is session memory, not brand voice
- ❌ "forgets what I said" - this is session memory, not brand voice
- ❌ "retains context" - ambiguous, avoid this phrase entirely

**USE THESE PHRASES INSTEAD:**
- ✅ "brand voice" or "brand personality"
- ✅ "personalization" or "personalized content"
- ✅ "brand preferences" or "brand settings"
- ✅ "tone and style" or "writing style"
- ✅ "robotic content" or "generic responses" (as symptoms)

**CRITICAL: When writing Ghostwriter-related stories:**
- Primary Service is ALWAYS **tailwind/aero** for chat features (NOT tailwind/ghostwriter)
- The ghostwriter SERVICE is a backend LLM call handler
- The ChatbotGenerator class lives in aero/packages/core/src/ghostwriter/services/chatbot-generator/
- The generations configs live in aero/packages/core/src/ghostwriter-labs/generations/*.ts

Example of WRONG: "Fix Ghostwriter brand voice and context retention" (Primary: ghostwriter)
Example of RIGHT: Story A: "Add brand voice to Ghostwriter chat" (Primary: aero) + Story B: "Improve Ghostwriter context handling" (Primary: aero)

**🚨 MANDATORY STORY SPLITTING CHECK FOR GHOSTWRITER ISSUES 🚨**

If the user feedback mentions BOTH of these symptoms:
- "generic/robotic responses" OR "ignores brand" OR "doesn't sound like my brand"
- "forgets what I said" OR "loses context" OR "doesn't remember"

You MUST write ONLY ONE of these stories, NOT both combined:

**CHOOSE ONE:**
- If feedback emphasizes brand voice → Write "Add Brand Voice to Ghostwriter Chat" story ONLY
- If feedback emphasizes context → Write "Improve Ghostwriter Context Retention" story ONLY

**DO NOT BUNDLE THEM.** These require different fixes:
- Brand voice = 1 line change in chat.ts
- Context retention = architectural redesign

If you find yourself writing both "brand voice" AND "context" in the same story title, STOP and pick ONE.

**CRITICAL VALIDATION QUESTIONS (Ask Before Finalizing Story):**

1. **Is this actually broken, or never implemented?**
   - If no code path exists for the feature, it's a NEW FEATURE, not a bug
   - Example: ghostwriter has NO brandy2 integration - brand voice is NOT broken, it doesn't exist

2. **Do all themes share ONE code change to fix?**
   - If different modules/services need changes, SPLIT the story
   - Example: "fetch brand data" (REST) vs "persist session" (cache) = 2 separate stories

3. **Is the dependency chain actually correct?**
   - gandalf = internal employee auth ONLY (Google SSO)
   - Pinterest OAuth goes: Pinterest API → tack → aero (NO gandalf)
   - Facebook OAuth goes: Meta API → zuck → aero (NO gandalf)

4. **Are the complexity levels compatible?**
   - Simple: Adding a parameter, fixing a typo, updating a message
   - Medium: Adding a new field to an API, modifying UI component
   - Complex: Adding service-to-service integration, adding state management, architectural changes

   **SPLIT IF**: One theme is Simple/Medium and another is Complex
   Example: "Pass brandId to endpoint" (Simple) + "Add server-side session storage" (Complex) = SPLIT INTO 2 STORIES

5. **Is this grouping by USER SYMPTOM or TECHNICAL ROOT CAUSE?**
   - BAD: "Users report bad content" (symptom) - could be brand voice, context, prompts, etc.
   - GOOD: "Chat endpoint doesn't pass brandId to prompt builder" (specific root cause)

   If multiple themes share a SYMPTOM but have DIFFERENT ROOT CAUSES, SPLIT THEM.

6. **Is this behavior WORKING AS DESIGNED, or actually broken?**
   - Many "issues" are intentional tradeoffs (e.g., token limits, rate limits, session timeouts)
   - Example: Ghostwriter chat "forgetting context" may be BY DESIGN (token limit trimming)
   - If behavior is documented/intentional, classify as ENHANCEMENT REQUEST, not bug

7. **Do ALL acceptance criteria test the SAME feature?**
   - BAD: AC #1 tests brand voice, AC #3 tests session persistence (different features)
   - GOOD: All 6 ACs test variations of timezone display (same feature, different scenarios)

   **RULE**: If you can't explain how ALL ACs relate to ONE code change, SPLIT the story.

**🚨 CRITICAL: HAPPY PATH VS ERROR PATH SPLITTING 🚨**

This is one of the most common scoping mistakes. NEVER bundle these in the same story:

8. **Are you mixing HAPPY PATH improvements with ERROR PATH handling?**
   - **Happy path**: What happens when everything works (UI clarity, new features, enhancements)
   - **Error path**: What happens when external services fail (API errors, timeouts, retries)

   These require DIFFERENT:
   - Code paths (UI components vs error handlers)
   - Testing strategies (E2E vs mocking/integration)
   - Review expertise (frontend vs backend reliability)

   **BAD EXAMPLE (coda_page_001 anti-pattern):**
   ```
   Story: "Enhance Pinterest Scheduler Timezone Clarity"
   AC #1-4: Display timezone clearly in scheduler UI (happy path - aero only)
   AC #5: Handle Pinterest API 503 errors gracefully (error path - requires tack!)
   ```
   This bundles unrelated concerns. AC #5 is about error resilience, not timezone clarity.

   **GOOD EXAMPLE (properly split):**
   ```
   Story A: "Enhance Pinterest Scheduler Timezone Clarity" (aero-only)
   - AC #1-4: All about displaying timezone info clearly
   - Single service (aero), single code change, single testing approach

   Story B: "Handle Pinterest Scheduling Errors Gracefully" (tack + aero)
   - AC #1-3: All about 503/429/timeout error handling
   - Multi-service, requires error injection testing
   ```

   **RULE**: If ANY acceptance criterion mentions "error", "failure", "timeout", "503", "429", or "unavailable" - CHECK if it belongs in a separate error-handling story.

9. **Have you VERIFIED the feature exists before claiming it's broken?**
   - Before writing "X doesn't work", check if code path for X even exists
   - Example: ghostwriter chat.handler.ts has NO brandy2 import - brand voice isn't "broken", it's MISSING
   - If feature doesn't exist, write it as NEW FEATURE story, not BUG FIX

10. **Does your proposed change CONTRADICT documented design decisions?**
   - Before proposing behavioral changes, check if the current behavior is INTENTIONAL
   - **CRITICAL EXAMPLE - timezone-date.ts:**
     - This file (aero/packages/tailwindapp/client/utils/timezone-date.ts) contains explicit documentation:
       "We want to keep the user interface in this timezone even if the user travels to a different timezone"
     - ANY AC proposing "auto-detect browser timezone" CONTRADICTS this documented design decision
     - This requires a PRODUCT/DESIGN DISCUSSION TICKET, not an engineering story

   **BAD EXAMPLE:**
   ```
   AC #2: System auto-detects user's current browser timezone
   ```
   This contradicts timezone-date.ts design! The behavior is INTENTIONAL.

   **GOOD EXAMPLE:**
   ```
   [Design Spike]: Evaluate timezone detection strategy
   - Current: Profile timezone persists across devices (by design per timezone-date.ts)
   - Requested: Auto-detect browser timezone
   - This requires product decision - not an engineering story
   ```

   **RULE**: If behavior X exists and is documented as intentional, but user feedback requests changing X:
   1. DO NOT write an AC to change it
   2. Note it in Technical Context as "Requires design discussion"
   3. Create a SEPARATE design spike ticket if needed

11. **Are you mixing BUG FIXES with NEW FEATURES in the same story?**
   - **Bug fix**: Restoring functionality that USED to work, or fixing code that doesn't match documented behavior
   - **New feature**: Adding functionality that never existed before

   **BAD EXAMPLE (from intercom_001 anti-pattern):**
   ```
   Story: "Fix Pinterest OAuth Reconnection"  [Bug Fix]
   AC #1: Reconnection completes successfully [Bug fix - good]
   AC #2: Expired token redirects to re-auth [Bug fix - good]
   AC #3: Users can select which Pinterest account to reconnect [NEW FEATURE - bad!]
   ```
   AC #3 requests a new account selection dropdown that doesn't exist - this is a NEW FEATURE, not part of the bug fix.

   **GOOD EXAMPLE (properly split):**
   ```
   Story A: "Fix Pinterest OAuth Reconnection" [Bug Fix]
   - All ACs test the reconnection flow working correctly

   Story B: "Add Pinterest Account Selection During Reconnection" [New Feature]
   - ACs test the new account selection UI
   ```

   **RULE**: Check each AC - if it adds NEW functionality that never existed:
   1. REMOVE it from the bug fix story
   2. Note it in Technical Context as "Future enhancement: [description]"
   3. Keep bug fix focused on restoring broken functionality

**CRITICAL FOR HIGH-QUALITY STORIES: Add Pre-Investigation Analysis**

To reach GOLD STANDARD quality (4.8+/5.0), you MUST include this section:

### Pre-Investigation Analysis (MANDATORY - DO NOT SKIP - REQUIRED FOR 5/5 SCORE)

**🚨 THIS SECTION DETERMINES YOUR GESTALT SCORE 🚨**

Without this section, your story CANNOT score higher than 4/5. Include ALL of:

**Likely Root Cause Hypothesis:** [Your educated guess based on the symptoms - BE SPECIFIC with code path]
- Evidence supporting this hypothesis: [Specific observations from user feedback - CITE QUOTES like "User said: 'The button doesn't work'"]
- Counter-evidence to consider: [What might disprove this hypothesis - e.g., "If logs show success, issue may be frontend-only"]
- Confidence level: [HIGH/MEDIUM/LOW] based on evidence strength
- **Specific code path:** [e.g., "Issue likely in aero/packages/core/src/ghostwriter-labs/generations/chat.ts line 21"]

**Code Paths to Examine (IMPORTANT: Tailwind uses TypeScript/Next.js monorepo):**

Tailwind codebase is TypeScript with Next.js App Router. Use these ACTUAL path patterns:

**aero (frontend monorepo):**
1. aero/packages/tailwindapp/app/[route]/page.tsx - Page components
2. aero/packages/tailwindapp/app/dashboard/v3/api/[endpoint]/route.ts - API routes (App Router)
3. aero/packages/tailwindapp/client/domains/[domain]/components/*.tsx - Feature components
4. aero/packages/tailwindapp/client/hooks/*.ts - React hooks
5. aero/packages/core/src/[module]/*.ts - Shared core logic

**Backend services:**
1. tack/service/lib/handlers/api/[endpoint]/[endpoint]-handler.ts - API handlers
2. tack/service/lib/clients/pinterestv5/*.ts - Pinterest API clients
3. ghostwriter/stack/service/handlers/api/[endpoint]/[endpoint].handler.ts - Ghostwriter APIs
4. brandy2/packages/client/src/*.ts - Brand data client

**🚨 TACK OAUTH HANDLERS - ACTUAL FILE PATHS (VERIFIED) 🚨**

When referencing tack OAuth handlers, use THESE exact paths:
- ✅ tack/service/lib/handlers/api/get-oauth-response/get-oauth-response-handler.ts - Handles OAuth response from Pinterest
- ✅ tack/service/lib/handlers/api/get-oauth-redirect/get-oauth-redirect-handler.ts - Generates OAuth redirect URL
- ✅ tack/service/lib/handlers/api/oauth-finalize/oauth-finalize-handler.ts - Finalizes OAuth token exchange
- ✅ tack/service/lib/clients/pinterestv5/oauth.ts - Pinterest OAuth client

**FILE PATHS THAT DO NOT EXIST (DO NOT REFERENCE THESE):**
- ❌ tack/service/lib/handlers/api/oauth/pinterest/callback/oauth-callback-handler.ts - DOES NOT EXIST
- ❌ tack/service/lib/handlers/api/oauth-callback/oauth-callback-handler.ts - DOES NOT EXIST
- ❌ tack/service/lib/handlers/oauth/*.ts - This directory structure DOES NOT EXIST

Example file paths (ACTUAL paths from codebase):
- "aero/packages/tailwindapp/app/dashboard/v3/api/oauth/pinterest/callback/route.ts" - Pinterest OAuth callback (aero side)
- "tack/service/lib/handlers/api/get-oauth-response/get-oauth-response-handler.ts" - OAuth response handling (tack side)
- "tack/service/lib/handlers/api/oauth-finalize/oauth-finalize-handler.ts" - OAuth token finalization
- "ghostwriter/stack/service/handlers/api/chat/chat.handler.ts" - Ghostwriter chat handler
- "aero/packages/tailwindapp/client/domains/scheduler/components/*.tsx" - Scheduler UI components

**⚠️ CRITICAL: DO NOT HALLUCINATE FILE PATHS ⚠️**

If you're UNSURE about a specific file path:
- Use GENERIC patterns with wildcards: "ghostwriter/stack/service/handlers/api/**/*.handler.ts"
- Say "Investigate [service]/[module] for [functionality]" instead of inventing specific filenames
- NEVER reference files like "session.manager.ts" or "brand-voice-handler.ts" unless you KNOW they exist
- If the user feedback doesn't mention specific code, use exploratory language: "Search for [pattern]"

**Known Ghostwriter endpoints (verified):**
- /api/chat - Main chat handler (chat.handler.ts)
- /prompt/pinterest-title-and-description - Pinterest content generation
- /prompt/facebook-post - Facebook post generation

**DO NOT reference:** /api/v1/ghostwriter/generate (doesn't exist)

**Database/State to Check:**
- Table/Collection: [specific table name]
- Key fields: [relevant columns]
- **EXACT Query** (copy-paste ready):
  SELECT id, user_id, status, created_at FROM [table_name] WHERE [condition] ORDER BY created_at DESC LIMIT 100;

**Logs to Search (EXACT grep patterns):**
- Service: [which service's logs]
- **Command** (copy-paste ready):
  grep -E "(error_pattern|related_pattern)" /var/log/[service]/app.log | tail -100
- Time correlation: [how to correlate with user reports]

**CRITICAL: This section MUST include actual SQL queries and grep commands that an engineer can copy-paste and run immediately.**

This section transforms a "vague bug report" into an "engineer-ready investigation plan".

## User Experience Flow

**You MUST describe BOTH current AND target UX with SPECIFIC UI elements:**

**Current UX (Problem State) - What happens TODAY:**
1. **User Action:** [exact click/input, e.g., "User clicks 'Connect Pinterest' button"]
2. **System Response:** [exactly what UI shows, e.g., "Spinner appears for 3s, then error toast appears"]
3. **Error/Confusion Point:** [specific moment of frustration, e.g., "'Authorization failed' message with no next steps"]
4. **User Impact:** [behavioral result, e.g., "User retries 3x, gives up, contacts support"]

**Target UX (Goal State) - What SHOULD happen:**
1. **User Action:** [same as above]
2. **System Response:** [ideal behavior with timing, e.g., "Spinner for <2s, redirects to Pinterest OAuth"]
3. **Success Indicator:** [how user KNOWS it worked, e.g., "Green checkmark + 'Pinterest Connected' toast for 3s"]
4. **Recovery Path:** [what happens on failure, e.g., "Clear error message + 'Try Again' button + link to help docs"]

**UX Signals Mapping - CRITICAL: Map EVERY signal to a SPECIFIC acceptance criterion:**

You MUST fill this table with actual AC references. Each signal type MUST map to at least one AC below.

| Signal Type | UI Element | Verifies AC # | Test Method |
|-------------|------------|---------------|-------------|
| Loading | [e.g., `#loading-spinner`] | AC #1 (Happy) | Assert visible during operation |
| Success | [e.g., `[data-testid="success-toast"]`] | AC #6 (Feedback) | Assert text matches expected message |
| Error | [e.g., `.error-message-banner`] | AC #4-5 (Error) | Assert appears within 3s of failure |
| Recovery | [e.g., `button[data-action="retry"]`] | AC #4-5 (Error) | Assert clickable, triggers retry flow |

**IMPORTANT**: After writing acceptance criteria, VERIFY each row in this table references a valid AC number.

## Acceptance Criteria

**🚨 ACCEPTANCE CRITERIA FORMAT IS MANDATORY FOR 5/5 SCORE 🚨**

Write exactly 6 testable criteria with this distribution:
1. **1 Happy path** (main success scenario)
2. **2 Edge cases** (boundary conditions, unusual inputs, concurrent operations) - MUST BE SPECIFIC, NOT GENERIC
3. **2 Error cases** (API failures, network issues, invalid data) - INCLUDE EXACT ERROR CODES
4. **1 Feedback case** (how user knows operation succeeded/failed)

**CRITICAL: Each criterion MUST include at least ONE of:**
- CSS selector (e.g., `[data-testid="success-toast"]`)
- API response code (e.g., `HTTP 200 with status: connected`)
- Specific timing threshold (e.g., "within 3 seconds")
- Exact error message text (e.g., "Pinterest is temporarily unavailable")

**CRITICAL: Each criterion MUST have a SPECIFIC verification method with OBSERVABLE OUTCOMES**

**For Edge Cases, you MUST pick 2 SPECIFIC scenarios (not just categories):**

Pick TWO concrete edge cases from these categories that are MOST LIKELY for this specific issue:

1. **Boundary Conditions** - What happens at limits?
   - Max/min values (e.g., 0 pins, 1000 pins, empty caption, 2200 char caption)
   - Empty states (no boards, no followers, new account)
   - Special characters (Unicode, emojis, RTL text, HTML entities)
   - Rate limits (what if API quota is hit mid-operation?)

2. **Timing/Concurrency** - What happens with parallelism?
   - Concurrent requests (user double-clicks, multiple tabs)
   - Race conditions (token refreshed while operation in progress)
   - Timeouts (Pinterest API slow response, 30s+)
   - Order dependencies (step 2 completes before step 1)

3. **State Transitions** - What happens when state changes unexpectedly?
   - Session expiry mid-operation (OAuth token expired during multi-step flow)
   - Stale data (UI shows old state, backend has new state)
   - Partial completion (half the operation succeeds, half fails)
   - Recovery scenarios (user refreshes page mid-operation)

**GOLD STANDARD REQUIREMENT: Be CONCRETE, not generic**

Instead of: "Edge case: Handle rate limits"
Write: "Given Pinterest API returns HTTP 429 (rate limit) after 3 successful pins, when user schedules 10 pins in batch, then system queues remaining 7 pins with exponential backoff (5s, 10s, 20s...) and shows progress bar with 'Retrying...' status"

The edge case should be SO SPECIFIC that an engineer can write the test case directly from reading it.

Format:
- [ ] **[Happy/Edge/Error/Feedback]** Given [specific precondition], when [specific action], then [expected observable behavior]
  - **Verify**: [test type] - Assert [exact condition] - Expected: [quantifiable outcome]

**🚨 REGRESSION TEST MARKING 🚨**

If you include an AC for functionality that ALREADY WORKS (to ensure no regression during the fix), mark it clearly:

- [ ] **[Regression]** Given user has multiple Pinterest accounts, when they click connect, then account selection dropdown appears
  - **Why regression test**: This already works but could break during OAuth changes - verify it still functions
  - **Verify**: E2E test - Assert dropdown visible with account list

DO NOT include ACs for existing features WITHOUT the [Regression] tag. Either:
1. Mark it as [Regression] with explanation why it's included
2. Remove it from the story if not relevant to the change

**MANDATORY: Your acceptance criteria MUST include specific CSS selectors or API codes like these examples:**

- [ ] **[Happy]** Given a user has valid Pinterest credentials, when they click "Connect Pinterest", then the connection succeeds and dashboard shows "Connected" status
  - **Verify**: E2E test (Playwright) - Assert `[data-testid="pinterest-status"]` text equals "Connected" - Expected: Status updates within 5s, no error toasts
  - **Selector**: `button[data-action="connect-pinterest"]` for trigger, `[data-testid="connection-status"]` for result
  - **API**: Expect POST /api/v1/pinterest/oauth/callback to return HTTP 200 with status: connected

- [ ] **[Edge]** Given a user's Pinterest session has expired (token older than 60 days), when they attempt to connect, then they are redirected to Pinterest OAuth page
  - **Verify**: Integration test - Assert HTTP 302 redirect to `https://api.pinterest.com/oauth/` - Expected: Redirect occurs, no data loss
  - **API**: Expect GET /api/v1/pinterest/auth/status returns HTTP 401 with error: token_expired, code: AUTH_001

- [ ] **[Error]** Given Pinterest API returns 503, when connection is attempted, then user sees error message "Pinterest is temporarily unavailable. Please try again in a few minutes."
  - **Verify**: Unit test with MSW mock - Assert error toast contains exact message - Expected: Toast visible for 5s, retry button appears
  - **Selector**: `.error-toast[data-error-type="service-unavailable"]` with text matching regex `/temporarily unavailable/`

- [ ] **[Feedback]** Given any connection attempt, when the process completes (success or failure), then user receives visual feedback
  - **Verify**: E2E test timing - Assert feedback element appears within 3000ms of click event - Expected: p95 latency < 3s
  - **Selector**: `[role="alert"]` or `[data-testid="feedback-indicator"]` appears within 3000ms

**CROSS-REFERENCE CHECK**: After writing all 6 ACs above, verify that:
- [ ] Every row in the UX Signals Mapping table references a valid AC number from this section
- [ ] AC #1 (Happy) is referenced by the Success signal
- [ ] AC #4-5 (Error) are referenced by the Error and Recovery signals
- [ ] AC #6 (Feedback) ties UX signals to observable outcomes

**🚨 FINAL SCOPING CHECK FOR ACCEPTANCE CRITERIA 🚨**

STOP and ask yourself: "Do ALL my ACs share the SAME root cause and require the SAME code change?"

If your story is about **UI enhancement** (like timezone clarity), your ACs should ONLY be about:
- ✅ Displaying information (timezone labels, confirmation messages)
- ✅ Handling user input variations (DST, travel, timezone change)
- ✅ UI edge cases (empty states, loading states)

Your ACs should NOT include:
- ❌ External API error handling (503, 429, timeout)
- ❌ Backend retry logic or circuit breakers
- ❌ Service-to-service communication failures

If you wrote an AC about "Pinterest API 503 error" in a timezone clarity story, DELETE IT and note it for a separate story.

**🚨 SPECIFIC BUNDLING MISTAKES TO AVOID 🚨**

These are COMMONLY bundled incorrectly - NEVER put these in the same story:

1. **Timezone display clarity** + **Scheduling conflict detection** = TWO SEPARATE STORIES
   - Timezone clarity: Adding labels like "EST" to times in UI (aero-only, simple)
   - Conflict detection: Checking if two pins are scheduled for same time (requires backend logic, complex)
   - These have NOTHING in common except they're both about scheduling

2. **Timezone display clarity** + **DST handling in backend** = TWO SEPARATE STORIES
   - Timezone clarity: UI-only, shows user what timezone they're in
   - DST handling: Backend logic for Unix timestamp conversion (tack, complex)

3. **UI clarity improvements** + **External API error handling** = TWO SEPARATE STORIES
   - UI clarity: Frontend-only, aero service
   - API error handling: Backend retries, circuit breakers (tack, multi-service)

4. **UI clarity improvements** + **Behavioral changes that contradict documented design** = TWO SEPARATE STORIES
   - UI clarity: Making existing behavior more visible (ENHANCEMENT)
   - Behavioral change: Changing how the system works (DESIGN DECISION)
   - **EXAMPLE**: timezone-date.ts documents that profile timezone persists even when traveling
     - ✅ "Display timezone more prominently" = UI clarity enhancement (keep in story)
     - ❌ "Auto-detect browser timezone" = Contradicts documented design (requires separate design spike)

5. **Input validation** + **Feature enhancements** = TWO SEPARATE STORIES
   - Input validation: Defensive coding, error handling (security/reliability improvement)
   - Feature enhancement: Adding new user-visible functionality
   - Example: "Validate time input is valid" is separate from "Show timezone clearly"

If your timezone clarity story has an AC about "conflict detection" or "scheduling collision", REMOVE IT immediately.
If your timezone clarity story has an AC about "auto-detect browser timezone", CHECK if this contradicts documented design (it does).
If your timezone clarity story has an AC about "invalid time input", MOVE IT to a separate validation story.

**🚨🚨🚨 TIMEZONE STORY SCOPING CHECKLIST (MUST VERIFY BEFORE SUBMITTING) 🚨🚨🚨**

Before finalizing ANY timezone-related story, answer these questions:

1. **Is EVERY AC about UI DISPLAY clarity?** (showing timezone info more clearly)
   - ✅ "Display timezone in confirmation message"
   - ✅ "Show timezone in time slot picker"
   - ❌ "Auto-detect timezone when traveling" (behavioral change - REMOVE)
   - ❌ "Detect scheduling conflicts" (separate feature - REMOVE)
   - ❌ "Handle Pinterest API 503 errors" (error handling - REMOVE)

2. **Does ANY AC propose changing behavior documented in timezone-date.ts?**
   - timezone-date.ts says: "Keep user interface in profile timezone even when traveling"
   - If AC proposes auto-detect browser timezone: REMOVE IT (requires design spike)

3. **Does ANY AC mention "conflict", "collision", or "overlap"?**
   - REMOVE IT - conflict detection is a SEPARATE feature

4. **Does ANY AC mention "503", "timeout", "retry", or "unavailable"?**
   - REMOVE IT - error handling is a SEPARATE story

5. **Are ALL your ACs achievable with AERO-ONLY changes?**
   - Timezone display = aero frontend changes only
   - If AC requires tack changes: REMOVE IT (different service boundary)

**🛑 FORBIDDEN ACs IN TIMEZONE STORIES (NEVER INCLUDE THESE) 🛑**

These phrases MUST NEVER appear in a timezone clarity story. If you wrote any of these, DELETE THE AC:

- ❌ "Pinterest API 503" - error handling story
- ❌ "Pinterest API error" - error handling story
- ❌ "service unavailable" - error handling story
- ❌ "retry" or "circuit breaker" - reliability story
- ❌ "scheduling conflict" - conflict detection story
- ❌ "overlap" or "collision" - conflict detection story
- ❌ "auto-detect timezone" or "browser timezone" - contradicts design
- ❌ "DST backend" or "Unix timestamp conversion" - backend story
- ❌ "tack service" (except noting it as dependency) - wrong service scope

**ALLOWED ACs IN TIMEZONE STORIES:**
- ✅ Display timezone in confirmation message
- ✅ Show timezone abbreviation (EST, PST) in time picker
- ✅ Handle missing timezone gracefully in UI
- ✅ Show tooltip explaining what timezone means
- ✅ DST edge cases that affect DISPLAY only (spring forward, fall back)

## Success Metrics

**🚨 CRITICAL: Do NOT invent statistics without data. If you don't know the baseline, say so explicitly. 🚨**

**IMPORTANT: Every metric MUST have a baseline ("before") and target ("after") value.**

**Rules for Success Metrics:**
1. If specific numbers aren't mentioned in user feedback, use qualitative estimates: "Baseline: Unknown - requires instrumentation"
2. Do NOT claim specific failure rates (e.g., "20% of scheduled pins fail") unless user feedback contains that data
3. For UI clarity issues (like timezone confusion), measure USER CONFIDENCE, not system failure rates
4. tack uses Unix timestamps - scheduling failures are NOT caused by timezone bugs. Be honest about what's actually broken.

Define measurable outcomes tied directly to user problems:

- **User Impact:** [metric with baseline and target]
  - Baseline: [current state, e.g., "37% of Pinterest reconnection attempts fail"]
  - Target: [goal state, e.g., "< 5% failure rate"]
  - Measurement: [how to measure, e.g., "Mixpanel event tracking on 'pinterest_connect_result'"]

- **Technical Health:** [metric with baseline and target]
  - Baseline: [current state, e.g., "OAuth callback errors: 150/day"]
  - Target: [goal state, e.g., "< 10/day"]
  - Measurement: [how to measure, e.g., "Datadog dashboard 'OAuth Health'"]

- **Business Outcome:** [user-facing outcome]
  - Current: [what users experience now]
  - Target: [what users will experience after fix]
  - Validation: [how PM will verify success with users]

## Investigation Subtasks

Number each subtask with specific file paths, queries, or commands. Include expected findings with quantifiable signals.

1. [ ] **[Code Audit]**: Examine `[specific file path]` for [specific pattern/function]
   - Look for: [specific code pattern, e.g., "error handling in catch blocks"]
   - Expected finding: [hypothesis with signal, e.g., "Missing retry logic in OAuth callback - look for lack of exponential backoff"]

2. [ ] **[Log Analysis]**: Query `[specific log system/dashboard]` with filter `[query]`
   - Time range: [e.g., "Last 7 days"]
   - Expected pattern: [what signals confirm the issue, e.g., "Spike in 401 errors correlating with user reports"]

3. [ ] **[Trace Code Path]**: Follow execution from `[entry point]` to `[exit point]`
   - Key decision points: [specific functions/conditionals to examine]
   - Expected finding: [where bug likely lives, e.g., "Token validation in auth.py:validate_token() may not handle expired tokens"]

4. [ ] **[Reproduce in Staging]**:
   - Pre-conditions: [exact setup needed]
   - Steps: [numbered steps to reproduce]
   - Expected vs Actual: [what should happen vs what happens, with observable signals]

## Definition of Done

- [ ] All acceptance criteria pass automated tests
- [ ] No regression in existing functionality (verified by existing test suite)
- [ ] Success metrics have baseline measurements before deployment
- [ ] Documentation updated if user-facing behavior changes

---

Generate a single, well-structured story based on the feedback above. Be specific and actionable - an engineer should be able to start work immediately after reading this story.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a PRINCIPAL engineer at Tailwind who also has product analyst skills, writing engineering stories that score 4.8+/5.0 on quality rubrics. Your differentiator: you include PRE-INVESTIGATION ANALYSIS with specific code paths, database tables, and log queries an engineer can run immediately. Your edge cases are SO SPECIFIC they can be copy-pasted into test files. You don't just describe problems - you hypothesize root causes with evidence. Your acceptance criteria include exact CSS selectors, API response codes, and timing thresholds. You understand Tailwind's architecture deeply: tack handles Pinterest OAuth and scheduling, zuck handles Facebook/Instagram, aero is the frontend monorepo that also contains ghostwriter-labs (AI generation configs) and ChatbotGenerator. The ghostwriter SERVICE is just an LLM backend - brand voice and generation logic live in aero. Brandy2 provides brand settings data. A senior engineer reading your story would say 'I know exactly what to do and where to look.'"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=3500
        )

        story_content = response.choices[0].message.content

        return {
            "content": story_content,
            "source_type": source_type,
            "generated_at": datetime.now().isoformat(),
            "model": "gpt-4o-mini"
        }

    except Exception as e:
        print(f"ERROR generating story: {e}")
        return None


def evaluate_gestalt(story: Dict[str, Any], gold_standard: str) -> Dict[str, Any]:
    """
    Evaluate story quality using LLM-as-judge gestalt comparison.

    Returns holistic quality score (1-5) with explanation.
    Does NOT score individual dimensions to avoid Goodhart's Law.
    """
    client = OpenAI()

    story_content = story.get("content", "")

    eval_prompt = f"""You are evaluating the quality of an engineering story against a STRICT gold standard.

## Gold Standard Reference (What great stories look like)

{gold_standard[:8000]}  # Truncate if too long

## Story Being Evaluated

{story_content}

## Evaluation Task - STRICT SCORING RUBRIC

Rate this story using these PRECISE criteria:

**Score 5 (Excellent - 4.8+ quality):** Must have AT LEAST 4 of these 5 elements:
- Pre-investigation analysis with specific code paths and file names
- Edge cases with concrete scenarios (not generic categories)
- Acceptance criteria with exact CSS selectors or API response codes
- Root cause hypothesis with supporting evidence (look for "Likely Root Cause" section)
- Database/log queries OR file paths to examine (for frontend-only stories, file paths count)

IMPORTANT: If the story has a "Pre-Investigation Analysis" section with a root cause hypothesis and code paths, that counts as meeting the hypothesis requirement even if worded differently.

**Score 4 (Good):** Has MOST of these but missing 1-2 elements:
- Clear problem statement and user impact
- Technical context with service mapping
- Testable acceptance criteria
- Investigation subtasks
- Success metrics with baselines

**Score 3 (Adequate):** Has basic structure but:
- Generic edge cases or technical context
- Vague verification methods
- Missing root cause hypothesis
- No specific code paths

**Score 2 (Weak):** Multiple gaps:
- Missing key sections
- Untestable criteria
- Vague technical context

**Score 1 (Poor):** Not actionable

## CRITICAL EVALUATION RULE

Give a score of 5 if the story includes AT LEAST 4 of these 5 elements:
1. Pre-Investigation Analysis section with code paths (look for "### Pre-Investigation Analysis" heading)
2. Specific file paths or database/log queries for investigation
3. Concrete edge case scenarios (not just categories like "boundary conditions")
4. CSS selectors or API codes in acceptance criteria
5. Root cause hypothesis with evidence (look for "Likely Root Cause Hypothesis:" text)

NOTE: Frontend-only stories don't need database queries if they have specific component file paths.
If unsure whether an element is present, give the story the benefit of the doubt.

Respond in this exact JSON format:
{{
    "gestalt_score": <number 1-5>,
    "explanation": "<2-3 sentence explanation>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "improvements": ["<improvement 1>", "<improvement 2>"]
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a senior PM evaluating story quality. Be critical and honest."},
                {"role": "user", "content": eval_prompt}
            ],
            temperature=0.2,
            max_tokens=500,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        result["evaluated_at"] = datetime.now().isoformat()
        return result

    except Exception as e:
        print(f"ERROR in gestalt evaluation: {e}")
        return {
            "gestalt_score": 0,
            "explanation": f"Evaluation failed: {e}",
            "strengths": [],
            "improvements": [],
            "error": str(e)
        }


def run_scoping_validation(stories: List[Dict[str, Any]], tailwind_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Run scoping validation using Claude with access to Tailwind codebase.

    This spawns Claude to evaluate whether themes in stories are properly scoped.
    """
    import subprocess

    # Default tailwind path (sibling directory to FeedForward)
    if tailwind_path is None:
        tailwind_path = str(PROJECT_ROOT.parent)

    # Prepare stories for validation
    stories_json = json.dumps([
        {"content": s.get("content", ""), "source_type": s.get("source_type", "unknown")}
        for s in stories
    ])

    cmd = [
        "python3",
        str(SCRIPT_DIR / "validate_scoping.py"),
        stories_json,
        "--tailwind-path", tailwind_path
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout for Claude evaluation
            cwd=str(SCRIPT_DIR)
        )

        # Try to parse JSON output - find the JSON block after "SCOPING VALIDATION RESULTS"
        output = result.stdout

        # Look for the JSON after the header
        json_start = output.find('{\n  "summary"')
        if json_start < 0:
            json_start = output.rfind('{"summary"')
        if json_start < 0:
            json_start = output.rfind('{')

        if json_start >= 0:
            json_output = output[json_start:]
            # Find the matching closing brace by counting braces
            brace_count = 0
            end_pos = 0
            for i, char in enumerate(json_output):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break

            if end_pos > 0:
                json_str = json_output[:end_pos]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    # Try the full remainder anyway
                    try:
                        return json.loads(json_output)
                    except json.JSONDecodeError:
                        pass

        return {
            "summary": {"average_scoping_score": 0, "properly_scoped_pct": 0},
            "error": "Could not parse scoping validation output",
            "raw_output": output[:2000]
        }

    except subprocess.TimeoutExpired:
        return {"summary": {"average_scoping_score": 0}, "error": "Scoping validation timed out"}
    except Exception as e:
        return {"summary": {"average_scoping_score": 0}, "error": str(e)}


def run_playwright_validation(stories: List[Dict[str, Any]], storage_state: Optional[str] = None) -> Dict[str, Any]:
    """
    Run Playwright validation on generated stories.

    This calls the validate_playwright.py script.
    """
    import subprocess

    # Extract technical areas from stories
    story_data = []
    for i, story in enumerate(stories):
        content = story.get("content", "")

        # Simple extraction of technical area from story content
        technical_area = None
        if "tailwind/ghostwriter" in content.lower() or "ghostwriter" in content.lower():
            technical_area = "tailwind/ghostwriter"
        elif "tailwind/tack" in content.lower() or "pinterest" in content.lower():
            technical_area = "tailwind/tack"
        elif "tailwind/gandalf" in content.lower() or "oauth" in content.lower():
            technical_area = "tailwind/gandalf"
        else:
            technical_area = "tailwind/aero"  # Default

        story_data.append({
            "id": f"test-story-{i+1}",
            "technical_area": technical_area,
            "description": content[:200]  # First 200 chars as description
        })

    # Build command
    cmd = [
        "python3",
        str(SCRIPT_DIR / "validate_playwright.py"),
        json.dumps(story_data)
    ]

    if storage_state:
        cmd.extend(["--storage-state", storage_state])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(SCRIPT_DIR)
        )

        # Try to parse JSON output
        output = result.stdout
        json_start = output.rfind('{"success"')
        if json_start > 0:
            json_output = output[json_start:]
            return json.loads(json_output)

        return {
            "success": result.returncode == 0,
            "raw_output": output,
            "error": result.stderr if result.returncode != 0 else None
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Playwright validation timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_full_test(manifest_path: Path = DEFAULT_MANIFEST,
                  storage_state: Optional[str] = None,
                  skip_scoping: bool = False,
                  tailwind_path: Optional[str] = None,
                  verbose: bool = True,
                  live_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run complete pipeline test on all sources in manifest or live data.

    Validation pipeline:
    1. Generate stories from test sources
    2. Evaluate gestalt quality (LLM-as-judge)
    3. Run scoping validation (Claude + Tailwind codebase)

    Args:
        manifest_path: Path to static test manifest (used if live_data is None)
        storage_state: Deprecated, not used
        skip_scoping: Skip scoping validation for faster iteration
        tailwind_path: Path to Tailwind repos for scoping validation
        verbose: Print progress output
        live_data: If provided, use this instead of static manifest

    Returns evaluation metrics for all sources.
    """
    start_time = datetime.now()

    print(f"\n{'='*70}")
    print("  RALPH V2 PIPELINE TEST")
    print(f"{'='*70}")
    print(f"  Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Load manifest from live data or file
    if live_data is not None:
        manifest = live_data
        test_data_dir = SCRIPT_DIR / "test_data"  # Not used for live data
        print(f"  Mode: LIVE DATA (non-deterministic)")
        print(f"  Sources: {live_data.get('source_counts', {})}")
    else:
        manifest = load_manifest(manifest_path)
        test_data_dir = manifest_path.parent
        print(f"  Mode: STATIC (manifest: {manifest_path.name})")

    gold_standard = load_gold_standard()
    thresholds = manifest["quality_thresholds"]

    print(f"\n  [CONFIG]")
    print(f"    Sources: {len(manifest['sources'])}")
    print(f"    Gestalt threshold: >= {thresholds['gestalt_min']}")
    print(f"    Scoping threshold: >= {thresholds.get('scoping_min', 3.5)}")
    print(f"    Scoping validation: {'ENABLED' if not skip_scoping else 'DISABLED'}")

    # Initialize cheap mode evaluator for dual-mode evaluation
    cheap_evaluator = None
    if CHEAP_MODE_AVAILABLE:
        try:
            patterns_path = ensure_patterns_v2()
            cheap_evaluator = CheapModeEvaluator(patterns_path)
            health = cheap_evaluator.get_health_status()
            print(f"    Cheap mode: ENABLED ({health.details.get('total_patterns', 0)} patterns)")
            if not health.healthy:
                print(f"      Warning: {health.flags}")
        except Exception as e:
            print(f"    Cheap mode: DISABLED (error: {e})")
    else:
        print(f"    Cheap mode: DISABLED (module not available)")

    # Process each source
    results = []
    all_stories = []
    total_sources = len(manifest["sources"])

    print(f"\n  [PHASE 1: STORY GENERATION & GESTALT EVALUATION]")
    print(f"  {'-'*50}")

    for idx, source in enumerate(manifest["sources"], 1):
        source_id = source["id"]
        source_type = source["type"]

        # Progress indicator
        print(f"\n  [{idx}/{total_sources}] {source_id} ({source_type})")

        # Load test data
        try:
            data = load_test_data(source, test_data_dir)
            print(f"       ✓ Loaded test data")
        except Exception as e:
            print(f"       ✗ ERROR: {e}")
            results.append({
                "source_id": source_id,
                "error": str(e),
                "gestalt_score": 0
            })
            continue

        # Run pipeline
        print(f"       ⟳ Generating story...", end=" ", flush=True)
        story = run_pipeline_on_source(data, source_type)

        if not story:
            print(f"FAILED")
            results.append({
                "source_id": source_id,
                "error": "Pipeline generation failed",
                "gestalt_score": 0
            })
            continue

        print(f"done")
        all_stories.append(story)

        # Evaluate gestalt (expensive mode - LLM judge)
        print(f"       ⟳ Evaluating gestalt (expensive)...", end=" ", flush=True)
        evaluation = evaluate_gestalt(story, gold_standard)
        gestalt = evaluation.get("gestalt_score", 0)
        print(f"score: {gestalt}/5")

        # Evaluate cheap mode (pattern-based) for dual-mode gap tracking
        cheap_result = {"cheap_score": 0, "cheap_available": False}
        gap = 0.0
        if cheap_evaluator is not None:
            print(f"       ⟳ Evaluating cheap mode...", end=" ", flush=True)
            cheap_result = evaluate_cheap_mode(story, source_id, cheap_evaluator)
            cheap_score = cheap_result.get("cheap_score", 0)
            gap = gestalt - cheap_score if gestalt > 0 and cheap_score > 0 else 0
            gap_status = "✓" if abs(gap) <= GAP_TARGET else "⚠"
            print(f"score: {cheap_score}/5 (gap: {gap:+.2f} {gap_status})")

        result_entry = {
            "source_id": source_id,
            "source_type": source_type,
            "expected_technical_area": source.get("expected_technical_area"),
            "gestalt_score": gestalt,
            "evaluation": evaluation,
            "cheap_score": cheap_result.get("cheap_score", 0),
            "cheap_details": cheap_result,
            "gap": round(gap, 2),
            "story_preview": story["content"][:1500]
        }
        results.append(result_entry)

        # Build DualModeResult for learning loop (if cheap mode enabled)
        if cheap_evaluator is not None:
            dual_result = build_dual_mode_result(source_id, evaluation, cheap_result)
            if dual_result:
                result_entry["dual_mode_result"] = dual_result

    # Collect dual-mode results for learning loop
    dual_mode_results = [
        r["dual_mode_result"] for r in results
        if r.get("dual_mode_result") is not None
    ]

    # Run scoping validation on all stories (uses Claude with Tailwind codebase access)
    scoping_result = {"skipped": True}
    discovered_patterns = []

    if not skip_scoping and all_stories:
        print(f"\n  [PHASE 2: SCOPING VALIDATION (Claude + Tailwind Codebase)]")
        print(f"  {'-'*50}")
        print(f"  ⟳ Analyzing {len(all_stories)} stories against local Tailwind repos...")

        scoping_result = run_scoping_validation(all_stories, tailwind_path)
        scoping_score = scoping_result.get("summary", {}).get("average_scoping_score", 0)
        scoping_pct = scoping_result.get("summary", {}).get("properly_scoped_pct", 0)

        print(f"  ✓ Scoping analysis complete")
        print(f"       Average score: {scoping_score}/5")
        print(f"       Properly scoped: {scoping_pct}%")

        # Extract discovered patterns for pipeline learning
        discovered_patterns = scoping_result.get("discovered_patterns", [])
        if discovered_patterns:
            print(f"       Patterns discovered: {len(discovered_patterns)}")
            for p in discovered_patterns[:3]:  # Show first 3
                ptype = "✓" if p.get("pattern_type") == "good_pattern" else "✗"
                print(f"         {ptype} {p.get('description', 'N/A')[:60]}...")

        # Update knowledge cache with discovered patterns (learning system)
        if KNOWLEDGE_CACHE_AVAILABLE:
            try:
                print(f"\n  [PHASE 2.5: UPDATING KNOWLEDGE CACHE]")
                update_knowledge_from_scoping(scoping_result)
            except Exception as e:
                print(f"  Warning: Could not update knowledge cache: {e}")

    # Run pattern learning loop (Phase 3 - if dual-mode enabled)
    learning_stats = {"skipped": True}
    if PATTERN_LEARNER_AVAILABLE and cheap_evaluator is not None and dual_mode_results:
        print(f"\n  [PHASE 3: PATTERN LEARNING LOOP]")
        print(f"  {'-'*50}")
        print(f"  ⟳ Running learning iteration with {len(dual_mode_results)} dual-mode results...")

        try:
            # Extract iteration number from output file naming (or use timestamp)
            import re
            iteration_match = re.search(r"iteration_(\d+)", str(SCRIPT_DIR / "outputs"))
            iteration = int(iteration_match.group(1)) if iteration_match else 1

            learning_stats = run_learning_iteration(
                patterns_path=PATTERNS_V2_PATH,
                dual_results=dual_mode_results,
                iteration=iteration,
            )

            print(f"  ✓ Learning iteration complete")
            print(f"       New proposals: {learning_stats.get('new_proposals', 0)}")
            print(f"       Patterns committed: {len(learning_stats.get('committed', []))}")
            print(f"       Patterns rejected: {len(learning_stats.get('rejected', []))}")
            print(f"       Still provisional: {learning_stats.get('still_provisional', 0)}")

            status = learning_stats.get("status", {})
            print(f"       Total active patterns: {status.get('active_patterns', 0)}")

        except Exception as e:
            print(f"  ⚠ Learning loop error: {e}")
            learning_stats = {"skipped": False, "error": str(e)}

    # Calculate summary metrics
    gestalt_scores = [r["gestalt_score"] for r in results if r.get("gestalt_score", 0) > 0]
    avg_gestalt = mean(gestalt_scores) if gestalt_scores else 0

    # Calculate cheap mode metrics (dual-mode)
    cheap_scores = [r["cheap_score"] for r in results if r.get("cheap_score", 0) > 0]
    avg_cheap = mean(cheap_scores) if cheap_scores else 0

    # Calculate gap metrics
    gaps = [r.get("gap", 0) for r in results if r.get("gestalt_score", 0) > 0 and r.get("cheap_score", 0) > 0]
    avg_gap = mean(gaps) if gaps else 0
    max_gap = max(abs(g) for g in gaps) if gaps else 0
    gaps_within_target = sum(1 for g in gaps if abs(g) <= GAP_TARGET)
    gap_compliance_pct = (gaps_within_target / len(gaps) * 100) if gaps else 0

    # Run convergence monitoring (Phase 4 - if dual-mode enabled)
    convergence_status = {"monitoring_enabled": False}
    suggested_action = None
    if CONVERGENCE_MONITOR_AVAILABLE and cheap_evaluator is not None and avg_gestalt > 0 and avg_cheap > 0:
        print(f"\n  [PHASE 4: CONVERGENCE MONITORING]")
        print(f"  {'-'*50}")

        try:
            monitor = ConvergenceMonitor(CONVERGENCE_HISTORY_PATH)

            # Record this iteration
            iteration = len(monitor.history) + 1
            story_ids = [r["source_id"] for r in results]

            monitor.record_iteration(
                iteration=iteration,
                expensive_avg=avg_gestalt,
                cheap_avg=avg_cheap,
                pattern_count=learning_stats.get("status", {}).get("active_patterns", 0),
                provisional_patterns=learning_stats.get("still_provisional", 0),
                patterns_committed=len(learning_stats.get("committed", [])),
                patterns_rejected=len(learning_stats.get("rejected", [])),
                story_ids=story_ids,
            )

            # Check for divergence
            divergence = monitor.check_divergence()
            if divergence.diverging:
                print(f"  ⚠ DIVERGENCE DETECTED: {divergence.reason}")
                print(f"       Diagnosis: {divergence.diagnosis}")
                print(f"       Action: {divergence.action}")

            # Check for convergence
            convergence = monitor.check_convergence()
            if convergence.converged:
                print(f"  ✓ CONVERGENCE ACHIEVED!")
                print(f"       Gap consistently within target ({GAP_TARGET})")
                print(f"       Proof: {convergence.proof}")

            # Get trend and suggested action
            trend = monitor.get_trend()
            suggested_action = monitor.suggest_action()

            convergence_status = {
                "monitoring_enabled": True,
                "iteration": iteration,
                "trend": trend,
                "diverging": divergence.diverging,
                "converged": convergence.converged,
                "suggested_action": suggested_action,
            }

            print(f"  ✓ Iteration {iteration} recorded")
            print(f"       Trend: {trend}")
            if suggested_action:
                print(f"       Suggested action: {suggested_action}")

        except Exception as e:
            print(f"  ⚠ Convergence monitoring error: {e}")
            convergence_status = {"monitoring_enabled": True, "error": str(e)}

    # Group by source type
    by_source_type = {}
    for r in results:
        st = r.get("source_type", "unknown")
        if st not in by_source_type:
            by_source_type[st] = []
        if r.get("gestalt_score", 0) > 0:
            by_source_type[st].append(r["gestalt_score"])

    source_type_avgs = {
        st: round(mean(scores), 2) if scores else 0
        for st, scores in by_source_type.items()
    }

    # Thresholds and pass/fail
    passes_gestalt = avg_gestalt >= thresholds["gestalt_min"]
    passes_per_source = all(
        avg >= thresholds.get("per_source_gestalt_min", 3.5)
        for avg in source_type_avgs.values() if avg > 0
    )
    # Gap threshold check (optional - warn if gap is too large)
    passes_gap = avg_gap <= GAP_TARGET if gaps else True

    # Scoping thresholds
    scoping_threshold = thresholds.get("scoping_min", 3.5)
    scoping_score_val = scoping_result.get("summary", {}).get("average_scoping_score", 0)
    passes_scoping = scoping_score_val >= scoping_threshold if not scoping_result.get("skipped") else True

    # Calculate duration
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    summary = {
        "timestamp": end_time.isoformat(),
        "duration_seconds": round(duration, 1),
        "sources_tested": len(manifest["sources"]),
        "stories_generated": len(all_stories),
        "average_gestalt": round(avg_gestalt, 2),
        "gestalt_threshold": thresholds["gestalt_min"],
        "passes_gestalt": passes_gestalt,
        "source_type_averages": source_type_avgs,
        "passes_per_source": passes_per_source,
        # Dual-mode metrics
        "average_cheap": round(avg_cheap, 2),
        "average_gap": round(avg_gap, 2),
        "max_gap": round(max_gap, 2),
        "gap_target": GAP_TARGET,
        "gap_compliance_pct": round(gap_compliance_pct, 1),
        "passes_gap": passes_gap,
        "dual_mode_enabled": cheap_evaluator is not None,
        # Scoping
        "scoping_score": round(scoping_score_val, 2) if scoping_score_val else 0,
        "scoping_threshold": scoping_threshold,
        "passes_scoping": passes_scoping,
        "patterns_discovered": len(discovered_patterns),
        # Learning loop
        "learning_enabled": not learning_stats.get("skipped", True),
        "patterns_committed": len(learning_stats.get("committed", [])),
        "patterns_rejected": len(learning_stats.get("rejected", [])),
        "patterns_provisional": learning_stats.get("still_provisional", 0),
        "total_active_patterns": learning_stats.get("status", {}).get("active_patterns", 0),
        # Convergence monitoring
        "convergence_monitoring": convergence_status.get("monitoring_enabled", False),
        "convergence_trend": convergence_status.get("trend"),
        "is_diverging": convergence_status.get("diverging", False),
        "is_converged": convergence_status.get("converged", False),
        "overall_pass": passes_gestalt and passes_per_source and passes_scoping
    }

    # Print verbose summary
    print(f"\n  {'='*70}")
    print(f"  SUMMARY")
    print(f"  {'='*70}")

    # Results table
    print(f"\n  ┌─────────────────────────┬─────────┬───────────┬────────┐")
    print(f"  │ Metric                  │ Value   │ Threshold │ Status │")
    print(f"  ├─────────────────────────┼─────────┼───────────┼────────┤")
    print(f"  │ Average Gestalt         │ {summary['average_gestalt']:<7} │ >= {thresholds['gestalt_min']:<5} │ {'PASS' if passes_gestalt else 'FAIL':^6} │")

    for st, avg in source_type_avgs.items():
        status = "PASS" if avg >= thresholds.get("per_source_gestalt_min", 3.5) else "FAIL"
        print(f"  │   └─ {st:<17} │ {avg:<7} │ >= 3.5    │ {status:^6} │")

    scoping_status = "PASS" if passes_scoping else "FAIL"
    if scoping_result.get("skipped"):
        scoping_status = "SKIP"
    print(f"  │ Scoping Score           │ {summary['scoping_score']:<7} │ >= {scoping_threshold:<5} │ {scoping_status:^6} │")

    # Dual-mode metrics (if enabled)
    if cheap_evaluator is not None:
        print(f"  ├─────────────────────────┼─────────┼───────────┼────────┤")
        print(f"  │ Cheap Mode Score        │ {summary['average_cheap']:<7} │   n/a     │   --   │")
        gap_status = "PASS" if passes_gap else "WARN"
        print(f"  │ Avg Gap (expensive-cheap)│ {summary['average_gap']:+.2f}   │ <= {GAP_TARGET:<5} │ {gap_status:^6} │")
        print(f"  │ Max Gap                 │ {summary['max_gap']:+.2f}   │   n/a     │   --   │")
        print(f"  │ Gap Compliance          │ {summary['gap_compliance_pct']:.0f}%    │   n/a     │   --   │")

    print(f"  └─────────────────────────┴─────────┴───────────┴────────┘")

    # Scoping patterns
    if discovered_patterns:
        print(f"\n  [DISCOVERED SCOPING PATTERNS]")
        for i, p in enumerate(discovered_patterns, 1):
            ptype = "GOOD" if p.get("pattern_type") == "good_pattern" else "BAD"
            print(f"  {i}. [{ptype}] {p.get('description', 'N/A')}")
            if p.get("example"):
                print(f"      Example: {p.get('example')[:70]}...")

    # Overall result
    overall = "PASS ✓" if summary["overall_pass"] else "FAIL ✗"
    dual_mode_str = f"Gap: {summary['average_gap']:+.2f}" if summary["dual_mode_enabled"] else "Dual-mode: OFF"
    print(f"\n  ┌─────────────────────────────────────────────────────────────────────┐")
    print(f"  │  OVERALL RESULT: {overall:^50} │")
    print(f"  │  Duration: {duration:.1f}s | Stories: {len(all_stories)} | {dual_mode_str:<26} │")
    print(f"  └─────────────────────────────────────────────────────────────────────┘")

    # Clean results for JSON serialization (remove Pydantic models)
    clean_results = []
    for r in results:
        clean_r = {k: v for k, v in r.items() if k != "dual_mode_result"}
        clean_results.append(clean_r)

    # Full output
    output = {
        "summary": summary,
        "results": clean_results,
        "scoping": scoping_result,
        "discovered_patterns": discovered_patterns,
        "learning": learning_stats if not learning_stats.get("skipped") else None,
        "convergence": convergence_status if convergence_status.get("monitoring_enabled") else None,
        "manifest_version": manifest.get("version", "unknown")
    }

    # Write results to file
    output_path = SCRIPT_DIR / "outputs" / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults written to: {output_path}")

    return output


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Ralph V2 Pipeline Test Harness - Generates stories and validates quality"
    )

    # Mode selection
    parser.add_argument("--live", action="store_true",
                        help="Use live data from Intercom, Coda tables, and Coda pages instead of static fixtures")

    # Live data configuration
    parser.add_argument("--intercom", type=int, default=8,
                        help="Number of Intercom conversations to load (live mode only)")
    parser.add_argument("--coda-tables", type=int, default=4,
                        help="Number of Coda table entries to load (live mode only)")
    parser.add_argument("--coda-pages", type=int, default=4,
                        help="Number of Coda page entries to load (live mode only)")
    parser.add_argument("--days", type=int, default=60,
                        help="Days back to search for Intercom data (live mode only)")
    parser.add_argument("--no-random", action="store_true",
                        help="Don't randomize data selection (live mode only)")

    # Static data configuration
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="Path to test data manifest (static mode only)")

    # Validation options
    parser.add_argument("--skip-scoping", action="store_true",
                        help="Skip scoping validation (faster iteration)")
    parser.add_argument("--tailwind-path", type=str,
                        help="Path to directory containing Tailwind repos (default: parent of FeedForward)")

    # Output options
    parser.add_argument("--output", type=Path,
                        help="Custom output path for results")
    parser.add_argument("-v", "--verbose", action="store_true", default=True,
                        help="Verbose output (default: True)")

    args = parser.parse_args()

    # Load data based on mode
    live_data = None
    if args.live:
        if not LIVE_DATA_AVAILABLE:
            print("ERROR: Live data loader not available. Make sure live_data_loader.py exists.")
            sys.exit(1)

        live_data = load_live_test_data(
            intercom_count=args.intercom,
            coda_table_count=args.coda_tables,
            coda_page_count=args.coda_pages,
            days_back=args.days,
            randomize=not args.no_random,
            verbose=args.verbose
        )

        if not live_data.get("sources"):
            print("ERROR: No live data could be loaded. Check database connection and Coda API credentials.")
            sys.exit(1)

    results = run_full_test(
        manifest_path=args.manifest,
        skip_scoping=args.skip_scoping,
        tailwind_path=args.tailwind_path,
        verbose=args.verbose,
        live_data=live_data
    )

    # Exit with appropriate code
    sys.exit(0 if results["summary"]["overall_pass"] else 1)


if __name__ == "__main__":
    main()

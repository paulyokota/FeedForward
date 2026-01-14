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


# Constants
SCRIPT_DIR = Path(__file__).parent
DEFAULT_MANIFEST = SCRIPT_DIR / "test_data" / "manifest.json"
GOLD_STANDARD_PATH = PROJECT_ROOT / "docs" / "story_knowledge_base.md"


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

    # Static file format
    path = test_data_dir / source["path"]

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

    # Generate story using the pipeline (improved for quality)
    # Key improvements from gold standard analysis:
    # - Explicit INVEST criteria
    # - Measurable/testable acceptance criteria
    # - Expected outcomes for investigation subtasks
    # - User persona context
    # - Specific technical service mapping for Tailwind
    prompt = f"""You are a senior product analyst creating an INVEST-compliant engineering story from user feedback.

## User Feedback Content

{content}

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
- **aero**: Main monorepo - frontend UI, API routes, AND brand voice injection (ghostwriter-labs module)
- **ghostwriter**: AI text generation backend - receives prompts from aero, DOES NOT call brandy2 directly
- **brandy2**: Brand voice/settings data provider - called by AERO, not ghostwriter

**⚠️ CRITICAL: Brand Voice Architecture (Often Misunderstood):**
- Brand voice injection happens in AERO, not ghostwriter
- Code path: aero/packages/core/src/ghostwriter-labs/generators/*.ts
- The `injectPersonalization()` function in aero fetches brand data from brandy2
- Ghostwriter receives the ALREADY-PERSONALIZED prompt from aero
- If a feature "lacks brand voice", the fix is in AERO (add injectPersonalization), NOT ghostwriter

**Dependency chains:**
- **Pinterest OAuth:** aero UI → tack (OAuth handlers) → Pinterest API
- **Facebook OAuth:** aero UI → zuck (OAuth handlers) → Meta Graph API
- **AI/Content Generation:** aero (fetches brand from brandy2, builds prompt) → ghostwriter (LLM call) → returns to aero
- **Scheduling:** aero UI → tack (Pinterest scheduler) → Pinterest API

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
   - Fix location: aero/packages/core/src/ghostwriter-labs/generations/chat.ts (NOTE: "generations" not "generators")
   - Effort: ~1 day (add function call, same pattern as pinterest-title-and-description.ts)

2. **"AI forgets what I said"** = Context retention issue
   - Root cause: Token limit trimming (BY DESIGN - 4096 token limit)
   - Fix location: Multiple files, architectural decision needed
   - Effort: ~1-2 weeks (database/cache design, multi-tab sync)

**THESE ARE NOT THE SAME BUG.** If user mentions both, write 2 separate stories.

Example of WRONG: "Fix Ghostwriter brand voice and context retention"
Example of RIGHT: Story A: "Add brand voice to Ghostwriter chat" + Story B: "Improve Ghostwriter context handling"

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

8. **Have you VERIFIED the feature exists before claiming it's broken?**
   - Before writing "X doesn't work", check if code path for X even exists
   - Example: ghostwriter chat.handler.ts has NO brandy2 import - brand voice isn't "broken", it's MISSING
   - If feature doesn't exist, write it as NEW FEATURE story, not BUG FIX

**CRITICAL FOR HIGH-QUALITY STORIES: Add Pre-Investigation Analysis**

To reach GOLD STANDARD quality (4.8+/5.0), you MUST include this section:

### Pre-Investigation Analysis (MANDATORY - DO NOT SKIP)

**Likely Root Cause Hypothesis:** [Your educated guess based on the symptoms - BE SPECIFIC]
- Evidence supporting this hypothesis: [Specific observations from user feedback - CITE QUOTES]
- Counter-evidence to consider: [What might disprove this hypothesis]
- Confidence level: [HIGH/MEDIUM/LOW] based on evidence strength

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

Example file paths (ACTUAL paths from codebase):
- "aero/packages/tailwindapp/app/dashboard/v3/api/oauth/pinterest/callback/route.ts" - Pinterest OAuth callback
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

Write exactly 6 testable criteria with this distribution:
1. **1 Happy path** (main success scenario)
2. **2 Edge cases** (boundary conditions, unusual inputs, concurrent operations)
3. **2 Error cases** (API failures, network issues, invalid data)
4. **1 Feedback case** (how user knows operation succeeded/failed)

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

## Success Metrics

**IMPORTANT: Every metric MUST have a baseline ("before") and target ("after") value.**

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
                {"role": "system", "content": "You are a PRINCIPAL engineer at Tailwind who also has product analyst skills, writing engineering stories that score 4.8+/5.0 on quality rubrics. Your differentiator: you include PRE-INVESTIGATION ANALYSIS with specific code paths, database tables, and log queries an engineer can run immediately. Your edge cases are SO SPECIFIC they can be copy-pasted into test files. You don't just describe problems - you hypothesize root causes with evidence. Your acceptance criteria include exact CSS selectors, API response codes, and timing thresholds. You understand Tailwind's architecture deeply: tack handles OAuth and scheduling, gandalf manages auth, ghostwriter powers AI features with brandy2 for brand voice. A senior engineer reading your story would say 'I know exactly what to do and where to look.'"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
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

**Score 5 (Excellent - 4.8+ quality):** Must have ALL of these:
- Pre-investigation analysis with specific code paths and file names
- Edge cases with concrete scenarios (not generic categories)
- Acceptance criteria with exact CSS selectors or API response codes
- Root cause hypothesis with supporting evidence
- Database tables and log queries an engineer can run immediately

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

If the story includes ALL of these gold-standard elements, you MUST give it a 5:
1. Pre-Investigation Analysis section with code paths
2. Specific database/log queries
3. Concrete edge case scenarios (not just categories)
4. CSS selectors or API codes in acceptance criteria

If it's missing ANY of these, cap the score at 4.

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

        # Evaluate gestalt
        print(f"       ⟳ Evaluating gestalt...", end=" ", flush=True)
        evaluation = evaluate_gestalt(story, gold_standard)
        gestalt = evaluation.get("gestalt_score", 0)
        print(f"score: {gestalt}/5")

        results.append({
            "source_id": source_id,
            "source_type": source_type,
            "expected_technical_area": source.get("expected_technical_area"),
            "gestalt_score": gestalt,
            "evaluation": evaluation,
            "story_preview": story["content"][:1500]
        })

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

    # Calculate summary metrics
    gestalt_scores = [r["gestalt_score"] for r in results if r.get("gestalt_score", 0) > 0]
    avg_gestalt = mean(gestalt_scores) if gestalt_scores else 0

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
        "scoping_score": round(scoping_score_val, 2) if scoping_score_val else 0,
        "scoping_threshold": scoping_threshold,
        "passes_scoping": passes_scoping,
        "patterns_discovered": len(discovered_patterns),
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
    print(f"\n  ┌─────────────────────────────────────────────────────────────────────┐")
    print(f"  │  OVERALL RESULT: {overall:^50} │")
    print(f"  │  Duration: {duration:.1f}s | Stories: {len(all_stories)} | Patterns: {len(discovered_patterns):<17} │")
    print(f"  └─────────────────────────────────────────────────────────────────────┘")

    # Full output
    output = {
        "summary": summary,
        "results": results,
        "scoping": scoping_result,
        "discovered_patterns": discovered_patterns,
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

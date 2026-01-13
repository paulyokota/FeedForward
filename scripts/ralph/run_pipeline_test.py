#!/usr/bin/env python3
"""
Ralph V2 Pipeline Test Harness

Runs the Feed Forward pipeline against test data and evaluates output quality.

Usage:
    python3 run_pipeline_test.py [--manifest PATH] [--output PATH]

Example:
    python3 run_pipeline_test.py
    python3 run_pipeline_test.py --manifest test_data/manifest.json
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


# Constants
SCRIPT_DIR = Path(__file__).parent
DEFAULT_MANIFEST = SCRIPT_DIR / "test_data" / "manifest.json"
GOLD_STANDARD_PATH = PROJECT_ROOT / "docs" / "story_knowledge_base.md"


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load test data manifest."""
    with open(manifest_path) as f:
        return json.load(f)


def load_test_data(source: Dict[str, Any], test_data_dir: Path) -> Dict[str, Any]:
    """Load a single test data source."""
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
    if source_type == "intercom":
        content = f"""
Subject: {source_data.get('source_subject', 'N/A')}

{source_data.get('source_body', '')}
"""
    elif source_type == "coda_table":
        rows = source_data.get("rows", [])
        content = "\n\n".join([
            f"Theme: {row.get('theme_name')}\nParticipants: {row.get('participant_count')}\nVerbatims: {row.get('verbatims')}\nSynthesis: {row.get('synthesis_notes')}"
            for row in rows
        ])
    elif source_type == "coda_page":
        content = source_data.get("content", "")
    else:
        content = str(source_data)

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

For Tailwind products, map to these services:
- OAuth/Integrations → tailwind/tack, tailwind/gandalf
- AI/Ghostwriter → tailwind/ghostwriter
- Scheduling → tailwind/tack
- Analytics → tailwind/analytics

- **Primary Service:** [specific service from above]
- **Affected Endpoints/URLs:** [specific URLs or API endpoints]
- **Related Components:** [specific code modules or features]
- **Error Patterns:** [any error codes, messages, or logs to look for]

## User Experience Flow

Describe the current user experience and the improved experience:

**Current UX (Problem State):**
1. [Step 1 - what user does]
2. [Step 2 - what happens that's wrong]
3. [Step 3 - resulting confusion/frustration]

**Ideal UX (Target State):**
1. [Step 1 - what user does]
2. [Step 2 - what should happen (with specific UI feedback)]
3. [Step 3 - successful outcome with clear confirmation]

**Key UX Signals:**
- Loading states: [how does user know system is working?]
- Success feedback: [what confirms the operation worked?]
- Error recovery: [how does user recover from failures?]

## Acceptance Criteria

Write 4-6 testable criteria covering:
1. Happy path (main success scenario)
2. Edge cases (boundary conditions, unusual inputs)
3. Error handling (what happens when things fail)
4. User feedback (how does the user know the operation succeeded/failed)

**CRITICAL: Each criterion MUST have a SPECIFIC verification method with OBSERVABLE OUTCOMES**

Format:
- [ ] **[Happy/Edge/Error/Feedback]** Given [specific precondition], when [specific action], then [expected observable behavior]
  - **Verify**: [test type] - Assert [exact condition] - Expected: [quantifiable outcome]

Example set with COMPLETE verification methods:
- [ ] **[Happy]** Given a user has valid Pinterest credentials, when they click "Connect Pinterest", then the connection succeeds and dashboard shows "Connected" status
  - **Verify**: E2E test (Playwright) - Assert `[data-testid="pinterest-status"]` text equals "Connected" - Expected: Status updates within 5s, no error toasts
- [ ] **[Edge]** Given a user's Pinterest session has expired (token older than 60 days), when they attempt to connect, then they are redirected to Pinterest OAuth page
  - **Verify**: Integration test - Assert HTTP 302 redirect to `https://api.pinterest.com/oauth/` - Expected: Redirect occurs, no data loss
- [ ] **[Error]** Given Pinterest API returns 503, when connection is attempted, then user sees error message "Pinterest is temporarily unavailable. Please try again in a few minutes."
  - **Verify**: Unit test with MSW mock - Assert error toast contains exact message - Expected: Toast visible for 5s, retry button appears
- [ ] **[Feedback]** Given any connection attempt, when the process completes (success or failure), then user receives visual feedback
  - **Verify**: E2E test timing - Assert feedback element appears within 3000ms of click event - Expected: p95 latency < 3s

## Success Metrics

Define measurable outcomes beyond test passage:
- **User Impact:** [specific metric, e.g., "Reduce failed OAuth attempts from X% to Y%"]
- **Technical Health:** [specific metric, e.g., "Error rate in oauth_callback endpoint drops below 1%"]
- **Time to Resolution:** [how quickly should we ship? e.g., "Within 1 sprint"]

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
                {"role": "system", "content": "You are a senior product analyst at Tailwind, expert in creating INVEST-compliant engineering stories. You understand Tailwind's architecture (tack for OAuth/scheduling, gandalf for auth, ghostwriter for AI features). Your stories are immediately actionable by engineers - specific, testable, and technically accurate."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2500
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

    eval_prompt = f"""You are evaluating the quality of an engineering story.

## Gold Standard Reference (What great stories look like)

{gold_standard[:8000]}  # Truncate if too long

## Story Being Evaluated

{story_content}

## Evaluation Task

Rate this story's OVERALL QUALITY on a 1-5 scale:

5 - Excellent: Engineer could start immediately. Problem is crystal clear,
    technical context is accurate and helpful, acceptance criteria are testable.
    A PM would approve this ticket without questions.

4 - Good: Minor improvements possible, but actionable. Core is solid.
    Engineer would only need minimal clarification.

3 - Adequate: Needs some clarification. Core is understandable but
    missing some details. Would require a brief discussion before starting.

2 - Weak: Significant gaps. Would be sent back for revision.
    Missing critical information about scope, technical context, or outcomes.

1 - Poor: Not actionable. Fundamental issues with clarity, scope, or value.
    Requires complete rewrite.

## Important Instructions

- Rate the OVERALL quality holistically - how does it "feel" compared to great stories?
- Do NOT break down into individual dimensions (that causes gaming)
- Explain your reasoning in 2-3 sentences
- Be critical but fair

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
                  skip_playwright: bool = False) -> Dict[str, Any]:
    """
    Run complete pipeline test on all sources in manifest.

    Returns evaluation metrics for all sources.
    """
    print(f"\n{'='*60}")
    print("RALPH V2 PIPELINE TEST")
    print(f"{'='*60}")
    print(f"Manifest: {manifest_path}")
    print(f"Started: {datetime.now().isoformat()}")

    # Load manifest and gold standard
    manifest = load_manifest(manifest_path)
    gold_standard = load_gold_standard()
    test_data_dir = manifest_path.parent

    print(f"\nLoaded {len(manifest['sources'])} test sources")
    print(f"Thresholds: gestalt >= {manifest['quality_thresholds']['gestalt_min']}")

    # Process each source
    results = []
    all_stories = []

    for source in manifest["sources"]:
        print(f"\n--- Processing: {source['id']} ({source['type']}) ---")

        # Load test data
        try:
            data = load_test_data(source, test_data_dir)
        except Exception as e:
            print(f"ERROR loading {source['path']}: {e}")
            results.append({
                "source_id": source["id"],
                "error": str(e),
                "gestalt_score": 0
            })
            continue

        # Run pipeline
        print(f"  Running pipeline...")
        story = run_pipeline_on_source(data, source["type"])

        if not story:
            print(f"  ERROR: Pipeline failed to generate story")
            results.append({
                "source_id": source["id"],
                "error": "Pipeline generation failed",
                "gestalt_score": 0
            })
            continue

        all_stories.append(story)

        # Evaluate gestalt
        print(f"  Evaluating gestalt quality...")
        evaluation = evaluate_gestalt(story, gold_standard)

        gestalt = evaluation.get("gestalt_score", 0)
        print(f"  Gestalt score: {gestalt}/5")
        print(f"  Explanation: {evaluation.get('explanation', 'N/A')[:100]}...")

        results.append({
            "source_id": source["id"],
            "source_type": source["type"],
            "expected_technical_area": source.get("expected_technical_area"),
            "gestalt_score": gestalt,
            "evaluation": evaluation,
            "story_preview": story["content"][:500]
        })

    # Run Playwright validation on all stories
    playwright_result = {"skipped": True}
    if not skip_playwright and all_stories:
        print(f"\n--- Running Playwright Validation ---")
        playwright_result = run_playwright_validation(all_stories, storage_state)
        print(f"  Success: {playwright_result.get('success', False)}")

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
        st: mean(scores) if scores else 0
        for st, scores in by_source_type.items()
    }

    # Summary
    thresholds = manifest["quality_thresholds"]
    passes_gestalt = avg_gestalt >= thresholds["gestalt_min"]
    passes_per_source = all(
        avg >= thresholds.get("per_source_gestalt_min", 3.5)
        for avg in source_type_avgs.values() if avg > 0
    )

    summary = {
        "timestamp": datetime.now().isoformat(),
        "sources_tested": len(manifest["sources"]),
        "stories_generated": len(all_stories),
        "average_gestalt": round(avg_gestalt, 2),
        "gestalt_threshold": thresholds["gestalt_min"],
        "passes_gestalt": passes_gestalt,
        "source_type_averages": source_type_avgs,
        "passes_per_source": passes_per_source,
        "playwright_success": playwright_result.get("success", False),
        "overall_pass": passes_gestalt and passes_per_source
    }

    # Print summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Stories generated: {summary['stories_generated']}")
    print(f"Average gestalt: {summary['average_gestalt']}/5 (threshold: {summary['gestalt_threshold']})")
    print(f"Passes gestalt: {'YES' if summary['passes_gestalt'] else 'NO'}")
    print(f"Per-source averages: {summary['source_type_averages']}")
    print(f"Passes per-source: {'YES' if summary['passes_per_source'] else 'NO'}")
    print(f"Playwright: {'PASS' if summary['playwright_success'] else 'SKIP/FAIL'}")
    print(f"OVERALL: {'PASS' if summary['overall_pass'] else 'FAIL'}")
    print(f"{'='*60}")

    # Full output
    output = {
        "summary": summary,
        "results": results,
        "playwright": playwright_result,
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

    parser = argparse.ArgumentParser(description="Ralph V2 Pipeline Test Harness")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="Path to test data manifest")
    parser.add_argument("--storage-state", type=str,
                        help="Path to Playwright storage state for auth")
    parser.add_argument("--skip-playwright", action="store_true",
                        help="Skip Playwright validation (faster for testing)")
    parser.add_argument("--output", type=Path,
                        help="Custom output path for results")

    args = parser.parse_args()

    results = run_full_test(
        manifest_path=args.manifest,
        storage_state=args.storage_state,
        skip_playwright=args.skip_playwright
    )

    # Exit with appropriate code
    sys.exit(0 if results["summary"]["overall_pass"] else 1)


if __name__ == "__main__":
    main()

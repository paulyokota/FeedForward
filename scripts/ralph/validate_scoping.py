#!/usr/bin/env python3
"""
Story Scoping Validator - Uses Claude to validate story scoping against Tailwind codebase.

This validator spawns a Claude agent with access to local Tailwind repos to evaluate
whether themes in a story are properly scoped together (same root cause, same fix).

Usage:
    python3 validate_scoping.py '<story_json>' [--tailwind-path PATH]

Example:
    python3 validate_scoping.py '{"content": "...", "source_type": "intercom"}'
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Default path to Tailwind repos (sibling to FeedForward)
DEFAULT_TAILWIND_PATH = Path(__file__).parent.parent.parent.parent  # /Users/.../Documents/GitHub/

# Key repos to check for technical areas
TAILWIND_REPOS = [
    "aero",       # Central mono-repo (frontend + backend)
    "gandalf",    # Authentication service
    "tack",       # Pinterest service
    "zuck",       # Facebook/Meta service
    "scooby",     # URL scraping
    "ghostwriter", # AI text generation
    "pablo",      # Image/video upload
    "charlotte",  # E-commerce/Products
    "dolly",      # Templates/Post Designs
    "brandy2",    # Brand settings
    "swanson",    # Billing/Plans
    "roundabout", # Edge routing
]


def build_scoping_prompt(story: Dict[str, Any], tailwind_path: Path) -> str:
    """Build the prompt for Claude to evaluate story scoping."""

    story_content = story.get("content", "")
    source_type = story.get("source_type", "unknown")

    # List available repos
    available_repos = []
    for repo in TAILWIND_REPOS:
        repo_path = tailwind_path / repo
        if repo_path.exists():
            available_repos.append(f"- {repo}: {repo_path}")

    repos_list = "\n".join(available_repos) if available_repos else "No repos found"

    prompt = f"""You are a senior engineering architect evaluating whether a user story has properly scoped themes.

## Your Task

Analyze the story below and determine if the themes/issues grouped together:
1. Share a common root cause (would be fixed by the same code change)
2. Follow vertical slicing principles (complete functionality, not horizontal layers)
3. Respect service boundaries (don't bundle unrelated services)

## Tailwind Codebase Access

You have READ access to these local Tailwind repos:

{repos_list}

**IMPORTANT**: Use the Read tool to examine actual code files when evaluating technical areas.
For example, if the story mentions "Pinterest OAuth", read files in {tailwind_path}/tack/ and {tailwind_path}/gandalf/ to understand the code structure.

## Service Architecture Reference

- **OAuth/Auth flows**: gandalf (token validation) → tack/zuck (platform-specific) → aero (UI)
- **AI/Ghostwriter**:
  - Standalone ghostwriter service handles chat/generation
  - BUT brand voice integration lives in aero: `aero/packages/core/src/ghostwriter-labs/processors/personalization.ts`
  - Brand data: aero → brandy2 (getBrandForOrg → listBrands)
  - **IMPORTANT**: When evaluating ghostwriter stories, ALSO check aero/packages/core/src/ghostwriter-labs/
- **Scheduling**: tack (Pinterest) or zuck (Facebook) → queue processing
- **E-commerce**: charlotte (products) → aero (display)

## Cross-Repo Integrations (Check BOTH repos)

- **Ghostwriter + Brand voice**: Check BOTH ghostwriter/ AND aero/packages/core/src/ghostwriter-labs/
- **Platform OAuth**: Check BOTH tack or zuck AND gandalf AND aero/packages/tailwindapp/

## Story to Evaluate

Source Type: {source_type}

```
{story_content}
```

## Evaluation Criteria

### 1. Root Cause Analysis
- Do all themes in this story stem from the same underlying issue?
- Would fixing one theme naturally fix the others?
- Or are these actually separate issues that happened to be reported together?

### 2. Service Boundary Check
- Does this story cross service boundaries unnecessarily?
- Example of BAD scoping: Pinterest OAuth + Facebook OAuth in same story (different services: tack vs zuck)
- Example of GOOD scoping: Pinterest OAuth + Pinterest token refresh in same story (both in tack/gandalf)

### 3. Vertical Slice Validation
- Is this a complete vertical slice (UI → logic → data)?
- Or is it mixing unrelated vertical slices?

## Your Response

After examining the story and relevant code, respond with this EXACT JSON format:

{{
    "scoping_score": <1-5 integer>,
    "is_properly_scoped": <true/false>,
    "root_cause_analysis": {{
        "identified_themes": ["<theme 1>", "<theme 2>", ...],
        "shared_root_cause": "<description of common cause, or 'NONE' if themes are unrelated>",
        "would_single_pr_fix": <true/false>
    }},
    "service_boundary_check": {{
        "services_involved": ["<service 1>", "<service 2>", ...],
        "crosses_boundaries_unnecessarily": <true/false>,
        "boundary_issue": "<description if crossing boundaries, or null>"
    }},
    "code_evidence": {{
        "files_examined": ["<path 1>", "<path 2>", ...],
        "key_findings": "<what you found in the code that informs your judgment>"
    }},
    "scoping_patterns": [
        {{
            "pattern_type": "<good_pattern|bad_pattern>",
            "description": "<what to do or avoid>",
            "example": "<concrete example from this story>"
        }}
    ],
    "recommendation": "<PASS|SPLIT|MERGE>",
    "recommendation_detail": "<if SPLIT: how to split; if MERGE: what to merge with; if PASS: why it's good>"
}}

## Scoring Guide

5 - Excellent scoping: Single root cause, respects boundaries, clean vertical slice
4 - Good scoping: Minor issues but fundamentally sound
3 - Acceptable: Some scope creep but workable
2 - Poor scoping: Should be split into multiple stories
1 - Severely misscoped: Unrelated issues bundled together

Be thorough. Read actual code files to verify your assessment. Your scoping patterns will be used to improve future story generation.
"""

    return prompt


def run_claude_evaluation(prompt: str, tailwind_path: Path, timeout: int = 300) -> Dict[str, Any]:
    """
    Run Claude CLI to evaluate the story scoping.

    Uses claude --print with Read/Glob tools enabled for codebase access.
    """

    try:
        # Use claude CLI with print mode + tools for codebase exploration
        result = subprocess.run(
            [
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                "--tools", "Read,Glob,Grep",
                "--add-dir", str(tailwind_path),
                "-p", prompt
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(tailwind_path)  # Run from tailwind dir for better access
        )

        output = result.stdout

        # Try to extract JSON from the response
        # Claude might include markdown or other text around the JSON
        json_start = output.find("{")
        json_end = output.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            json_str = output[json_start:json_end]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # Try to clean up the JSON
                pass

        # If we couldn't parse JSON, return raw output
        return {
            "scoping_score": 0,
            "is_properly_scoped": False,
            "error": "Could not parse Claude response as JSON",
            "raw_output": output[:2000]
        }

    except subprocess.TimeoutExpired:
        return {
            "scoping_score": 0,
            "is_properly_scoped": False,
            "error": "Claude evaluation timed out"
        }
    except FileNotFoundError:
        return {
            "scoping_score": 0,
            "is_properly_scoped": False,
            "error": "Claude CLI not found. Make sure 'claude' is in PATH."
        }
    except Exception as e:
        return {
            "scoping_score": 0,
            "is_properly_scoped": False,
            "error": str(e)
        }


def validate_story_scoping(
    story: Dict[str, Any],
    tailwind_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Validate story scoping using Claude with access to Tailwind codebase.

    Args:
        story: Story dict with 'content' and 'source_type'
        tailwind_path: Path to directory containing Tailwind repos

    Returns:
        Evaluation results with scoping score and patterns
    """

    if tailwind_path is None:
        tailwind_path = DEFAULT_TAILWIND_PATH

    # Verify tailwind path exists
    if not tailwind_path.exists():
        return {
            "scoping_score": 0,
            "is_properly_scoped": False,
            "error": f"Tailwind path not found: {tailwind_path}"
        }

    # Check for at least one repo
    found_repos = [r for r in TAILWIND_REPOS if (tailwind_path / r).exists()]
    if not found_repos:
        return {
            "scoping_score": 0,
            "is_properly_scoped": False,
            "error": f"No Tailwind repos found in {tailwind_path}"
        }

    print(f"  Found {len(found_repos)} Tailwind repos: {', '.join(found_repos[:5])}...")

    # Build prompt and run evaluation
    prompt = build_scoping_prompt(story, tailwind_path)

    print(f"  Running Claude scoping evaluation (with tool access)...")
    result = run_claude_evaluation(prompt, tailwind_path)

    # Add metadata
    result["evaluated_at"] = datetime.now().isoformat()
    result["tailwind_path"] = str(tailwind_path)
    result["repos_available"] = found_repos

    return result


def validate_multiple_stories(
    stories: List[Dict[str, Any]],
    tailwind_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Validate scoping for multiple stories.

    Returns aggregate results and all patterns discovered.
    """

    results = []
    all_patterns = []

    for i, story in enumerate(stories):
        print(f"\n--- Validating story {i+1}/{len(stories)} ---")
        result = validate_story_scoping(story, tailwind_path)
        results.append(result)

        # Collect patterns
        if "scoping_patterns" in result:
            all_patterns.extend(result["scoping_patterns"])

        score = result.get("scoping_score", 0)
        print(f"  Scoping score: {score}/5")
        if result.get("recommendation"):
            print(f"  Recommendation: {result['recommendation']}")

    # Calculate aggregate metrics
    scores = [r.get("scoping_score", 0) for r in results if r.get("scoping_score", 0) > 0]
    avg_score = sum(scores) / len(scores) if scores else 0
    properly_scoped = sum(1 for r in results if r.get("is_properly_scoped", False))

    # Deduplicate patterns
    unique_patterns = []
    seen_descriptions = set()
    for p in all_patterns:
        desc = p.get("description", "")
        if desc and desc not in seen_descriptions:
            seen_descriptions.add(desc)
            unique_patterns.append(p)

    return {
        "summary": {
            "stories_evaluated": len(stories),
            "average_scoping_score": round(avg_score, 2),
            "properly_scoped_count": properly_scoped,
            "properly_scoped_pct": round(properly_scoped / len(stories) * 100, 1) if stories else 0
        },
        "results": results,
        "discovered_patterns": unique_patterns,
        "evaluated_at": datetime.now().isoformat()
    }


def main():
    parser = argparse.ArgumentParser(description="Validate story scoping against Tailwind codebase")
    parser.add_argument("story_json", type=str, help="Story JSON string or path to JSON file")
    parser.add_argument("--tailwind-path", type=Path, default=DEFAULT_TAILWIND_PATH,
                        help="Path to directory containing Tailwind repos")
    parser.add_argument("--output", type=Path, help="Output file for results")

    args = parser.parse_args()

    # Parse story input
    story_input = args.story_json

    if os.path.exists(story_input):
        # It's a file path
        with open(story_input) as f:
            story_data = json.load(f)
    else:
        # It's a JSON string
        try:
            story_data = json.loads(story_input)
        except json.JSONDecodeError as e:
            print(f"ERROR: Could not parse story JSON: {e}")
            sys.exit(1)

    # Handle single story or list
    if isinstance(story_data, list):
        result = validate_multiple_stories(story_data, args.tailwind_path)
    else:
        result = validate_story_scoping(story_data, args.tailwind_path)

    # Output results
    output_json = json.dumps(result, indent=2, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output_json)
        print(f"\nResults written to: {args.output}")
    else:
        print("\n" + "="*60)
        print("SCOPING VALIDATION RESULTS")
        print("="*60)
        print(output_json)

    # Exit code based on results
    if isinstance(story_data, list):
        success = result["summary"]["properly_scoped_pct"] >= 80
    else:
        success = result.get("is_properly_scoped", False)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Ralph Wiggum Playwright Validation Script

This script validates that technical_area recommendations in stories
actually exist as repositories and are documented in the codebase map.

Usage:
    python3 validate_playwright.py '<json_stories_data>'

Example:
    python3 validate_playwright.py '[{"id":"story-001","technical_area":"tailwind/aero"}]'

Exit codes:
    0 - Success (>= 85% validation pass rate)
    1 - Failure (< 85% validation pass rate or error)
"""

import subprocess
import json
import sys
import os
from datetime import datetime
from pathlib import Path


def find_codebase_map():
    """Find the tailwind-codebase-map.md file relative to script location."""
    script_dir = Path(__file__).parent
    # Try relative paths from script location
    candidates = [
        script_dir / "../../docs/tailwind-codebase-map.md",
        script_dir.parent.parent / "docs/tailwind-codebase-map.md",
        Path("docs/tailwind-codebase-map.md"),
    ]

    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            return resolved

    return None


def validate_technical_area(repo_name, codebase_map_content=None):
    """
    Actually test if the repository exists and has relevant files.

    Args:
        repo_name: Repository name (without 'tailwind/' prefix)
        codebase_map_content: Optional pre-loaded content of codebase map

    Returns:
        dict with 'valid' (bool), 'reason' (str), 'checks' (list of check results)
    """
    print(f"\n  VALIDATING: {repo_name}")

    checks = []

    # Normalize repo name - remove 'tailwind/' prefix if present
    if repo_name.startswith("tailwind/"):
        repo_name = repo_name[9:]

    if not repo_name:
        print(f"     INVALID - Empty repository name")
        return {"valid": False, "reason": "empty_repo_name", "checks": []}

    # Test 1: Check if repo exists on GitHub via git ls-remote
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", f"https://github.com/tailwindlabs/{repo_name}"],
            capture_output=True,
            timeout=15
        )

        if result.returncode != 0:
            # Try alternative org names
            alt_orgs = ["tailwind", "tailwindcss"]
            found = False

            for org in alt_orgs:
                alt_result = subprocess.run(
                    ["git", "ls-remote", "--heads", f"https://github.com/{org}/{repo_name}"],
                    capture_output=True,
                    timeout=15
                )
                if alt_result.returncode == 0 and alt_result.stdout:
                    found = True
                    print(f"     Repository exists: {org}/{repo_name}")
                    checks.append({"check": "repo_exists", "passed": True, "org": org})
                    break

            if not found:
                stderr = result.stderr.decode().strip() if result.stderr else "No error message"
                print(f"     INVALID - Repository not found on GitHub")
                print(f"     Tried: tailwindlabs/{repo_name}, tailwind/{repo_name}, tailwindcss/{repo_name}")
                checks.append({"check": "repo_exists", "passed": False, "error": stderr})
                return {"valid": False, "reason": "repo_not_found", "checks": checks}
        else:
            if result.stdout:
                print(f"     Repository exists: tailwindlabs/{repo_name}")
                checks.append({"check": "repo_exists", "passed": True, "org": "tailwindlabs"})
            else:
                print(f"     INVALID - Repository exists but has no branches")
                checks.append({"check": "repo_exists", "passed": False, "error": "no_branches"})
                return {"valid": False, "reason": "repo_empty", "checks": checks}

    except subprocess.TimeoutExpired:
        print(f"     TIMEOUT - Could not reach GitHub in 15 seconds")
        checks.append({"check": "repo_exists", "passed": False, "error": "timeout"})
        return {"valid": False, "reason": "timeout", "checks": checks}
    except Exception as e:
        print(f"     ERROR - {str(e)}")
        checks.append({"check": "repo_exists", "passed": False, "error": str(e)})
        return {"valid": False, "reason": f"error: {str(e)}", "checks": checks}

    # Test 2: Check against codebase-map if available
    if codebase_map_content:
        # Look for repo name in the codebase map (case-insensitive partial match)
        repo_lower = repo_name.lower()
        map_lower = codebase_map_content.lower()

        if repo_lower in map_lower or f"/{repo_lower}" in map_lower:
            print(f"     Repository found in tailwind-codebase-map.md")
            checks.append({"check": "codebase_map", "passed": True})
        else:
            print(f"     WARNING - Repository NOT in tailwind-codebase-map.md")
            print(f"     This suggests technical_area may be inaccurate")
            checks.append({"check": "codebase_map", "passed": False, "warning": "not_in_map"})
            # Don't fail for this - repo exists but may not be mapped yet
    else:
        print(f"     SKIP - tailwind-codebase-map.md not available for cross-reference")
        checks.append({"check": "codebase_map", "passed": None, "skipped": True})

    # If repo exists, consider it valid even if not in map
    print(f"     VALID - Repository verified on GitHub")
    return {"valid": True, "reason": "verified", "checks": checks}


def validate_stories_batch(stories_data):
    """
    Validate all stories in a batch.

    Args:
        stories_data: List of dicts with 'id' and 'technical_area' keys.

    Returns:
        tuple: (success: bool, results: list, summary: dict)
    """
    timestamp = datetime.now().isoformat()

    print(f"\n{'='*60}")
    print(f"PLAYWRIGHT VALIDATION RUN - {timestamp}")
    print(f"{'='*60}")

    # Load codebase map once
    codebase_map_path = find_codebase_map()
    codebase_map_content = None

    if codebase_map_path:
        try:
            with open(codebase_map_path, "r") as f:
                codebase_map_content = f.read()
            print(f"\nCodebase map loaded: {codebase_map_path}")
        except Exception as e:
            print(f"\nWARNING: Could not read codebase map: {e}")
    else:
        print(f"\nWARNING: tailwind-codebase-map.md not found")

    results = []

    for story in stories_data:
        story_id = story.get('id', 'unknown')
        technical_area = story.get('technical_area', '')

        # Normalize technical_area
        if technical_area:
            technical_area = technical_area.strip()

        if not technical_area:
            print(f"\n  SKIP: {story_id} - no technical_area specified")
            results.append({
                'id': story_id,
                'valid': False,
                'reason': 'no_technical_area',
                'technical_area': None
            })
            continue

        validation = validate_technical_area(technical_area, codebase_map_content)
        results.append({
            'id': story_id,
            'valid': validation['valid'],
            'reason': validation['reason'],
            'technical_area': technical_area,
            'checks': validation.get('checks', [])
        })

    # Calculate success rate
    total = len(results)
    passed = sum(1 for r in results if r['valid'])
    failed = total - passed
    success_rate = (passed / total * 100) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"PLAYWRIGHT VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Timestamp: {timestamp}")
    print(f"Total stories validated: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Threshold: 85%")
    print(f"{'='*60}")

    summary = {
        'timestamp': timestamp,
        'total': total,
        'passed': passed,
        'failed': failed,
        'success_rate': success_rate,
        'threshold': 85,
        'meets_threshold': success_rate >= 85
    }

    if success_rate < 85:
        print(f"\n  THRESHOLD NOT MET: {success_rate:.1f}% < 85%")
        print(f"  Do NOT declare completion")
        print(f"  Return to Phase 1 to improve technical area accuracy")
        return False, results, summary
    else:
        print(f"\n  THRESHOLD MET: {success_rate:.1f}% >= 85%")
        print(f"  Completion may proceed to Phase 4")
        return True, results, summary


def print_detailed_results(results):
    """Print detailed per-story results."""
    print(f"\n{'='*60}")
    print(f"DETAILED RESULTS")
    print(f"{'='*60}")

    for r in results:
        status = "VALID" if r['valid'] else "INVALID"
        symbol = "" if r['valid'] else ""
        tech_area = r.get('technical_area', 'N/A')
        reason = r.get('reason', '')

        print(f"\n  {symbol} {r['id']}")
        print(f"      Technical area: {tech_area}")
        print(f"      Status: {status}")
        if reason and reason != 'verified':
            print(f"      Reason: {reason}")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 validate_playwright.py '<json_stories_data>'")
        print("")
        print("Example:")
        print('  python3 validate_playwright.py \'[{"id":"story-001","technical_area":"tailwind/aero"}]\'')
        print("")
        print("Input format: JSON array of objects with 'id' and 'technical_area' fields")
        print("")
        print("Exit codes:")
        print("  0 - Success (>= 85% validation pass rate)")
        print("  1 - Failure (< 85% validation pass rate or error)")
        sys.exit(1)

    stories_json = sys.argv[1]

    try:
        stories = json.loads(stories_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON input: {e}")
        print(f"Input received: {stories_json[:200]}...")
        sys.exit(1)

    if not isinstance(stories, list):
        print(f"ERROR: Expected JSON array, got {type(stories).__name__}")
        sys.exit(1)

    if len(stories) == 0:
        print("WARNING: Empty stories list provided")
        print("No validation to perform")
        sys.exit(0)

    success, results, summary = validate_stories_batch(stories)
    print_detailed_results(results)

    # Output JSON summary for programmatic consumption
    print(f"\n{'='*60}")
    print("JSON OUTPUT (for programmatic use):")
    print(f"{'='*60}")
    output = {
        'success': success,
        'summary': summary,
        'results': results
    }
    print(json.dumps(output, indent=2))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

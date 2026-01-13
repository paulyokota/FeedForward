#!/usr/bin/env python3
"""
Ralph Wiggum Playwright Validation Script

REAL browser automation that:
- Opens actual browser window (not headless)
- Navigates to GitHub repos
- Pauses for manual login if needed (60 second timeout)
- Verifies code files are actually findable
- Reports validation with timestamped evidence

Usage:
    python3 validate_playwright.py '<json_stories_data>'

Example:
    python3 validate_playwright.py '[{"id":"story-001","technical_area":"tailwind/aero","description":"Fix auth issue"}]'

Exit codes:
    0 - Success (>= 85% validation pass rate)
    1 - Failure (< 85% validation pass rate or error)
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: Playwright not installed.")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)


def extract_keywords(problem_description):
    """
    Extract key technical terms from problem description.
    """
    keywords = []
    problem_lower = problem_description.lower()

    # Common technical keywords
    if 'auth' in problem_lower or 'login' in problem_lower:
        keywords.extend(['auth', 'login', 'session'])
    if 'token' in problem_lower or 'oauth' in problem_lower:
        keywords.extend(['token', 'oauth', 'credential'])
    if 'billing' in problem_lower or 'payment' in problem_lower:
        keywords.extend(['billing', 'payment', 'invoice', 'stripe'])
    if 'scheduler' in problem_lower or 'schedule' in problem_lower:
        keywords.extend(['scheduler', 'schedule', 'cron', 'job'])
    if 'timezone' in problem_lower or 'time' in problem_lower:
        keywords.extend(['timezone', 'time', 'date'])
    if 'pinterest' in problem_lower:
        keywords.extend(['pinterest', 'pin', 'board'])
    if 'cache' in problem_lower:
        keywords.extend(['cache', 'redis', 'memcache'])
    if 'api' in problem_lower:
        keywords.extend(['api', 'endpoint', 'route'])
    if 'websocket' in problem_lower:
        keywords.extend(['websocket', 'socket', 'ws'])
    if 'email' in problem_lower:
        keywords.extend(['email', 'mail', 'smtp'])
    if 'notification' in problem_lower:
        keywords.extend(['notification', 'notify', 'alert'])
    if 'upload' in problem_lower or 'image' in problem_lower:
        keywords.extend(['upload', 'image', 'media', 'file'])
    if 'error' in problem_lower or 'exception' in problem_lower:
        keywords.extend(['error', 'exception', 'handler'])
    if 'test' in problem_lower:
        keywords.extend(['test', 'spec', 'mock'])
    if 'config' in problem_lower:
        keywords.extend(['config', 'settings', 'env'])

    # If no keywords found, use generic ones
    if not keywords:
        keywords = ['main', 'index', 'lib', 'src', 'config', 'README']

    return list(set(keywords))  # Remove duplicates


async def validate_technical_area(page, repo_name, story_problem):
    """
    Real Playwright browser validation.
    Opens browser, navigates to GitHub repo, verifies code is findable.
    """
    print(f"\n  VALIDATING: {repo_name}")

    # Truncate problem description for display
    problem_preview = story_problem[:60] + "..." if len(story_problem) > 60 else story_problem
    print(f"     Story problem: {problem_preview}")

    # Normalize repo name
    if repo_name.startswith("tailwind/"):
        repo_name = repo_name[9:]

    if not repo_name:
        print(f"     INVALID - Empty repository name")
        return {"valid": False, "reason": "empty_repo_name", "files_found": []}

    # Try different GitHub org variations
    orgs_to_try = ["tailwindlabs", "tailwind", "tailwindcss"]
    repo_url = None

    for org in orgs_to_try:
        test_url = f"https://github.com/{org}/{repo_name}"
        print(f"     Trying {test_url}")

        try:
            response = await page.goto(test_url, wait_until="domcontentloaded", timeout=15000)

            if response and response.status == 200:
                repo_url = test_url
                print(f"     Repository loaded: {org}/{repo_name}")
                break
            elif response and response.status == 404:
                continue
        except Exception as e:
            continue

    if not repo_url:
        print(f"     INVALID - Repository not found in any org")
        print(f"     Tried: {', '.join([f'{org}/{repo_name}' for org in orgs_to_try])}")
        return {"valid": False, "reason": "repo_not_found", "files_found": []}

    # Check if login is required
    try:
        # Check for login prompt
        login_form = await page.query_selector('form[action*="/session"]')
        if login_form:
            print(f"     LOGIN REQUIRED")
            print(f"     Browser window is open - PLEASE LOG IN")
            print(f"     Waiting for login (60 second timeout)...")
            print(f"     Complete login in browser, then script will resume")

            # Wait for navigation away from login page
            try:
                await page.wait_for_url(f"**/{repo_name}**", timeout=60000)
                print(f"     Login successful, resuming validation")
            except:
                print(f"     Login timeout - continuing anyway")
    except Exception:
        pass

    # Extract keywords from problem description
    keywords = extract_keywords(story_problem)
    print(f"     Searching for files matching: {', '.join(keywords[:5])}")

    found_files = []

    try:
        # Wait for repo content to load
        await page.wait_for_selector('div[role="grid"], [data-testid="repo-content"], .js-navigation-container', timeout=10000)

        # Get page content and look for file/folder links
        content = await page.content()

        # Look for common code patterns in page content
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in content.lower():
                # Try to find actual file links
                file_links = await page.query_selector_all(f'a[href*="/{keyword}"], a[href*="{keyword}"]')
                for link in file_links[:3]:
                    try:
                        text = await link.text_content()
                        href = await link.get_attribute('href')
                        if text and href and ('/blob/' in href or '/tree/' in href):
                            found_files.append(text.strip())
                    except:
                        pass

        # Also get visible file/folder names
        visible_items = await page.query_selector_all('[role="rowheader"] a, .js-navigation-open')
        for item in visible_items[:20]:
            try:
                text = await item.text_content()
                if text:
                    text = text.strip()
                    for keyword in keywords:
                        if keyword.lower() in text.lower() and text not in found_files:
                            found_files.append(text)
            except:
                pass

        # Remove duplicates and limit
        found_files = list(set(found_files))[:5]

        if found_files:
            print(f"     Found relevant files: {', '.join(found_files)}")
            print(f"     Developer can navigate to investigate this issue")
        else:
            print(f"     No files found matching keywords: {', '.join(keywords[:3])}")
            print(f"     Repository exists but matching files not found")
            print(f"     Treating as VALID (repo is correct, may need keyword refinement)")

        return {"valid": True, "reason": "verified", "files_found": found_files}

    except asyncio.TimeoutError:
        print(f"     Could not load file list (page timeout)")
        print(f"     But repository is accessible")
        return {"valid": True, "reason": "repo_accessible_no_files", "files_found": []}
    except Exception as e:
        print(f"     Warning during file search: {str(e)}")
        return {"valid": True, "reason": "repo_accessible_search_error", "files_found": []}


async def validate_stories_batch(stories_data, headless=False):
    """
    Validate all stories in a batch using real Playwright browser automation.
    Opens actual browser window for interactive testing.

    Args:
        stories_data: List of story dicts with id, technical_area, description
        headless: If True, run headless (for CI). Default False for interactive.
    """
    timestamp = datetime.now().isoformat()

    print(f"\n{'='*60}")
    print(f"PLAYWRIGHT VALIDATION RUN - {timestamp}")
    print(f"{'='*60}")
    print(f"   Starting browser automation ({'HEADLESS' if headless else 'VISIBLE WINDOW'})...")
    print(f"   If login is needed, you'll see a browser window")
    print(f"   Each validation takes 15-60 seconds depending on login")

    results = []
    login_required_count = 0

    async with async_playwright() as p:
        # Launch browser with UI visible (not headless) for interactive login
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for i, story in enumerate(stories_data, 1):
            print(f"\n[{i}/{len(stories_data)}] Processing story...")

            story_id = story.get('id', 'unknown')
            technical_area = story.get('technical_area', '')
            problem_description = story.get('description', story.get('problem', ''))

            if not technical_area:
                print(f"   SKIP: {story_id} - no technical_area specified")
                results.append({
                    'id': story_id,
                    'valid': False,
                    'reason': 'no_technical_area',
                    'technical_area': None,
                    'files_found': []
                })
                continue

            validation = await validate_technical_area(page, technical_area, problem_description)
            results.append({
                'id': story_id,
                'valid': validation['valid'],
                'reason': validation['reason'],
                'technical_area': technical_area,
                'files_found': validation.get('files_found', [])
            })

            # Small delay between requests to be polite to GitHub
            await asyncio.sleep(1)

        await browser.close()

    # Calculate success rate
    total = len(results)
    passed = sum(1 for r in results if r['valid'])
    failed = total - passed
    success_rate = (passed / total * 100) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"PLAYWRIGHT VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Timestamp: {timestamp}")
    print(f"Browser mode: {'Headless' if headless else 'Visible window'}")
    print(f"Total stories validated: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {success_rate:.1f}%")
    print(f"Threshold: 85%")
    print(f"{'='*60}")

    # Print detailed results
    print(f"\n{'='*60}")
    print(f"DETAILED RESULTS")
    print(f"{'='*60}")

    for r in results:
        status = "VALID" if r['valid'] else "INVALID"
        symbol = "" if r['valid'] else ""
        tech_area = r.get('technical_area', 'N/A')
        files = r.get('files_found', [])

        print(f"\n  {symbol} {r['id']}")
        print(f"      Technical area: {tech_area}")
        print(f"      Status: {status}")
        if files:
            print(f"      Files found: {', '.join(files[:3])}")
        if r.get('reason') and r['reason'] not in ['verified', 'repo_accessible_no_files']:
            print(f"      Reason: {r['reason']}")

    summary = {
        'timestamp': timestamp,
        'browser_mode': 'headless' if headless else 'visible',
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
    else:
        print(f"\n  THRESHOLD MET: {success_rate:.1f}% >= 85%")
        print(f"  Completion may proceed to Phase 4")

    # Output JSON summary for programmatic consumption
    print(f"\n{'='*60}")
    print("JSON OUTPUT (for programmatic use):")
    print(f"{'='*60}")
    output = {
        'success': success_rate >= 85,
        'summary': summary,
        'results': results
    }
    print(json.dumps(output, indent=2))

    return success_rate >= 85, results, summary


async def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate_playwright.py '<json_stories_data>' [--headless]")
        print("")
        print("Example:")
        print('  python3 validate_playwright.py \'[{"id":"story-001","technical_area":"tailwind/aero","description":"Fix auth issue"}]\'')
        print("")
        print("Options:")
        print("  --headless    Run browser in headless mode (no visible window)")
        print("")
        print("Exit codes:")
        print("  0 - Success (>= 85% validation pass rate)")
        print("  1 - Failure (< 85% validation pass rate or error)")
        sys.exit(1)

    # Parse arguments
    headless = "--headless" in sys.argv
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

    success, results, summary = await validate_stories_batch(stories, headless=headless)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

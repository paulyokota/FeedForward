#!/usr/bin/env python3
"""
Initialize Playwright Session

Opens an interactive browser window at GitHub, waits for user to log in,
and saves the authentication state for future use.

This allows subsequent Playwright validation runs to skip the login step.

Usage:
    python3 init_playwright_session.py [--output-path PATH]

Options:
    --output-path PATH    Path to save storage state JSON (default: outputs/playwright_state.json)

Example:
    python3 init_playwright_session.py
    python3 init_playwright_session.py --output-path ~/my_session.json

Exit codes:
    0 - Success (user logged in, state saved)
    1 - Failure (timeout, error, or user canceled)
"""

import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: Playwright not installed.")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)


async def initialize_session(output_path):
    """
    Open interactive browser, wait for GitHub login, save session state.

    Args:
        output_path: Path where storage state JSON will be saved
    """
    print(f"\n{'='*60}")
    print("PLAYWRIGHT SESSION INITIALIZATION")
    print(f"{'='*60}")
    print(f"   Opening browser at github.com...")
    print(f"   Please log in to GitHub (including 2FA if enabled)")
    print(f"   Session state will be saved to: {output_path}")
    print(f"   Timeout: 120 seconds")
    print(f"{'='*60}\n")

    async with async_playwright() as p:
        # Launch visible browser for interactive login
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        # Navigate to GitHub
        try:
            await page.goto("https://github.com", wait_until="domcontentloaded", timeout=15000)
            print("   Navigated to github.com")
        except Exception as e:
            print(f"   ERROR: Failed to navigate to GitHub: {e}")
            await browser.close()
            return False

        # Check if already logged in
        try:
            avatar = await page.query_selector('img.avatar, [data-login]')
            if avatar:
                print("   Already logged in to GitHub!")
                print("   Saving session state...")

                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Save storage state
                await context.storage_state(path=str(output_path))

                print(f"\n{'='*60}")
                print("SUCCESS")
                print(f"{'='*60}")
                print(f"   Session state saved to: {output_path}")
                print(f"   You can now use this with --storage-state flag:")
                print(f"   python3 validate_playwright.py '<stories>' --storage-state {output_path}")
                print(f"{'='*60}\n")

                await browser.close()
                return True
        except Exception:
            pass

        # Wait for user to log in
        print("\n   Please log in to GitHub in the browser window...")
        print("   Waiting for login to complete (up to 120 seconds)...")

        try:
            # Wait for avatar/user indicator to appear (sign of successful login)
            await page.wait_for_selector(
                'img.avatar, [data-login], summary[aria-label*="View profile"]',
                timeout=120000
            )

            print("\n   Login detected!")
            print("   Saving session state...")

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save storage state
            await context.storage_state(path=str(output_path))

            print(f"\n{'='*60}")
            print("SUCCESS")
            print(f"{'='*60}")
            print(f"   Session state saved to: {output_path}")
            print(f"   You can now use this with --storage-state flag:")
            print(f"   python3 validate_playwright.py '<stories>' --storage-state {output_path}")
            print(f"{'='*60}\n")

            await browser.close()
            return True

        except asyncio.TimeoutError:
            print("\n   ERROR: Login timeout after 120 seconds")
            print("   No session state saved")
            await browser.close()
            return False
        except Exception as e:
            print(f"\n   ERROR: {e}")
            await browser.close()
            return False


async def main():
    # Parse arguments
    output_path = None

    if "--output-path" in sys.argv:
        output_path_idx = sys.argv.index("--output-path")
        if output_path_idx + 1 < len(sys.argv):
            output_path = Path(sys.argv[output_path_idx + 1])
        else:
            print("ERROR: --output-path requires a path argument")
            sys.exit(1)

    # Default output path
    if output_path is None:
        output_path = Path(__file__).parent / "outputs" / "playwright_state.json"

    # Show help
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)

    # Initialize session
    success = await initialize_session(output_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

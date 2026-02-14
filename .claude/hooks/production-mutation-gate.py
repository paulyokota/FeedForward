#!/usr/bin/env python3
"""
PreToolUse hook: Production Mutation Gate

Blocks Bash commands that would mutate production surfaces (Slack, Shortcut)
and directs Claude to use agenterminal.execute_approved instead.

This is a deterministic enforcement layer. Advisory instructions in CLAUDE.md
failed to prevent a batch of 91 unreviewed Slack mutations on 2026-02-13.
This hook ensures production mutations cannot bypass human approval.

Detection targets:
  Slack:    chat.update, chat.postMessage, chat.delete, reactions.add, reactions.remove
  Shortcut: any PUT/POST/DELETE to api.app.shortcut.com

Safe operations pass through:
  Slack:    conversations.replies, conversations.history (reads)
  Shortcut: GET requests (search, fetch)

Exit codes:
  0  = allow (not a mutation, or not a Bash call)
  2  = block (mutation detected, stderr message fed back to Claude)
"""

from __future__ import annotations

import json
import re
import sys

# Slack mutation endpoints (the API method appears in the URL path)
SLACK_MUTATION_PATTERNS = [
    r"slack\.com/api/chat\.update",
    r"slack\.com/api/chat\.postMessage",
    r"slack\.com/api/chat\.delete",
    r"slack\.com/api/reactions\.add",
    r"slack\.com/api/reactions\.remove",
]

# chat.delete is permanent and unrecoverable
SLACK_DELETE_PATTERN = r"slack\.com/api/chat\.delete"

# Shortcut mutations: PUT/POST/DELETE to the API
# We need both the domain AND a mutating HTTP method
SHORTCUT_DOMAIN_PATTERN = r"api\.app\.shortcut\.com"
SHORTCUT_MUTATING_METHOD = r"-X\s*(PUT|POST|DELETE|PATCH)"


def detect_slack_mutation(command: str) -> str | None:
    """Returns the matched endpoint name, or None if no mutation detected."""
    for pattern in SLACK_MUTATION_PATTERNS:
        if re.search(pattern, command):
            # Extract the method name for the message
            match = re.search(r"slack\.com/api/([\w.]+)", command)
            return match.group(1) if match else "unknown"
    return None


def detect_shortcut_mutation(command: str) -> str | None:
    """Returns the HTTP method if a Shortcut mutation is detected, or None."""
    if re.search(SHORTCUT_DOMAIN_PATTERN, command):
        method_match = re.search(SHORTCUT_MUTATING_METHOD, command)
        if method_match:
            return method_match.group(1)
        # Python HTTP libraries might not use -X explicitly.
        # Check for requests.put/post/delete patterns
        if re.search(r"requests\.(put|post|delete|patch)\s*\(", command):
            method_match = re.search(r"requests\.(put|post|delete|patch)", command)
            return method_match.group(1).upper() if method_match else None
        # Check for httpx.put/post/delete patterns
        if re.search(r"httpx\.(put|post|delete|patch)\s*\(", command):
            method_match = re.search(r"httpx\.(put|post|delete|patch)", command)
            return method_match.group(1).upper() if method_match else None
        # Check for urllib.request with method= specifying a mutating method
        if re.search(r"method\s*=\s*['\"]?(PUT|POST|DELETE|PATCH)", command, re.IGNORECASE):
            method_match = re.search(r"method\s*=\s*['\"]?(PUT|POST|DELETE|PATCH)", command, re.IGNORECASE)
            return method_match.group(1).upper() if method_match else None
        # If it's just a curl with no -X and hitting shortcut, check for -d/--data
        # which implies POST
        if re.search(r"curl\b", command) and re.search(r"(-d\s|--data)", command):
            return "POST"
    return None


def deny(reason: str):
    """Block the tool call with a reason fed back to Claude."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))
    sys.exit(0)


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"production-mutation-gate: invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    # Check for Slack mutations
    slack_method = detect_slack_mutation(command)
    if slack_method:
        is_delete = bool(re.search(SLACK_DELETE_PATTERN, command))
        if is_delete:
            deny(
                f"BLOCKED: Slack chat.delete detected. This is a PERMANENT deletion "
                f"with no undo. You MUST: (1) save the full message content to a file "
                f"first, (2) present the exact change to the user and get explicit "
                f"approval before executing. Use agenterminal.execute_approved if "
                f"available, otherwise show the command and ask the user to run it."
            )
        else:
            deny(
                f"BLOCKED: Slack mutation detected ({slack_method}). Production "
                f"surface mutations require human approval. Present the exact change "
                f"to the user and get explicit approval. Use "
                f"agenterminal.execute_approved if available, otherwise show the "
                f"command and ask the user to run it."
            )

    # Check for Shortcut mutations
    shortcut_method = detect_shortcut_mutation(command)
    if shortcut_method:
        deny(
            f"BLOCKED: Shortcut mutation detected ({shortcut_method} to "
            f"api.app.shortcut.com). Production surface mutations require human "
            f"approval. Present the exact change to the user and get explicit "
            f"approval. Use agenterminal.execute_approved if available, otherwise "
            f"show the command and ask the user to run it."
        )

    # Not a production mutation — allow
    sys.exit(0)


if __name__ == "__main__":
    main()

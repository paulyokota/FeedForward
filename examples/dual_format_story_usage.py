"""
Example usage of DualStoryFormatter.

This demonstrates how to use the dual-format story generator
with and without codebase context.
"""

from src.story_formatter import DualStoryFormatter

# Example 1: Basic story without codebase context
print("=" * 80)
print("Example 1: Basic Dual-Format Story")
print("=" * 80)

formatter = DualStoryFormatter()

theme_data = {
    "issue_signature": "login_timeout_error",
    "title": "Fix Login Timeout Error",
    "product_area": "Authentication",
    "component": "auth_service",
    "user_type": "Tailwind user trying to log in",
    "user_intent": "log in without timeout errors",
    "benefit": "access my account reliably",
    "symptoms": [
        "User attempts to log in",
        "Login succeeds after 30 seconds",
        "Timeout error does not display properly",
    ],
    "root_cause_hypothesis": "Slow database query in authentication flow",
    "occurrences": 8,
    "first_seen": "2026-01-01",
    "last_seen": "2026-01-14",
    "task_type": "bug-fix",
}

evidence_data = {
    "customer_messages": [
        {"text": "I can't log in, it times out every time"},
        {"text": "Login is very slow, takes 30+ seconds"},
        "Sometimes I get an error, sometimes it just hangs",
    ]
}

result = formatter.format_story(theme_data, evidence_data=evidence_data)

print(f"\n✅ Generated story (format: {result.format_version})")
print(f"📅 Generated at: {result.generated_at}")
print(f"\n{'='*80}")
print("HUMAN SECTION PREVIEW (first 500 chars):")
print(f"{'='*80}")
print(result.human_section[:500] + "...")
print(f"\n{'='*80}")
print("AI SECTION PREVIEW (first 500 chars):")
print(f"{'='*80}")
print(result.ai_section[:500] + "...")

# Example 2: Story with codebase context
print("\n\n" + "=" * 80)
print("Example 2: Story with Codebase Context")
print("=" * 80)

try:
    from src.story_tracking.services.codebase_context_provider import (
        ExplorationResult,
        FileReference,
        CodeSnippet,
    )

    exploration_result = ExplorationResult(
        relevant_files=[
            FileReference(
                path="src/auth/login_handler.py",
                line_start=45,
                line_end=67,
                relevance="3 matches: timeout, database_query, login",
            ),
            FileReference(
                path="src/auth/database.py",
                line_start=120,
                relevance="2 matches: slow_query, authentication",
            ),
        ],
        code_snippets=[
            CodeSnippet(
                file_path="src/auth/login_handler.py",
                line_start=45,
                line_end=55,
                content='''def handle_login(username, password):
    """Process user login."""
    # This query is slow - need optimization
    user = db.query(User).filter(
        User.username == username
    ).first()
    return authenticate(user, password)''',
                language="python",
                context="Main login handler - database query needs optimization",
            )
        ],
        investigation_queries=[
            "SELECT * FROM users WHERE last_login > NOW() - INTERVAL '7 days';",
            "grep -r 'authenticate' src/auth/",
        ],
        exploration_duration_ms=1250,
        success=True,
    )

    result_with_context = formatter.format_story(
        theme_data, exploration_result=exploration_result, evidence_data=evidence_data
    )

    print(f"\n✅ Generated story with codebase context")
    print(f"📁 Files found: {len(exploration_result.relevant_files)}")
    print(f"📝 Snippets extracted: {len(exploration_result.code_snippets)}")
    print(f"🔍 Investigation queries: {len(exploration_result.investigation_queries)}")

    # Check that codebase context appears in AI section
    if "src/auth/login_handler.py" in result_with_context.ai_section:
        print("✅ Codebase context included in AI section")

    if "Relevant Files:" in result_with_context.ai_section:
        print("✅ File references formatted correctly")

    if "Code Snippets:" in result_with_context.ai_section:
        print("✅ Code snippets formatted correctly")

except ImportError:
    print("⚠️  Codebase context provider not available - skipping example 2")

# Example 3: Writing output to file
print("\n\n" + "=" * 80)
print("Example 3: Saving Story to File")
print("=" * 80)

output_file = "/tmp/dual_format_story_example.md"
with open(output_file, "w") as f:
    f.write(result.combined)

print(f"✅ Story written to: {output_file}")
print(f"📊 File size: {len(result.combined)} bytes")

# Example 4: Accessing metadata
print("\n\n" + "=" * 80)
print("Example 4: Accessing Story Metadata")
print("=" * 80)

print(f"Format Version: {result.format_version}")
print(f"Generated At: {result.generated_at}")
print(f"Has Codebase Context: {result.codebase_context is not None}")
print(f"Human Section Length: {len(result.human_section)} chars")
print(f"AI Section Length: {len(result.ai_section)} chars")

print("\n" + "=" * 80)
print("✨ All examples completed successfully!")
print("=" * 80)

# Codebase Exploration Task Specification

> **GitHub Issue**: #37 - Dual-Format Story Output with Agent SDK Codebase Context
> **Version**: 1.0
> **Created**: 2026-01-15

This specification defines how Claude Agent SDK explores target codebases to find relevant context for FeedForward themes/stories. The goal is to transform generic story output into actionable engineering tickets with specific file paths, code snippets, and investigation queries.

---

## 1. Task Description

### Purpose

When FeedForward extracts a theme like "login timeout errors", the exploration task enriches it with:

1. **Relevant files** with specific line numbers
2. **Code snippets** showing related logic
3. **Investigation queries** (SQL, API calls) ready to execute

### Input: Theme Data

The exploration receives structured theme data from `ThemeExtractor`:

```json
{
  "issue_signature": "pinterest_oauth_token_refresh_failure",
  "product_area": "account",
  "component": "oauth",
  "user_intent": "Reconnect Pinterest account after token expired",
  "symptoms": [
    "Pinterest reconnection fails",
    "Error message: 'Token refresh failed'",
    "Works after clearing cookies"
  ],
  "affected_flow": "Account Settings -> Pinterest -> Reconnect",
  "root_cause_hypothesis": "OAuth refresh token expired or invalid grant error not handled"
}
```

### Output: Exploration Result

```json
{
  "relevant_files": [
    {
      "path": "src/auth/pinterest_oauth.py",
      "line_start": 145,
      "line_end": 180,
      "relevance": "Contains OAuth token refresh logic with retry handling"
    },
    {
      "path": "src/handlers/account_reconnect.py",
      "line_start": 67,
      "line_end": 92,
      "relevance": "Account reconnection endpoint that calls OAuth refresh"
    }
  ],
  "code_snippets": [
    {
      "file_path": "src/auth/pinterest_oauth.py",
      "line_start": 156,
      "line_end": 168,
      "content": "async def refresh_token(self, refresh_token: str):\n    try:\n        response = await self.client.post(\n            '/oauth/token',\n            data={'grant_type': 'refresh_token', 'refresh_token': refresh_token}\n        )\n        return response.json()\n    except HTTPError as e:\n        # BUG: Does not handle 'invalid_grant' specifically\n        logger.error(f'Token refresh failed: {e}')\n        raise OAuthError('Token refresh failed')",
      "language": "python",
      "context": "Token refresh implementation - missing invalid_grant handling"
    }
  ],
  "investigation_queries": [
    "SELECT user_id, oauth_provider, error_code, created_at FROM oauth_errors WHERE oauth_provider = 'pinterest' AND error_code LIKE '%invalid_grant%' ORDER BY created_at DESC LIMIT 20",
    "SELECT COUNT(*) as error_count, error_code FROM oauth_errors WHERE oauth_provider = 'pinterest' AND created_at > NOW() - INTERVAL '7 days' GROUP BY error_code ORDER BY error_count DESC"
  ],
  "exploration_metadata": {
    "repo": "tailwind/tack",
    "files_searched": 47,
    "patterns_matched": 12,
    "exploration_time_ms": 1250
  }
}
```

---

## 2. Exploration Strategy

### Phase 1: Initial File Discovery

Use Glob patterns to find candidate files based on `product_area` and `component`:

```python
# Step 1a: Component-specific search
files = glob(f"**/*{component}*.*")

# Step 1b: Product area directory search
files += glob(f"**/{product_area}/**/*.*")

# Step 1c: Keyword-based search from symptoms
for symptom_keyword in extract_keywords(symptoms):
    files += glob(f"**/*{symptom_keyword}*.*")
```

### Phase 2: Content Search with Grep

Search file contents for symptom keywords and error messages:

```python
# Step 2a: Search for symptom keywords
for symptom in symptoms:
    matches += grep(pattern=symptom, path=repo_path)

# Step 2b: Search for error message patterns
for error_pattern in extract_error_patterns(symptoms):
    matches += grep(pattern=error_pattern, path=repo_path)

# Step 2c: Search for affected flow keywords
flow_keywords = affected_flow.lower().replace(" -> ", "|").replace(" ", "_")
matches += grep(pattern=flow_keywords, path=repo_path, "-i": True)
```

### Phase 3: File Reading and Snippet Extraction

Read promising files and extract relevant code snippets:

```python
# Step 3a: Score and rank files by relevance
ranked_files = rank_by_relevance(matches, theme)

# Step 3b: Read top N files (typically 5-10)
for file in ranked_files[:10]:
    content = read_file(file.path)

    # Step 3c: Extract relevant snippets with context
    snippets = extract_snippets_around_matches(
        content=content,
        match_lines=file.match_lines,
        context_lines=5  # Lines before/after match
    )
```

### Phase 4: Investigation Query Generation

Generate investigation queries if database/API patterns are detected:

```python
# Step 4a: Detect database table references
tables = detect_table_references(snippets)

# Step 4b: Generate SQL queries for investigation
if tables:
    queries = generate_investigation_queries(
        tables=tables,
        theme=theme,
        time_window="7 days"
    )

# Step 4c: Generate API investigation calls
api_endpoints = detect_api_endpoints(snippets)
if api_endpoints:
    queries += generate_api_test_calls(api_endpoints, theme)
```

---

## 3. Search Patterns by Component

### Component to File Pattern Mapping

| Component     | Primary Patterns                     | Secondary Patterns                 |
| ------------- | ------------------------------------ | ---------------------------------- |
| `oauth`       | `**/auth/**`, `**/*oauth*.*`         | `**/token*.*`, `**/session*.*`     |
| `scheduler`   | `**/scheduler/**`, `**/*schedule*.*` | `**/queue*.*`, `**/job*.*`         |
| `billing`     | `**/billing/**`, `**/payment*/**`    | `**/subscription*.*`, `**/plan*.*` |
| `communities` | `**/tribe*/**`, `**/community*/**`   | `**/group*.*`, `**/member*.*`      |
| `analytics`   | `**/analytics/**`, `**/insight*/**`  | `**/metric*.*`, `**/stat*.*`       |
| `publishing`  | `**/publish*/**`, `**/post*/**`      | `**/queue*.*`, `**/draft*.*`       |
| `ai`          | `**/ghostwriter/**`, `**/ai/**`      | `**/llm*.*`, `**/prompt*.*`        |
| `extension`   | `**/extension/**`, `**/browser/**`   | `**/chrome*.*`, `**/content*.*`    |

### Product Area to Repository Mapping

Based on `docs/tailwind-codebase-map.md`:

| Product Area           | Primary Repository                               | API Domain                                       |
| ---------------------- | ------------------------------------------------ | ------------------------------------------------ |
| `scheduling`           | `tailwind/tack`, `tailwind/aero/packages/bachv2` | `tack.tailwindapp.com`, `bachv3.tailwindapp.com` |
| `pinterest_publishing` | `tailwind/tack`                                  | `tack.tailwindapp.com`                           |
| `instagram_publishing` | `tailwind/zuck`                                  | `zuck.tailwindapp.com`                           |
| `facebook_publishing`  | `tailwind/zuck`                                  | `zuck.tailwindapp.com`                           |
| `ai_creation`          | `tailwind/ghostwriter`                           | Internal                                         |
| `communities`          | `tailwind/aero` (tribes module)                  | `bach.tailwindapp.com/tribes`                    |
| `analytics`            | `tailwind/tack`, `tailwind/aero`                 | Dashboard V3 API                                 |
| `billing`              | `tailwind/swanson`                               | `swanson.tailwindapp.com`                        |
| `account`              | `tailwind/gandalf`                               | `gandalf.tailwindapp.net`                        |
| `integrations`         | `tailwind/charlotte`, `tailwind/scooby`          | `charlotte.tailwindapp.com`                      |

### File Type Priorities by Issue Type

| Issue Type  | Priority File Types                  | Search Depth   |
| ----------- | ------------------------------------ | -------------- |
| Bug/Error   | `*.py`, `*.ts`, `*.js`, `*.sql`      | Full search    |
| Feature Gap | `*.md`, `*.yaml`, `*.json` (configs) | Config-first   |
| Performance | `*.py`, `*.sql`, `*.ts` (queries)    | Query-focused  |
| UI Issue    | `*.tsx`, `*.jsx`, `*.css`            | Frontend-first |

---

## 4. Output Format

### ExplorationResult Schema

```typescript
interface ExplorationResult {
  // Files identified as relevant to the theme
  relevant_files: RelevantFile[];

  // Extracted code snippets with context
  code_snippets: CodeSnippet[];

  // Ready-to-run investigation queries
  investigation_queries: string[];

  // Metadata about the exploration process
  exploration_metadata: ExplorationMetadata;
}

interface RelevantFile {
  path: string; // Relative path within repo
  line_start: number; // First relevant line
  line_end: number; // Last relevant line
  relevance: string; // Why this file is relevant (1-2 sentences)
}

interface CodeSnippet {
  file_path: string; // Path to source file
  line_start: number; // Starting line number
  line_end: number; // Ending line number
  content: string; // Actual code content
  language: string; // Programming language
  context: string; // Why this snippet matters
}

interface ExplorationMetadata {
  repo: string; // Repository explored
  files_searched: number; // Total files examined
  patterns_matched: number; // Pattern matches found
  exploration_time_ms: number; // Time taken
}
```

### Formatting for Human-Facing Output

When rendering for the Engineering Story (human-facing section):

````markdown
### Relevant Files

- `src/auth/pinterest_oauth.py:145-180` - OAuth token refresh logic
- `src/handlers/account_reconnect.py:67-92` - Reconnection endpoint

### Code Snippets

```python
# src/auth/pinterest_oauth.py:156-168
async def refresh_token(self, refresh_token: str):
    try:
        response = await self.client.post(
            '/oauth/token',
            data={'grant_type': 'refresh_token', 'refresh_token': refresh_token}
        )
        return response.json()
    except HTTPError as e:
        # BUG: Does not handle 'invalid_grant' specifically
        logger.error(f'Token refresh failed: {e}')
        raise OAuthError('Token refresh failed')
```
````

### Investigation Queries

```sql
-- Check recent OAuth errors
SELECT user_id, oauth_provider, error_code, created_at
FROM oauth_errors
WHERE oauth_provider = 'pinterest'
  AND error_code LIKE '%invalid_grant%'
ORDER BY created_at DESC LIMIT 20;
```

````

### Formatting for AI Agent Task

When rendering for the AI Coding Agent Task:

```markdown
## Context & Architecture

### Relevant Files:
- `src/auth/pinterest_oauth.py:145-180` - OAuth token refresh logic with retry handling
- `src/handlers/account_reconnect.py:67-92` - Account reconnection endpoint

### Key Code (Reference):
The token refresh implementation at `src/auth/pinterest_oauth.py:156-168` does not handle `invalid_grant` errors specifically - all errors raise generic OAuthError.

### Database Investigation:
Execute this query to understand error patterns:
```sql
SELECT COUNT(*) as error_count, error_code
FROM oauth_errors
WHERE oauth_provider = 'pinterest'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY error_code
ORDER BY error_count DESC
````

````

---

## 5. Security Guardrails

### Approved Repository Allowlist

Only explore repositories in the approved list. Configuration via environment variables:

```python
# Environment configuration (from codebase_security.py)
REPO_BASE_PATH = Path(os.environ.get("FEEDFORWARD_REPOS_PATH", "/Users/paulyokota/repos"))
APPROVED_REPOS = {"aero", "tack", "charlotte", "ghostwriter", "zuck", "gandalf", "swanson", "scooby"}
````

### Validation Functions

Use the security module functions from `src/story_tracking/services/codebase_security.py`:

```python
from story_tracking.services.codebase_security import (
    validate_repo_name,          # Check repo is in allowlist
    validate_path,               # Prevent path traversal
    get_repo_path,               # Get validated repo path
    is_sensitive_file,           # Check if file is sensitive
    redact_secrets,              # Redact secrets from content
    filter_exploration_results,  # Filter sensitive files from results
    validate_git_command_args,   # Validate git command safety
)
```

### Sensitive File Patterns

These patterns are automatically filtered from exploration results:

```python
BLACKLIST_PATTERNS = [
    ".env*",              # Environment files
    "*secrets*",          # Secret files
    "*credentials*",      # Credential files
    "*.pem", "*.key",     # Private keys
    "*.p12", "*.pfx",     # Certificate stores
    "*password*",         # Password files
    "*.keystore", "*.jks", # Java keystores
    "*private*key*",      # Private key files
    ".aws/*", ".ssh/*",   # Cloud/SSH credentials
]
```

### Secret Redaction

Secrets in code snippets are automatically redacted:

```python
# Before redaction
code = 'api_key = "sk-1234567890abcdef"'

# After redaction (via redact_secrets())
code = 'api_key = "[REDACTED]"'

# Patterns matched:
# - api_key, api-key
# - password
# - token, auth_token, auth-token
# - secret
# - access_key, access-key
# - private_key, private-key
```

### Security Validation Flow

```
1. validate_repo_name(repo) -> Ensure repo is in allowlist
2. validate_path(file_path) -> Prevent path traversal
3. filter_exploration_results(files) -> Remove sensitive files
4. redact_secrets(content) -> Redact any leaked secrets
5. Return sanitized results
```

### Audit Logging

All security validations are logged for audit purposes:

```python
# Logs generated by security module
logger.warning(f"Repo validation failed: '{repo_name}' not in approved list")
logger.warning(f"Path validation failed: '{path}' not within base path")
logger.info(f"Sensitive file detected: '{filepath}' matches pattern '{pattern}'")
logger.info(f"Redacting {count} potential secret(s) from content")
```

---

## 6. Example Prompts

### Example 1: Bug - "Login timeout errors"

**Theme Input:**

```json
{
  "issue_signature": "pinterest_login_timeout_error",
  "product_area": "account",
  "component": "oauth",
  "user_intent": "Log into Pinterest account through Tailwind",
  "symptoms": [
    "Login page hangs for 30+ seconds",
    "Error: 'Connection timeout'",
    "Happens intermittently"
  ],
  "affected_flow": "Login -> Pinterest OAuth -> Callback",
  "root_cause_hypothesis": "OAuth callback timeout not handled gracefully"
}
```

**Exploration Prompt:**

```
You are exploring the Tailwind codebase to find code relevant to this customer issue.

Theme: pinterest_login_timeout_error
Product Area: account
Component: oauth
Symptoms: Login page hangs 30+ seconds, Connection timeout error, Intermittent

EXPLORATION TASKS:
1. Search for files matching: **/auth/**, **/*oauth*.*, **/*login*.*
2. Grep for patterns: "timeout", "connection", "oauth.*callback", "pinterest.*auth"
3. Read matching files, extract snippets around timeout/error handling
4. Generate SQL queries if oauth_sessions or login_attempts tables found

OUTPUT FORMAT: Return ExplorationResult JSON with relevant_files, code_snippets, and investigation_queries.

SECURITY: Only explore approved repos. Filter sensitive files. Redact any secrets found.
```

### Example 2: Feature Gap - "Missing bulk export functionality"

**Theme Input:**

```json
{
  "issue_signature": "analytics_bulk_export_missing",
  "product_area": "analytics",
  "component": "export",
  "user_intent": "Export all analytics data as CSV for external reporting",
  "symptoms": [
    "No bulk export option visible",
    "Can only export one report at a time",
    "Requesting multi-board export"
  ],
  "affected_flow": "Insights -> Export -> (missing bulk option)",
  "root_cause_hypothesis": "Feature not implemented - export is single-report only"
}
```

**Exploration Prompt:**

```
You are exploring the Tailwind codebase to understand the current export implementation.

Theme: analytics_bulk_export_missing
Product Area: analytics
Component: export
User Need: Bulk CSV export of analytics across multiple boards

EXPLORATION TASKS:
1. Search for files matching: **/analytics/**, **/*export*.*, **/*report*.*
2. Grep for patterns: "export", "csv", "download", "analytics.*report"
3. Read export-related files, understand current single-report flow
4. Identify extension points for bulk export feature

OUTPUT FORMAT: Return ExplorationResult JSON with current implementation files and suggested extension points.

SECURITY: Only explore approved repos. Filter sensitive files. Redact any secrets found.
```

### Example 3: Performance - "Slow dashboard loading"

**Theme Input:**

```json
{
  "issue_signature": "dashboard_slow_load_performance",
  "product_area": "analytics",
  "component": "dashboard",
  "user_intent": "View Pinterest analytics dashboard quickly",
  "symptoms": [
    "Dashboard takes 15+ seconds to load",
    "Spinning loader for extended time",
    "Faster on other accounts"
  ],
  "affected_flow": "Dashboard -> Load Analytics -> Render Charts",
  "root_cause_hypothesis": "N+1 query issue or missing database index for large accounts"
}
```

**Exploration Prompt:**

```
You are exploring the Tailwind codebase to find performance bottlenecks.

Theme: dashboard_slow_load_performance
Product Area: analytics
Component: dashboard
Symptoms: 15+ second load time, prolonged spinner, varies by account size

EXPLORATION TASKS:
1. Search for files matching: **/dashboard/**, **/*analytics*.*, **/*query*.*
2. Grep for patterns: "SELECT", "JOIN", "analytics", "dashboard.*load"
3. Read database query files, identify potential N+1 patterns
4. Generate EXPLAIN queries for suspicious SQL

OUTPUT FORMAT: Return ExplorationResult JSON with query files, potential N+1 patterns, and EXPLAIN queries.

SECURITY: Only explore approved repos. Filter sensitive files. Redact any secrets found.
```

---

## 7. Integration with FeedForward Pipeline

### Where Exploration Fits

```
Theme Extraction (existing)
         |
         v
Codebase Exploration (NEW) <-- This specification
         |
         v
Dual-Format Story Generation
         |
         v
Story Creation in Shortcut
```

### Exploration Trigger Points

1. **New Theme Detected**: When `ThemeExtractor.extract()` creates a new theme
2. **Story Promotion**: When an orphan theme reaches MIN_GROUP_SIZE (3) and becomes a story
3. **Manual Enrichment**: When PM requests additional context for existing story

### Configuration

```yaml
# config/exploration.yaml
exploration:
  enabled: true
  max_files_per_search: 50
  max_snippets_per_file: 3
  context_lines: 5
  exploration_timeout_ms: 30000

  repos:
    base_path: "${FEEDFORWARD_REPOS_PATH}"
    approved: ["aero", "tack", "charlotte", "ghostwriter", "zuck"]

  security:
    filter_sensitive: true
    redact_secrets: true
    audit_log: true
```

### API Design (Future)

```python
# Proposed exploration service interface
class CodebaseExplorer:
    async def explore(
        self,
        theme: Theme,
        repo: str,
        max_files: int = 50,
    ) -> ExplorationResult:
        """
        Explore codebase for context relevant to theme.

        Args:
            theme: Extracted theme with symptoms and hypothesis
            repo: Repository to explore (must be in approved list)
            max_files: Maximum files to examine

        Returns:
            ExplorationResult with files, snippets, and queries

        Raises:
            ValueError: If repo not in approved list
            SecurityError: If path traversal detected
        """
        pass
```

---

## 8. Acceptance Criteria

### Exploration Quality

- [ ] Exploration returns 3-10 relevant files per theme (not 0, not 100+)
- [ ] Code snippets include 5 lines of context before/after key code
- [ ] Investigation queries are syntactically valid SQL
- [ ] File paths are relative to repo root, not absolute

### Security Requirements

- [ ] Only approved repos can be explored
- [ ] Sensitive files (`.env`, credentials) are filtered
- [ ] Secrets in code snippets are redacted
- [ ] Path traversal attacks (`../../../`) are blocked
- [ ] All security validations are logged

### Performance Requirements

- [ ] Exploration completes in < 30 seconds for typical theme
- [ ] Uses streaming/pagination for large repos
- [ ] Caches file listings between explorations

### Output Quality

- [ ] Relevant files include meaningful relevance descriptions
- [ ] Code snippets are syntactically complete (not mid-function cuts)
- [ ] Investigation queries target correct tables based on snippets

---

## 9. References

- **GitHub Issue**: #37 - Dual-Format Story Output with Agent SDK Codebase Context
- **Security Module**: `src/story_tracking/services/codebase_security.py`
- **Codebase Map**: `docs/tailwind-codebase-map.md`
- **Story Templates**: `docs/story_knowledge_base.md` (Section 5.2 - AI Coding Agent Task Template)
- **Example Output**: `docs/examples/dual-format-story-example.md`
- **Theme Extractor**: `src/theme_extractor.py`

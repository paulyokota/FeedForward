# Browser Capabilities Investigation

**Date:** 2026-02-01
**Branch:** `claude/investigate-browser-capabilities-51Kr9`

## Summary

Investigation of Claude Code's browser capabilities within the FeedForward project context. Documents available tools, their use cases, and integration patterns.

## Claude Code Built-in Browser Tools

### 1. WebFetch

**Purpose:** Fetch and analyze web content via AI model processing

**Capabilities:**
- Fetches URL content and converts HTML to markdown
- Processes content with an AI prompt
- 15-minute caching for repeated requests
- Automatic HTTPS upgrade

**Limitations:**
- Read-only (cannot interact with pages)
- No JavaScript execution
- Cannot handle authentication/sessions
- May follow redirects but requires manual re-fetch

**Use Case:** Extracting information from public web pages, documentation lookup

### 2. WebSearch

**Purpose:** Search the web for information

**Capabilities:**
- Returns search results with links
- Domain filtering (allow/block specific sites)
- Up-to-date information beyond knowledge cutoff

**Limitations:**
- US availability only
- Search results only, not full content
- Requires follow-up WebFetch for content extraction

**Use Case:** Finding documentation, researching APIs, current events

## Playwright Integration (Project-Specific)

### Custom Scripts

Located in `scripts/ralph/`:

| Script | Purpose |
|--------|---------|
| `validate_playwright.py` | Validates GitHub repos exist and contain relevant files |
| `init_playwright_session.py` | Creates authenticated browser sessions for reuse |

**Features:**
- Full browser automation (Chromium)
- Interactive mode for login/2FA
- Session persistence via storage state
- GitHub private repo access (with authentication)

**Execution:** Manual via `python3 scripts/ralph/validate_playwright.py`

### MCP Playwright (Developer-Kit Plugin)

Referenced in `docs/testing/playwright-dnd-visual-testing.md`:

```
mcp__plugin_developer-kit_playwright__browser_run_code
```

**Capabilities (when available):**
- Execute arbitrary Playwright code
- Mouse/keyboard control
- Screenshot capture
- Wait for selectors/animations

**Current Status:**
- No `.mcp.json` configuration file exists in project
- Availability depends on environment configuration
- Not verified as available in current session

## Capability Comparison Matrix

| Capability | WebFetch | WebSearch | Playwright Scripts | MCP Playwright |
|------------|----------|-----------|-------------------|----------------|
| Fetch web content | Yes | No | Yes | Yes |
| Search the web | No | Yes | No | No |
| JavaScript execution | No | N/A | Yes | Yes |
| Authentication support | No | N/A | Yes | Yes |
| Interactive elements | No | N/A | Yes | Yes |
| Screenshots | No | N/A | Yes | Yes |
| Session persistence | No | N/A | Yes | Yes |
| Direct Claude integration | Yes | Yes | No (Bash) | Yes |

## Recommended Usage Patterns

### Public Content Retrieval
```
Tool: WebFetch
Pattern: Direct fetch with extraction prompt
Example: Documentation lookup, public API docs
```

### Research/Discovery
```
Tool: WebSearch → WebFetch
Pattern: Search first, then fetch relevant results
Example: Finding solutions to errors, library options
```

### Private Repository Validation
```
Tool: Playwright Scripts via Bash
Pattern: Initialize session, run validation script
Example: GitHub private repo verification in Ralph pipeline
```

### Visual/Interactive Testing (if MCP available)
```
Tool: MCP Playwright
Pattern: Run Playwright code for DOM interaction
Example: Drag-and-drop testing, screenshot capture
```

## Project Integration Points

1. **Ralph Pipeline** (`scripts/ralph/`)
   - Uses Playwright for GitHub repo validation
   - Validates technical areas map to real code locations

2. **Tailwind Codebase Map** (`docs/tailwind-codebase-map.md`)
   - URL mappings verified via Playwright browser automation

3. **Frontend Visual Testing** (`docs/testing/playwright-dnd-visual-testing.md`)
   - Drag-and-drop visual QA via MCP Playwright

## GitHub Operations

### Environment Status

| Tool | Available | Notes |
|------|-----------|-------|
| `gh` CLI | **No** | Not installed in this environment |
| `git` commands | **Yes** | Full git access (push, pull, branch, etc.) |
| `curl` | **Yes** | Can call GitHub API directly |
| GitHub API via WebFetch | **Yes** | Read-only for public repos |

### Capability Matrix

| Operation | Method | Auth Required | Available |
|-----------|--------|---------------|-----------|
| **Read issues** | WebFetch + GitHub API | No (public repos) | Yes |
| **Create issues** | curl + GitHub API | Yes (token) | No token available |
| **Post comments** | curl + GitHub API | Yes (token) | No token available |
| **Read PRs** | WebFetch + GitHub API | No (public repos) | Yes |
| **Create PRs** | curl + GitHub API | Yes (token) | No token available |
| **Close PRs/issues** | curl + GitHub API | Yes (token) | No token available |
| **Create branches** | `git checkout -b` + `git push` | Git credentials | Yes |
| **Delete branches** | `git push origin --delete` | Git credentials | Yes |

### What Works Now

**Reading (Public Repos):**
```bash
# Via WebFetch
WebFetch https://api.github.com/repos/OWNER/REPO/issues

# Via curl
curl https://api.github.com/repos/OWNER/REPO/issues
```

**Branch Operations:**
```bash
# Create branch
git checkout -b feature/my-branch
git push -u origin feature/my-branch

# Delete branch
git push origin --delete feature/my-branch
```

### What Requires GitHub Token

Operations that modify GitHub state (not git state) require authentication:

```bash
# Would need GITHUB_TOKEN environment variable
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/OWNER/REPO/issues \
  -d '{"title":"Issue title","body":"Issue body"}'
```

**Missing:** No `GITHUB_TOKEN` or `GH_TOKEN` available in this environment.

### CLAUDE.md Discrepancy

The project's `CLAUDE.md` references `gh` commands:
```markdown
- Use `gh issue list` to view open issues
- Use `gh issue create` to create new issues
```

However, **`gh` CLI is not available** in the current environment. This should be addressed by either:
1. Installing `gh` CLI in the environment
2. Updating CLAUDE.md to reflect actual capabilities
3. Providing a GitHub token for API access

## Gaps and Recommendations

### Current Gaps

1. **No MCP configuration** - `.mcp.json` not present, limiting MCP tool access
2. **Authentication complexity** - Playwright scripts require interactive login
3. **No headless CI integration** - Current setup assumes interactive mode
4. **No `gh` CLI** - Referenced in CLAUDE.md but not available
5. **No GitHub token** - Cannot create/modify issues, PRs, or comments via API

### Recommendations

1. **For simple web lookups:** Use WebFetch (already available)
2. **For reading GitHub data:** Use WebFetch + GitHub API (works for public repos)
3. **For branch operations:** Use git commands directly (works)
4. **For GitHub write operations:** Request GitHub token or `gh` CLI installation
5. **For visual testing:** Consider adding MCP Playwright configuration if needed
6. **For authenticated web tasks:** Use Playwright scripts with session persistence

## Files Referenced

- `docs/testing/playwright-dnd-visual-testing.md` - MCP Playwright guide
- `scripts/ralph/validate_playwright.py` - GitHub validation script
- `scripts/ralph/init_playwright_session.py` - Session initialization
- `.claude/settings.json` - Project Claude settings (no MCP config)

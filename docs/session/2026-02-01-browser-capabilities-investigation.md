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

## Gaps and Recommendations

### Current Gaps

1. **No MCP configuration** - `.mcp.json` not present, limiting MCP tool access
2. **Authentication complexity** - Playwright scripts require interactive login
3. **No headless CI integration** - Current setup assumes interactive mode

### Recommendations

1. **For simple web lookups:** Use WebFetch (already available)
2. **For GitHub operations:** Use `gh` CLI instead of browser automation when possible
3. **For visual testing:** Consider adding MCP Playwright configuration if needed
4. **For authenticated web tasks:** Use Playwright scripts with session persistence

## Files Referenced

- `docs/testing/playwright-dnd-visual-testing.md` - MCP Playwright guide
- `scripts/ralph/validate_playwright.py` - GitHub validation script
- `scripts/ralph/init_playwright_session.py` - Session initialization
- `.claude/settings.json` - Project Claude settings (no MCP config)

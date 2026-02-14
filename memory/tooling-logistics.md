# Tooling Logistics

How to access each data source. Recipes that have been tested and work.

## Environment Variables

All tokens live in `/Users/paulyokota/Documents/GitHub/FeedForward/.env`.
Python scripts (intercom-sync, intercom-search, cli.py) load it via `dotenv`
automatically.

**For shell/curl commands**, use the `grep` approach (most reliable):

```bash
SHORTCUT_API_TOKEN=$(grep '^SHORTCUT_API_TOKEN=' /Users/paulyokota/Documents/GitHub/FeedForward/.env | cut -d= -f2)
```

`source .env` works sometimes but intermittently fails to pass tokens to curl
(produces "organization context missing" errors). The `grep` approach is
deterministic. Use it for all Shortcut API calls.

**Shell vs Python subprocess:** Shell variables aren't inherited by child
processes (like `python3 -c "..."`). For inline Python that needs tokens, use
`export`:

```bash
export SHORTCUT_API_TOKEN=$(grep '^SHORTCUT_API_TOKEN=' .env | cut -d= -f2)
```

Python scripts that use `dotenv` (intercom-search, intercom-sync, cli.py)
handle this themselves.

Key variables:

- `SHORTCUT_API_TOKEN` — Shortcut REST API
- `INTERCOM_ACCESS_TOKEN` — Intercom API (also used by MCP)
- `INTERCOM_APP_ID` — `2t3d8az2`
- `DATABASE_URL` — `postgresql://localhost:5432/feedforward`
- `OPENAI_API_KEY` — used for embeddings in classification pipeline

## Shortcut API

Base URL: `https://api.app.shortcut.com/api/v3`

Auth header: `Shortcut-Token: $SHORTCUT_API_TOKEN`

### Load token (do this first, every time)

```bash
SHORTCUT_API_TOKEN=$(grep '^SHORTCUT_API_TOKEN=' /Users/paulyokota/Documents/GitHub/FeedForward/.env | cut -d= -f2)
```

### Fetch a story by ID

```bash
curl -s -H "Content-Type: application/json" \
  -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
  "https://api.app.shortcut.com/api/v3/stories/{ID}"
```

### Search stories

```bash
curl -s -H "Content-Type: application/json" \
  -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
  "https://api.app.shortcut.com/api/v3/search/stories?query=state:%22Ready+to+Build%22&page_size=25"
```

Search is GET, not POST. See `box/shortcut-ops.md` for search operators.

### Update a story (fill-cards pattern)

For card updates with markdown descriptions, **always write the payload to a
temp file** and use `curl -d @file`. Inline `python3 -c json.dumps(...)` breaks
on long descriptions with nested quotes and markdown.

```bash
# Step 1: Build payload in Python, write to temp file
python3 -c "
import json
payload = {
    'description': '''Your full markdown description here...''',
    'workflow_state_id': 500000019,   # Ready to Build
    'owner_ids': [],                   # Unassign all owners
    'custom_fields': [{
        'field_id': '69812486-120c-4e45-a64e-2662ab423eea',
        'value_id': '698b5277-edf5-424f-84f3-89dc57c3115c'  # e.g. TURBO
    }]
}
with open('/tmp/ff-YYYYMMDD/sc_payload.json', 'w') as f:
    json.dump(payload, f)
"

# Step 2: Push with curl
curl -s -X PUT -H "Content-Type: application/json" \
  -H "Shortcut-Token: $SHORTCUT_API_TOKEN" \
  -d @/tmp/ff-YYYYMMDD/sc_payload.json \
  "https://api.app.shortcut.com/api/v3/stories/{ID}"
```

**Gotchas that have bitten us:**

- `custom_fields` uses `value_id`, NOT `value`. Using `value` returns
  `{"errors":{"custom_fields":[{"value_id":"missing-required-key"}]}}`.
- Fill-cards play is three operations in one PUT: update description + change
  state to Ready to Build (500000019) + unassign owners (`owner_ids: []`).
  Don't forget the state change.
- Always set Product Area (`custom_fields`) in the same PUT. We've shipped
  cards without it and had to go back.
- **Don't write inline Python via Bash.** Bash `!` history expansion breaks
  `!=` inside double quotes, `$` interpolation eats Python variables, and
  quoting gets unmanageable. Write a temp `.py` file and run it instead.

### Workspace constants

See `box/shortcut-ops.md` for workflow state IDs, product area IDs, and member IDs.

## PostgreSQL (FeedForward DB)

Connection: `postgresql://localhost:5432/feedforward`

### Direct SQL

```bash
psql postgresql://localhost:5432/feedforward -c "SELECT COUNT(*) FROM conversations"
```

### Python scripts (auto-load .env via dotenv)

```bash
python3 box/intercom-search.py "RSS feed"                  # Full-text search
python3 box/intercom-search.py "pins disappeared" --since 90
python3 box/intercom-search.py --count "smartpin"
python3 box/intercom-sync.py --status                      # Check sync state
```

### Useful queries

See `box/queries.md` for saved SQL patterns.

### Key tables

- `conversations` — imported Intercom conversations with classification
- `conversation_search_index` — full-text search across complete threads (issue #284)
- `conversation_sync_state` — tracks sync progress
- `themes` — classified themes (good for volume, bad for discovery)

## Intercom API

### Via MCP

The Intercom MCP server is configured in `.mcp.json`. Use for conversation
lookups, contact searches, etc.

### Via Python

```bash
python3 box/intercom-search.py "query"  # Best for full-thread search
```

The search index includes all conversation parts (replies), not just opening
messages. This is the main advantage over the Intercom API's `source.body`
search which only hits opening messages.

### Via curl

```bash
INTERCOM_ACCESS_TOKEN=$(grep '^INTERCOM_ACCESS_TOKEN=' /Users/paulyokota/Documents/GitHub/FeedForward/.env | cut -d= -f2)
curl -s -H "Authorization: Bearer $INTERCOM_ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "https://api.intercom.io/conversations/search" \
  -d '{"query": {"field": "source.body", "operator": "~", "value": "RSS"}}'
```

Remember: `source.body` only searches the opening message. Feature-request
phrasing ("would love to", "is there a way to") returns 0 results. Use
topic-keyword nouns instead.

## PostHog

Access via PostHog MCP server. Check `box/posthog-events.md` for known event
names before searching.

### Common patterns

- **Ad-hoc queries: use `query-run`**, not `insight-query`. `insight-query`
  requires an existing `insightId`. `query-run` accepts inline query definitions.
- Person properties: `properties.subscriptionState`, `properties['$geoip_country_code']`
- Cross-reference with Intercom: get email from Intercom, query PostHog events
  filtered by `person.properties.email IN (...)`

## Target Codebase (aero)

Path: `/Users/paulyokota/Documents/GitHub/aero/`

### Key locations

- `packages/core/src/` — business logic (turbo, billing, etc.)
- `packages/database/lib/schemas/postgres/` — Drizzle ORM schema definitions
- `packages/tailwindapp/` — Next.js frontend
- `packages/jarvis/` — admin/backend service
- `packages/tailwindapp-legacy/` — PHP legacy app

### Reading minified JS

`Read` tool can't handle single-line megafiles. Use Python regex extraction:

```bash
python3 -c "
import re
text = open('path/to/file.js').read()
for m in re.finditer(r'.{0,200}KEYWORD.{0,200}', text):
    print(m.group())
"
```

## Session Management

- Session notes: `box/session.md`
- Investigation log: `box/log.md`
- NOT `docs/session/last-session.md` (overwritten by Developer Kit Stop hook)

### Session temp directory

Use `/tmp/ff-YYYYMMDD/` for all session artifacts (payloads, intermediate
data, exports). Create at start, clean up at end:

```bash
mkdir -p /tmp/ff-$(date +%Y%m%d)    # Session start
rm -rf /tmp/ff-$(date +%Y%m%d)      # Session end (or /session-end does it)
```

All temp file paths in recipes below (e.g. `/tmp/ff-YYYYMMDD/sc_payload.json`) should
use this directory instead: `/tmp/ff-YYYYMMDD/sc_payload.json`.

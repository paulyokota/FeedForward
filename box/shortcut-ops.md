# Shortcut Operations Reference

Reference for Shortcut workspace maintenance tasks. Not a procedure — context
and constraints for working with the Tailwind Shortcut workspace.

Originated from the assist-bot project (Phase 0 observations, Feb 2026). The
detailed procedural skills that generated this knowledge are archived at
`/Users/paulyokota/Documents/GitHub/assist-bot/.claude/skills/`.

## Workspace Constants

### IDs

| Thing                     | ID                                     |
| ------------------------- | -------------------------------------- |
| Workspace slug            | `tailwnd`                              |
| Tailwind team (group)     | `69812486-e192-4bed-888a-c5ef9c19d174` |
| Paul's member ID          | `698124a4-138b-4743-abd6-ec12c64d9262` |
| Workflow ID               | `500000018`                            |
| Product Area custom field | `69812486-120c-4e45-a64e-2662ab423eea` |

### Workflow States

| State             | ID          |
| ----------------- | ----------- |
| In Definition     | `500000022` |
| Need Requirements | `500000024` |
| Ready to Build    | `500000019` |
| Build             | `500000020` |
| Test              | `500000023` |
| Released          | `500000021` |

### Product Areas

| Area             | Value ID                               |
| ---------------- | -------------------------------------- |
| SMARTPIN         | `698b5277-bc75-43cd-a37d-3d47d7496a5f` |
| PIN SCHEDULER    | `698b5277-ba29-43fd-be4a-76f7a0167751` |
| TURBO            | `698b5277-edf5-424f-84f3-89dc57c3115c` |
| KEYWORD RESEARCH | `698b5277-41ef-4f4c-bb67-3c83c60513ec` |
| EXTENSION        | `698b5277-a45a-480a-9940-5e1e9700a011` |
| CREDITS          | `698b5277-da44-47a7-b475-392a590a8d5d` |
| META             | `698b5277-da81-480d-a650-3eaf6131229e` |
| NAV              | `698b5277-d354-4cb1-893b-1cb71a5bf9a3` |
| BILLING          | `698b5277-fa07-4751-8ac6-b6d86f2ca2de` |
| API/MCP          | `698b5277-43c1-411a-9b32-d39bcfd1c2cc` |
| M4U              | `698e9253-c138-4e96-9dd3-7c732aff37fd` |
| GHOSTWRITER      | `698fb17d-1494-418b-ab46-aee08fe9bfff` |

### Slack

| Thing                | Value                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------- |
| #ideas channel ID    | `C0ADJ4ATJE4`                                                                          |
| Bot scopes confirmed | `channels:read`, `channels:history`, `reactions:read`, `reactions:write`, `chat:write` |
| Bot scope missing    | `users:read` (can't resolve Slack user IDs to names)                                   |

## API Quirks

- **Search is GET, not POST.** `GET /api/v3/search/stories?query=...&page_size=25` works. `POST /api/v3/search/stories` returns 404. Includes full descriptions. Supports search operators. Follow `next` URL for pagination. Max 250 per page, 1000 total results. `detail=slim` omits descriptions/comments (faster for title-only matching).
- **Group stories endpoint** (`/groups/{id}/stories`) does NOT include `description`. Must fetch individual stories via `GET /stories/{id}` for full content. Prefer the search endpoint when you need descriptions.
- **JSON payloads**: Always construct with Python `json.dumps()`. Bash string interpolation breaks on quotes, newlines, and markdown in descriptions.
- **Slack `conversations.replies`**: Always pass the parent message `ts`, not a reply's `ts`. Passing a reply's `ts` returns only that one message (no error, no parent, no siblings). This would silently break idempotency checks for existing bot replies.
- **Slack `already_reacted`**: Treat as success, not error.
- **Slack `Retry-After`**: Sleep the specified duration, then retry.
- **Story link conflicts**: "Cannot create a duplicate story link" means it already exists — treat as success.
- **Pagination**: Shortcut search returns 25 per page. Slack history returns up to 200 with cursor-based pagination. Always check for `has_more` / `next`.
- **Intercom `source.body` search only searches the first message.** Admin replies, internal notes, and Intercom app cards (e.g., "Jam for Customer Support") are NOT searchable via the conversations search API. To find conversations where a CS agent used a specific tool or mentioned something in a reply, you need the conversation ID from another source (Slack thread, CS person, etc.) and fetch it directly via `GET /conversations/{id}`.
- **Intercom conversation fetch concurrency.** The default `INTERCOM_FETCH_CONCURRENCY=10` in `intercom-sync.py` is extremely conservative. At concurrency 10, throughput was ~1.1 conv/sec (64 req/min). At concurrency 80, throughput jumped to ~100 conv/sec (~6000 req/min) with zero 429 errors. The bottleneck at low concurrency is network latency per request, not rate limits. The script's hardcoded cap is 100 (`min(100, ...)`); for bulk syncs, 80 is a good default.
- **Intercom API requires `Accept: application/json` header.** Without it, `urllib.request` gets HTTP 406 Not Acceptable. `curl` sends `Accept: */*` by default so it works without, but Python's `urllib` does not. Always include it in programmatic calls.
- **Intercom conversation parts have different `part_type` values.** Only `comment` contains the main conversation messages. `assignment` contains CS agent handoff messages (often substantive — Mike's Jam offers, troubleshooting replies). `note` contains internal notes and app card results (Jam upload confirmations, recording URLs). `open` contains reopen messages. Everything else (`snoozed`, `close`, `timer_unsnooze`, `fin_guidance_applied`, `default_assignment`, `conversation_attribute_updated_by_admin`, `company_updated`, `channel_and_reply_time_expectation`) has no useful body text.
- **Search index covers 5 part types.** `build_full_conversation_text()` in `digest_extractor.py` indexes `comment`, `assignment`, `close`, `open`, and `note` parts. Internal notes starting with "Insight has been recorded" (Intercom Insight boilerplate) are filtered. Other part types have no useful body text and are excluded.
- **FeedForward `.env` sourcing.** `source .env` alone doesn't export variables for Python subprocesses. Use `export $(grep -E '^(VAR1|VAR2)' .env | xargs)` to make specific vars available, or run scripts that load `.env` themselves (like `intercom-sync.py` which uses `python-dotenv`).

## Search Operators (useful subset)

Full reference: [Shortcut help center article on search operators](https://help.shortcut.com/hc/en-us/articles/360000046646)

| Operator            | Example                                  | Notes                                        |
| ------------------- | ---------------------------------------- | -------------------------------------------- |
| `state:`            | `state:"In Definition"`                  | Quote multi-word states                      |
| `!state:`           | `!state:Released`                        | Exclusion with `!` or `-` prefix             |
| `is:archived`       | `!is:archived`                           | Filter archived stories                      |
| `type:`             | `type:bug`, `type:feature`, `type:chore` | Story type filter                            |
| `owner:`            | `owner:paulyokota`                       | Uses mention name, no `@`                    |
| `team:`             | `team:Tailwind`                          | Team name, not ID                            |
| `product-area:`     | `product-area:SMARTPIN`                  | Shortcut-defined custom field                |
| `title:`            | `title:"smart pin"`                      | Search within titles only                    |
| `description:`      | `description:shipped`                    | Search within descriptions only              |
| `has:external-link` | `!has:external-link`                     | Stories with/without external links          |
| `has:comment`       | `has:comment`                            | Stories with comments                        |
| `has:deadline`      | `!has:deadline`                          | Stories with/without due dates               |
| `created:`          | `created:2026-01-01..*`                  | Date range with `..`, use `*` for open-ended |
| `updated:`          | `updated:today`                          | Also supports `yesterday`                    |
| `is:overdue`        | `is:overdue`                             | Due date in the past                         |

Operators combine with AND logic. No OR support. Invert any operator with `!` or `-` prefix.

**Useful compound queries:**

- All active stories: `!is:archived !state:Released`
- Paul's Need Requirements cards: `owner:paulyokota state:"Need Requirements"`
- Bugs in SmartPin: `type:bug product-area:SMARTPIN`
- Old unfilled cards: `state:"In Definition" created:*..2026-01-01`
- Stories without Slack links: `!has:external-link !is:archived`

## Story Template

New Shortcut cards use this description template:

```
[Link to original idea in Slack](PERMALINK)

## "What"
-

## Evidence
-

## Architecture Context
-

## UI Representation (Wireframes, descriptions of visuals, etc.)
-

## Monetization Angle
-

## Reporting Needs/Measurement Plan
-

## Release Strategy
-
```

### Section expectations

Most cards today are bare-bones — a one-liner "What" and dashes everywhere else.
The goal is to make each section substantive:

- **"What"**: Clear description of what we're building and why. What changes from
  the user's perspective, what is true when this is done. Should stand on its own
  as a scope definition without implementation detail. Not a solution sketch or
  implementation plan. Not just a verbatim Slack quote.
- **Evidence**: Data points, customer quotes, support ticket counts, usage metrics
  — anything that demonstrates demand or validates the need. Verbatim quotes are
  strongest. Include Intercom conversation IDs for traceability.
- **Architecture Context**: Orientation for the developer picking this up. What
  exists today, what doesn't exist, dead ends to avoid, key constraints. The goal
  is to save the developer from re-discovering the landscape, not to prescribe how
  to build the solution. For feature/chore cards: describe the current state of the
  relevant system area (files, data model, integrations) without specifying
  implementation steps. For bug cards: more prescriptive detail is appropriate since
  the fix path is typically deterministic (root cause location, failure mechanism,
  specific code paths involved). Separate from UI Representation (architecture is
  backend/system, UI is what the user sees).
- **UI Representation**: Written descriptions of what the user sees and interacts
  with. Reference existing component files. Describe current state and proposed
  changes per screen. Avoid "Create flow" phrasing (conflicts with Tailwind Create
  product). Use "New [X] form", "Edit form", "Dashboard", etc.
- **Monetization Angle**: How this connects to revenue. Keep tight: only points
  that add real insight. Credit consumption patterns and acquisition/retention
  levers are most useful. Skip speculative tier-gating unless it's a clear call.
- **Reporting Needs/Measurement Plan**: What to measure to know if this worked.
  Events to track, success criteria, dashboards.
- **Release Strategy**: Rollout scope (all users, beta, feature flag), announcement
  plan (email, marketing, SEO), support enablement (help docs, canned responses).
  This is NOT implementation steps; those belong in Architecture Context.

Bug cards use a leaner template: only include sections with actual content. Skip
blank Monetization, UI, Reporting, Release sections.

When creating cards from investigations, populate sections with findings rather
than leaving them empty. The fill-cards play is for fleshing out what's missing.

## Card Quality Gate

Check before presenting a card for approval. Every criterion must pass. If one
doesn't, revise the card.

1. **Problem before solution**: Is the problem stated independently from any
   implementation ideas? Would the card still make sense as a problem statement
   with the Architecture Context removed?
2. **Scoping-ready**: Does the card describe the feature behavior and current system
   state clearly enough that a developer with codebase access could estimate the
   work? Architecture Context should orient, not prescribe.
3. **Verifiable evidence**: Is every factual claim linked to a source? Intercom
   conversation URLs, PostHog saved insight links, specific file paths. No
   unanchored assertions.
4. **Observable done state**: Could someone write a test, check a dashboard, or
   perform a user action to verify this card is complete? Is "done" concrete,
   not vague?

## Plays

### 1. Sync Ideas (Slack #ideas → Shortcut)

**What it does**: Match ideas posted in Slack #ideas to Shortcut stories. Create
cards for unmatched ideas, add link-back lines to story descriptions, add
`:shortcut:` reactions to Slack messages, post thread replies with story links.
For ideas that match Released stories, post a "This shipped!" thread reply with
the story link so the original poster knows it landed.

**Key behaviors**:

- Default data window: last 90 days of Slack messages
- Each top-level Slack message = one idea (threads may contain sub-ideas)
- Matching is semantic — compare idea text against story titles and descriptions
- Likely matches need Paul's confirmation one at a time
- New cards go to "In Definition" state, owned by Paul, no team assignment
- Infer Product Area from idea text using keyword matching (see Product Area Keywords below)
- All In Definition stories should be assigned to Paul
- Match against Released stories too: if an idea matches something already shipped,
  post a "This shipped!" thread reply with the story link instead of creating a card
- Slack messages may contain quoted/attached content (shared from private conversations
  or other channels). Always check `attachments` and `blocks` for the real idea text,
  not just the top-level `text` field
- Bug cards use a leaner template: only include sections with actual content (skip
  blank Monetization, UI, Reporting, Release sections)
- Set `story_type` when creating cards: `bug` for bug reports, `feature` for ideas
  (default). Enables `type:bug` search operator for filtering.
- Set `external_links` to the Slack permalink URL when creating cards. This enables
  `has:external-link` search filtering. The markdown link stays in the description
  too (visible when reading the card). Both serve different purposes.

**Idempotency**:

- Check for existing `:shortcut:` reaction before adding
- Check thread for existing bot reply with same Shortcut URL before posting
- Check thread for existing "shipped" reply before posting a duplicate
- Check story description for existing link line before prepending
- `already_reacted` from Slack = success

**Slack thread reply formats**:

- **Tracked reply** (new idea matched or created):
  `Tracked: <shortcut_url|SC-NNN: Story title>`
- **Shipped reply** (idea matches a Released story):
  `This shipped! <shortcut_url|SC-NNN: Story title>`

**Correct state per card**:

- Released stories should have TWO bot replies: a Tracked reply AND a
  This shipped! reply, with Tracked posted first (earlier timestamp)
- All other states should have ONE bot reply: a Tracked reply only
- A single Slack thread may carry replies for multiple cards

No automated audit script currently. Thread state verification is manual.

### 2. Find Dupes (Shortcut deduplication)

**What it does**: Find potential duplicate stories, present pairs for review,
execute decisions (archive loser, merge content, add story links).

**Key behaviors**:

- Exclude archived and Released stories from analysis
- Pass 1: keyword/Jaccard similarity on titles (threshold: >=35% or >=3 shared terms after stop word removal)
- Pass 2: semantic review of flagged pairs using titles AND descriptions
- Present one pair at a time with full content for comparison
- Decisions: keep one (archive other), combine into one, keep both, keep both + "relates to" link
- Story link verbs: `duplicates` (loser → winner) or `relates to`

**Idempotency**:

- Check if story link already exists before creating
- Check `archived` status before archiving
- Check for `## Merged from SC-{id}` heading before merging content

### 3. Fill Cards (investigation-driven grooming)

**What it does**: Find stories with empty template sections, investigate across
data sources (Intercom API, PostHog, codebase, Slack), synthesize findings into
card content, and present a complete draft for Paul's approval.

**The goal is an approved draft, not a pushed card.** Pushing to Shortcut is a
separate step that happens only after Paul has reviewed the full card text and
said to ship it. "Let me push it" is not approval. Present the wording, wait
for explicit go-ahead.

**Pre-flight (before starting a card)**:

1. Read the Story Template (above) so section names and expectations are fresh
2. Check the card's workflow state: Need Requirements cards get context to
   support a stakeholder conversation. In Definition cards get the full
   treatment (investigation, solution sketch, all sections).
3. Ask: "Is this a bug or a feature?" Bug cards use a leaner template (skip
   blank Monetization, UI, Reporting, Release sections).
4. Ask: "Is this a new feature or an extension of an existing one?" Frame as
   extension when possible. Identify the closest existing feature surface.
5. Check `box/posthog-events.md` for already-discovered event names in this
   product area. Check `box/queries.md` for saved SQL patterns.
6. **Refresh the Intercom search index** so full-text search covers recent
   conversations. Run from the FeedForward repo root:
   ```
   INTERCOM_FETCH_CONCURRENCY=80 python3 box/intercom-sync.py --since $(date -v-7d +%Y-%m-%d)
   ```
   This syncs conversations updated in the last 7 days (listing + full thread
   fetch). Takes seconds for a week's worth. Use `--status` to check the
   index state. See "Intercom Search Patterns" below for how to query.

**Key behaviors**:

- Rank by most empty sections first, then oldest
- Present one card at a time with full content rendered
- Investigate: Intercom (local search index + API for specific conversations),
  PostHog, codebase, Slack for evidence. See "Intercom Search Patterns" below.
- Synthesize into clear, concise product writing (bullet points, no jargon inflation)
- Don't add ideas Paul didn't express, don't drop ideas he did
- Present the full draft text for review before pushing anything
- "mark as ready" = update + move to Ready to Build + unassign all owners (only after approval)
- Supports voice mode if available

**Verification bar** (before presenting a draft):

- If the card names a database column or table, you've read the schema definition
- If the card names a code file or path, you've confirmed it exists
- If the card recommends a data source, you've traced the write path to confirm it has the data you're claiming
- If the card cites a number, you can point to where it came from

This isn't about constraining creativity or solution design. It's about making
sure the facts underneath the solution are correct before presenting.

**Quality gate**: Run the Card Quality Gate (above) before presenting draft
for approval.

**Story links**: After filling a card, search Shortcut for non-archived cards that
share infrastructure, prerequisites, or overlapping scope. Propose links with the
right verb:

| Verb         | Direction                 | When to use                                                                                                               |
| ------------ | ------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `blocks`     | Subject blocks Object     | Object cannot ship without Subject being done first. Test: "Could Object ship if Subject didn't exist?" If no, it blocks. |
| `relates to` | Bidirectional             | Cards share infrastructure, overlap in scope, or inform each other, but neither is a prerequisite.                        |
| `duplicates` | Subject duplicates Object | Used in Find Dupes play. Subject is the loser (gets archived).                                                            |

Default to `relates to` unless there's a genuine prerequisite dependency. Present
proposed links alongside the card draft for approval.

**Idempotency**:

- Re-fetch current description from Shortcut before each update (don't use stale cache)
- Only update sections Paul explicitly changed — preserve everything else

**Completion (after Paul approves and says to ship)**:

All three steps, every time. Don't stop after the description update.

1. **Update description** via Shortcut API
2. **Move to Ready to Build** (workflow state `500000019`)
3. **Unassign all owners** (`owner_ids: []`)

If any new PostHog event names were discovered during investigation, add them
to `box/posthog-events.md`.

### 4. Recurring Request (Intercom explicit feature request → Shortcut card)

**What it does**: Find a recurring explicit feature request in Intercom that isn't
already tracked in Shortcut, validate it against the codebase and PostHog, and
produce a full card in Ready to Build.

This is one flavor of new-card play. Others (e.g. cards from PostHog anomalies,
codebase patterns, competitive gaps) would have different discovery phases.

**Criteria for a valid candidate**:

- 3+ distinct users clearly asking for the same thing
- At least one conversation in the past 30 days (use Intercom API, DB is stale)
- Not already tracked in Shortcut (search by topic keyword)

**Phase 1: Find the signal**

1. Start with the local Intercom search index for full-thread keyword search
   (see "Intercom Search Patterns" above). This searches all conversation parts
   including admin replies, not just opening messages. Use topic nouns: "RSS",
   "carousel", "hashtag", "undo", etc. Refresh the index first (pre-flight step
   6 from fill-cards). Fall back to the Intercom API `source.body` search for
   opening-message-only queries when needed.
2. Check hit counts to gauge volume. Filter out spam-heavy topics.
3. For each promising topic, search Shortcut (`GET /api/v3/search/stories?query=...`)
   to confirm it's not already tracked.
4. DB can validate volume (GROUP BY issue_signature, COUNT DISTINCT contact_email)
   but is bad for discovery. Most themes are bugs, not feature requests.

**Phase 2: Validate**

1. Read 8-12 actual Intercom conversations to confirm users are asking for the
   same thing. Record conversation IDs and verbatim quotes.
2. Verify at least one conversation is within the last 30 days.
3. Run a codebase Explore subagent (background) to map the relevant feature area.
   Verify key claims from the subagent by reading files yourself.
4. Query PostHog for usage context: how many people use the adjacent feature
   surface, country breakdown if relevant, comparison benchmarks.
5. Before writing the card, ask: "Is this a new feature or an extension of an
   existing one?" Frame as extension when possible. Identify the closest existing
   feature surface and build from there.

**Phase 3: Build the card**

1. Use the Story Template from this document. All sections required for feature
   cards. Architecture Context and Open Questions are included when there are
   meaningful findings.
2. Present the full card text for Paul's review. Don't push to Shortcut until
   explicit approval.
3. Create the story in Ready to Build state, assigned to Tailwind team, Product
   Area inferred from content, no individual owners.

**Verification bar** (same as fill-cards):

- Database columns/tables named on the card: you've read the schema definition
- Code files named on the card: you've confirmed they exist and do what you claim
- Data sources recommended: you've traced the write path
- Numbers cited: you can point to where they came from

**Quality gate**: Run the Card Quality Gate (above) before presenting draft
for approval.

### 5. Customer Reported Bug Discovery (Intercom symptom search → Shortcut bug card)

**What it does**: Find untracked product bugs by searching Intercom for symptom
keywords, cross-referencing reporters against PostHog failure events, and tracing
failure paths in the codebase. Produces a lean bug card in Ready to Build.

This is the bug counterpart to Recurring Request (play 4). Play 4 hunts for
untracked feature requests using topic nouns. This play hunts for untracked bugs
using symptom language.

**Phase 1: Signal hunting**

1. Search the local Intercom index for symptom keywords: "disappeared", "lost",
   "broken", "stuck", "failed", "error", "crash", "missing", "gone", "won't load".
   Refresh the index first (pre-flight step 6 from fill-cards).
2. Score each keyword by volume and signal-to-noise. Low volume + high signal
   ("disappeared": 7 hits, all real bugs) beats high volume + noise ("error": 98
   hits, mostly billing/spam).
3. Check recency: are there instances in the last 30 days? If the most recent
   instance is 6+ months old, flag as historical and deprioritize. Bugs that
   stopped being reported may already be fixed.
4. Check Shortcut to confirm the bug isn't already tracked.
5. Don't stack unreliable methods. DB theme classifications + keyword matching
   against Shortcut titles compounds error. Go to primary sources and use reasoning.

**Phase 2: Read and cluster**

1. Read 8-12 actual conversations behind the best keyword hits. Confirm they
   describe the same symptom.
2. Cluster into candidate bugs. One keyword search may surface multiple distinct
   issues.
3. If any conversation references a Jam recording URL (`jam.dev/c/...`), pull
   structured debug data via the Jam MCP: `getConsoleLogs` for errors,
   `getNetworkRequests` for failed API calls, `getMetadata` for browser/OS context.
   This can surface the technical root cause directly from the user's session.

**Phase 3: Cross-reference to PostHog**

1. Pull contact emails from the Intercom conversations.
2. Query PostHog for failure/error events filtered by those emails. The
   Intercom-to-PostHog email cross-reference is the strongest evidence technique:
   it turns "users say X happens" into "users who say X happens have Y failure
   events."
3. Check volume: query the failure event unfiltered for total count, unique users,
   and weekly trend over 90 days. Spiky patterns suggest infrastructure issues.
   Steady patterns suggest code bugs.

**Phase 4: Codebase trace**

1. Grep the aero codebase for the failure reason or error string.
2. Check whether the failure has user-facing UI copy (error messages, status
   indicators). Unmapped failure reasons that fall through to generic fallbacks
   are higher severity.
3. Trace the failure path: where does the error originate, how does it propagate,
   what does the user see?

**Phase 5: Card**

1. Use the lean bug template: What, Evidence, Architecture Context. Skip
   Monetization, UI Representation, Reporting, Release Strategy unless they have
   real content.
2. Evidence should include: Intercom conversation links with verbatim quotes,
   PostHog event counts with saved insight links, the email cross-reference
   results. If Jam recordings provided debug data, include the key findings
   (specific errors, failed requests).
3. Architecture Context for bugs can be more prescriptive than for features: root
   cause location, failure mechanism, specific code paths. The fix path is
   typically more deterministic.
4. Present the full card text for approval.

**Verification bar** (same as fill-cards):

- Failure reasons named on the card: you've grepped for them in the codebase
- Code files named on the card: you've confirmed they exist and do what you claim
- Numbers cited: you can point to the PostHog saved insight
- Cross-reference claims: you've run the actual query, not inferred from adjacent data

**Quality gate**: Run the Card Quality Gate before presenting draft for approval.

## General Constraints

- **Mutation cap**: 25 mutations per run. Each card creation, description update,
  reaction, thread reply, story link, or archive = 1. Finish the current item
  before checking the cap.
- **Human-in-the-loop**: All three plays present items one at a time and wait for
  Paul's decision. Don't batch-execute without review.
- **Mutation gate**: A PreToolUse hook blocks all Slack mutations (`chat.update`,
  `chat.postMessage`, `chat.delete`, `reactions.add`, `reactions.remove`) and Shortcut
  mutations (PUT/POST/DELETE/PATCH) through Bash. Reads pass through. When blocked,
  route through `agenterminal.execute_approved` or present the command for the user
  to run manually.
- **Rate limiting**: 0.5s delay between sequential API calls. Respect `Retry-After`.

## Intercom Search Patterns

The local search index (`conversation_search_index` table) contains full
conversation threads — all admin replies, internal notes, and customer messages
— not just the opening message. This is the primary tool for Intercom evidence
gathering. The Intercom API `source.body` search only hits the first message.

**Refresh before use** (pre-flight step 6):

```
INTERCOM_FETCH_CONCURRENCY=80 python3 box/intercom-sync.py --since $(date -v-7d +%Y-%m-%d)
```

**Full-text search** (searches all conversation parts):

```sql
SELECT conversation_id, source_body, part_count,
       ts_rank(to_tsvector('english', full_text), query) AS rank
FROM conversation_search_index,
     to_tsquery('english', 'screen & recording') AS query
WHERE to_tsvector('english', full_text) @@ query
ORDER BY rank DESC
LIMIT 20;
```

**ILIKE fallback** (when you need exact phrase or partial match):

```sql
SELECT conversation_id, source_body, part_count
FROM conversation_search_index
WHERE full_text ILIKE '%jam.dev%'
ORDER BY updated_at DESC
LIMIT 20;
```

**Fetch a specific conversation** (when you have an ID from search results,
Slack, or a CS person):

```
curl -s "https://api.intercom.io/conversations/{ID}" \
  -H "Authorization: Bearer $INTERCOM_ACCESS_TOKEN" \
  -H "Intercom-Version: 2.11" \
  -H "Accept: application/json"
```

**Check index health**:

```
python3 box/intercom-sync.py --status
```

**Key limitations**:

- `source.body` API search only hits opening messages (see API Quirks above)
- The indexer covers `comment`, `assignment`, `close`, `open`, and `note` parts.
  Internal notes with Intercom Insight boilerplate ("Insight has been recorded...")
  are filtered out. Other part types (`snoozed`, `timer_unsnooze`,
  `fin_guidance_applied`, `default_assignment`, `conversation_attribute_updated_by_admin`,
  `company_updated`, `channel_and_reply_time_expectation`) have no useful body text
  and are excluded. See API Quirks for the full `part_type` breakdown.
- The local index is as fresh as the last `--since` run. Always refresh first.

## Jam MCP (Screen Recording Debug Data)

Jam is a screen recording tool used by CS agents. When a customer reports a visual
bug or behavioral issue, CS asks them to record a Jam. The recording captures
console logs, network requests, user events, and video — structured debug data
that's otherwise lost in text descriptions.

**Use case for investigations**: During card-fill or recurring-request plays, when
an Intercom conversation references a Jam recording (URL like `jam.dev/c/...`),
use the Jam MCP to extract structured debug data. This replaces manually opening
the Jam link and reading through the recording.

**MCP server configuration**:

```
Server URL: https://mcp.jam.dev/mcp
Transport: HTTP (streamable)
Auth: OAuth (sign in to Jam workspace when prompted)
```

**Setup** (one-time, per machine):

```bash
claude mcp add -s user Jam -- npx -y mcp-remote@latest https://mcp.jam.dev/mcp
```

Uses `mcp-remote` as a stdio proxy (same pattern as PostHog). The `-s user` flag
stores the config in `~/.claude.json` (available across all projects). On first
use, `mcp-remote` opens a browser for Jam OAuth. The native `-t http` transport
doesn't complete the OAuth flow — always use `mcp-remote` for OAuth-based HTTP
MCP servers.

**Available tools**:

| Tool                 | Purpose                                            |
| -------------------- | -------------------------------------------------- |
| `getDetails`         | Full Jam details (title, description, reporter)    |
| `getConsoleLogs`     | Console output during recording (errors, warnings) |
| `getNetworkRequests` | HTTP requests/responses (API failures, 4xx/5xx)    |
| `getScreenshot`      | Screenshot at a specific timestamp                 |
| `getUserEvents`      | Click/scroll/input events during recording         |
| `getMetadata`        | Browser, OS, screen size, URL                      |
| `getVideoTranscript` | Transcript of the recording (narration if present) |
| `analyzeVideo`       | AI analysis of the video content                   |
| `listJams`           | List Jams (filter by folder, date, etc.)           |
| `listMembers`        | Workspace members                                  |
| `listFolders`        | Workspace folders                                  |
| `createComment`      | Add a comment to a Jam                             |
| `updateJam`          | Update Jam metadata (title, folder, etc.)          |

**Investigation pattern**: When a conversation mentions a Jam URL, extract the
Jam ID from the URL, then call `getConsoleLogs` and `getNetworkRequests` to find
the technical root cause. `getMetadata` gives browser/OS context. This is
especially useful for visual bugs and intermittent failures where the customer
description alone isn't enough to reproduce.

**Jam flow markers in Intercom** (searchable in the index after the part_type fix):

| Phase    | part_type    | Search pattern                                    | Notes                                                    |
| -------- | ------------ | ------------------------------------------------- | -------------------------------------------------------- |
| Offer    | `assignment` | `"Would you mind taking a screen recording"`      | Mike's canned Jam prompt. ~380 hits across full history. |
| Complete | `note`       | `"Jam created!"` or `"View the screen recording"` | Intercom app card confirming upload succeeded.           |

The offer marker finds every conversation where CS offered Jam. The complete
marker finds where a recording was actually uploaded. The gap between them
(offer without complete) indicates the customer didn't follow through — but
determining why requires reading the conversation, not string matching.

## Product Area Keywords

For inferring Product Area when creating new cards from Slack ideas.

| Product Area     | Keywords / signals                                                                                                                                       |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SMARTPIN         | smartpin, smart pin, template, pin generation, AI pin, design customization, text overlay, branded color, style tone, URL page, sitemap, bulk activation |
| PIN SCHEDULER    | scheduler, schedule pin, bulk edit, bulk delete, pin draft, date range, carousel, image grid, pin from URL, alt text, SEO filename                       |
| TURBO            | turbo, boost, engagement, turbo feed, turbo queue, turbo onboarding, auto-queue, auto-renew, moderation                                                  |
| KEYWORD RESEARCH | keyword, keyword search, keyword plan, commercial intent, CSV import, saved keywords                                                                     |
| EXTENSION        | extension, browser extension, visit site, outbound click, turbo extension                                                                                |
| CREDITS          | credit, credit cost, credit refresh, credit consumption, credit visibility                                                                               |
| META             | instagram, facebook, IG, FB, meta, grid planner                                                                                                          |
| NAV              | navigation, nav, product-focused nav                                                                                                                     |
| BILLING          | billing, subscription, cancel, past-due, invoice                                                                                                         |
| API/MCP          | API, MCP, ChatGPT, integration, workflow, app store                                                                                                      |
| M4U              | made for you, generate a pin, pin from URL, URL scrape, labs, ghostwriter pin                                                                            |
| GHOSTWRITER      | ghostwriter, ghost writer, GW, bulk ghostwriter, AI generation stuck, generation failed                                                                  |

**Tie-break priority** (most specific wins): GHOSTWRITER > PIN SCHEDULER (for ghostwriter-specific issues), EXTENSION > TURBO, KEYWORD RESEARCH > SMARTPIN > M4U > PIN SCHEDULER, CREDITS > BILLING. When ambiguous, propose best guess and flag it.

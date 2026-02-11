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

### Slack

| Thing                | Value                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------- |
| #ideas channel ID    | `C0ADJ4ATJE4`                                                                          |
| Bot scopes confirmed | `channels:read`, `channels:history`, `reactions:read`, `reactions:write`, `chat:write` |
| Bot scope missing    | `users:read` (can't resolve Slack user IDs to names)                                   |

## API Quirks

- **Group stories endpoint** (`/groups/{id}/stories`) does NOT include `description`. Must fetch individual stories via `GET /stories/{id}` for full content.
- **JSON payloads**: Always construct with Python `json.dumps()`. Bash string interpolation breaks on quotes, newlines, and markdown in descriptions.
- **Slack `already_reacted`**: Treat as success, not error.
- **Slack `Retry-After`**: Sleep the specified duration, then retry.
- **Story link conflicts**: "Cannot create a duplicate story link" means it already exists — treat as success.
- **Pagination**: Shortcut search returns 25 per page. Slack history returns up to 200 with cursor-based pagination. Always check for `has_more` / `next`.

## Story Template

New Shortcut cards use this description template:

```
[Link to original idea in Slack](PERMALINK)

## "What"
-

## Evidence
-

## Monetization Angle
-

## UI Representation (Wireframes, descriptions of visuals, etc.)
-

## Reporting Needs/Measurement Plan
-

## Release strategy
-
```

### Section expectations

Most cards today are bare-bones — a one-liner "What" and dashes everywhere else.
The goal is to make each section substantive:

- **"What"**: Clear feature description. What does this do, who is it for, what
  changes from the user's perspective. Not just a verbatim Slack quote.
- **Evidence**: Data points, customer quotes, support ticket counts, usage metrics
  — anything that demonstrates demand or validates the need.
- **Monetization Angle**: How this connects to revenue. Credit consumption,
  conversion, retention, upsell path.
- **UI Representation**: Wireframes, mockups, or written descriptions of what the
  user sees and interacts with.
- **Reporting Needs/Measurement Plan**: What to measure to know if this worked.
  Events to track, success criteria, dashboards.
- **Release strategy**: Phasing, feature flags, beta groups, rollout plan.

When creating cards from investigations, populate sections with findings rather
than leaving them empty. The fill-cards play is for fleshing out what's missing.

## The Three Plays

### 1. Sync Ideas (Slack #ideas → Shortcut)

**What it does**: Match ideas posted in Slack #ideas to Shortcut stories. Create
cards for unmatched ideas, add link-back lines to story descriptions, add
`:shortcut:` reactions to Slack messages, post thread replies with story links.

**Key behaviors**:

- Default data window: last 90 days of Slack messages
- Each top-level Slack message = one idea (threads may contain sub-ideas)
- Matching is semantic — compare idea text against story titles and descriptions
- Likely matches need Paul's confirmation one at a time
- New cards go to "In Definition" state, owned by Paul, assigned to Tailwind team
- Infer Product Area from idea text using keyword matching (see Product Area Keywords below)
- All In Definition stories should be assigned to Paul

**Idempotency**:

- Check for existing `:shortcut:` reaction before adding
- Check thread for existing bot reply with same Shortcut URL before posting
- Check story description for existing link line before prepending
- `already_reacted` from Slack = success

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

**Key behaviors**:

- Rank by most empty sections first, then oldest
- Present one card at a time with full content rendered
- Investigate: hit Intercom API (not just DB), PostHog, codebase, Slack for evidence
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

**Idempotency**:

- Re-fetch current description from Shortcut before each update (don't use stale cache)
- Only update sections Paul explicitly changed — preserve everything else

## General Constraints

- **Mutation cap**: 25 mutations per run. Each card creation, description update,
  reaction, thread reply, story link, or archive = 1. Finish the current item
  before checking the cap.
- **Human-in-the-loop**: All three plays present items one at a time and wait for
  Paul's decision. Don't batch-execute without review.
- **Rate limiting**: 0.5s delay between sequential API calls. Respect `Retry-After`.

## Product Area Keywords

For inferring Product Area when creating new cards from Slack ideas.

| Product Area     | Keywords / signals                                                                                                                                       |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SMARTPIN         | smartpin, smart pin, template, pin generation, AI pin, design customization, text overlay, branded color, style tone, URL page, sitemap, bulk activation |
| PIN SCHEDULER    | scheduler, schedule pin, bulk edit, bulk delete, ghostwriter, pin draft, date range, carousel, image grid, pin from URL, alt text, SEO filename          |
| TURBO            | turbo, boost, engagement, turbo feed, turbo queue, turbo onboarding, auto-queue, auto-renew, moderation                                                  |
| KEYWORD RESEARCH | keyword, keyword search, keyword plan, commercial intent, CSV import, saved keywords                                                                     |
| EXTENSION        | extension, browser extension, visit site, outbound click, turbo extension                                                                                |
| CREDITS          | credit, credit cost, credit refresh, credit consumption, credit visibility                                                                               |
| META             | instagram, facebook, IG, FB, meta, grid planner                                                                                                          |
| NAV              | navigation, nav, product-focused nav                                                                                                                     |
| BILLING          | billing, subscription, cancel, past-due, invoice                                                                                                         |
| API/MCP          | API, MCP, ChatGPT, integration, workflow, app store                                                                                                      |

**Tie-break priority** (most specific wins): EXTENSION > TURBO, KEYWORD RESEARCH > SMARTPIN > PIN SCHEDULER, CREDITS > BILLING. When ambiguous, propose best guess and flag it.

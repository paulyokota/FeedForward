# Investigation Log

Observations from investigations that might point toward tooling, process
improvements, or patterns worth codifying. Not every entry here becomes a tool.
Entries accumulate until a pattern emerges across multiple investigations.

**What belongs here:**

- Something was slow that could be faster
- Something was manual that could be automated
- Something was repeated across investigations
- A workaround that suggests a missing tool
- An approach that worked surprisingly well and should be reused
- Something that almost didn't happen because it wasn't obvious to try
- A data source quirk that's easy to forget between sessions

**What doesn't belong here:**

- One-off findings from a specific investigation (those go in the story)
- Tactical codebase notes (those go in auto memory)

## Entries

### 2026-02-11 — First investigation (multi-language AI content generation)

- **PostHog event names aren't guessable.** Tried `smart_pin_generated`, actual name
  was `Generated SmartContent descriptions`. Had to use `event-definitions-list` with
  keyword search to find the right names. This will happen every investigation.

- **Country breakdown is a useful reach proxy but requires manual non-English classification.**
  PostHog gives country codes, but deciding which countries are "non-English-primary" was
  a manual judgment call with a hardcoded list. If we do reach estimation often, a reusable
  country-to-language mapping would save time and improve consistency.

- **Pipeline classifications were unreliable.** Started with theme classifications from
  the old pipeline, user corrected to verify against primary source text. The primary
  sources were richer and more convincing. Default should always be: read `source_body`
  / `support_insights`, not trust `issue_signature` or `user_intent` classifications.

- **Querying the FeedForward DB required figuring out the schema each time.** Had to
  explore tables, column names, relationships. A quick-reference of the key tables and
  their useful columns would save 5-10 minutes per investigation.

- **The aero codebase navigation was ad-hoc.** Found SmartPin prompts by searching for
  keywords. A lightweight map of "where AI generation code lives" would have been faster.
  But this might be too specific to one investigation to generalize yet.

- **The "almost didn't happen" moment:** Pivoting from total user counts to country
  breakdown for reach estimation. The initial numbers (3,500+ SmartPin users) were
  technically correct but not the right question. The right question was "how many of
  those users are non-English?" That pivot made the story much stronger. Worth
  remembering: always ask "is the denominator right?"

- **Tried Intercom MCP three times before giving up.** Searched for "intercom" MCP tools,
  got nothing. User corrected: "API not mcp for intercom." There are two access paths:
  (1) the FeedForward PostgreSQL DB which has cached/imported conversations, and (2) the
  Intercom API via `src/intercom_client.py`. No MCP server. The DB data gets staler every
  day we don't run the import pipeline. For investigations about recent activity, may need
  to pull fresh data via the API first.

- **`issue_type` column is useless — all 16,593 rows are "other".** First query tried
  to filter by `issue_type = 'feature_request'` and got zero rows. Had to discover that
  the themes table (`issue_signature`, `user_intent`) is where the real signal lives.
  The conversations table's classification fields are essentially noise.

- **SQL errors added friction.** `column "classification" does not exist` (wrong column
  name), then `ORDER BY expressions must appear in select list` (DISTINCT + ORDER BY
  incompatibility). Two failed queries before finding the right pattern. A reusable
  "find recurring themes with N+ distinct users" query would eliminate this every time.

- **Subagent for codebase exploration worked really well.** Spawned an Explore agent to
  map AI language handling in the aero repo. Got a comprehensive report back in ~90
  seconds. Much faster and more thorough than manually grepping. Worth reusing for
  codebase-heavy investigations.

- **The investigation hit context limits mid-stream.** Research phase consumed ~168k
  tokens and triggered automatic compaction before PostHog analysis was complete.
  The investigation had to be resumed in a new context window. For longer investigations,
  this is a real constraint — need to either work faster or structure work so partial
  results are saved somewhere durable before context runs out.

- **Real-time user corrections shaped the whole methodology.** Three corrections in quick
  succession ("API not mcp", "primary sources only", "ensure they're talking about the
  same thing") turned what could have been a sloppy surface-level investigation into a
  rigorous one. The pipeline can't do this. This might be the single strongest argument
  for the Claude-in-a-Box approach.

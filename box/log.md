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

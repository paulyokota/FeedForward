# Saved Queries

Reusable SQL queries for the FeedForward PostgreSQL database. Run via
`python3 -c` with `psycopg2` or any Postgres client.

Connection: `postgresql://localhost:5432/feedforward`

## Schema Quick Reference

```
conversations (PK: id)
  id, contact_email, contact_id, source_body, created_at,
  issue_type (ALL "other", useless), support_insights (JSONB)

themes (joins via conversation_id)
  id, conversation_id, issue_signature, user_intent, product_area,
  component, diagnostic_summary, key_excerpts (JSONB), extracted_at
```

## Recurring Themes (3+ distinct users)

The go-to query for finding themes with multiple distinct users. Start here
when looking for repeated issues or feature requests.

```sql
SELECT
    t.issue_signature,
    t.user_intent,
    t.product_area,
    COUNT(DISTINCT c.contact_email) AS distinct_users,
    COUNT(*) AS conversation_count,
    MAX(c.created_at) AS most_recent
FROM themes t
JOIN conversations c ON t.conversation_id = c.id
WHERE c.contact_email IS NOT NULL
GROUP BY t.issue_signature, t.user_intent, t.product_area
HAVING COUNT(DISTINCT c.contact_email) >= 3
ORDER BY distinct_users DESC, most_recent DESC;
```

**Notes:**

- `issue_signature` is the canonical theme name (e.g., `ai_language_mismatch`)
- Most themes are bugs/failures. Feature requests are rare in this table.
- For feature request discovery, use Intercom API topic-keyword search instead.
- This query is better for validating volume of known issues.

## Recurring Themes with Recency Filter

Same as above, but only themes with at least one conversation in the last 90 days.
Prevents surfacing stale historical issues.

```sql
SELECT
    t.issue_signature,
    t.user_intent,
    t.product_area,
    COUNT(DISTINCT c.contact_email) AS distinct_users,
    COUNT(*) AS conversation_count,
    MAX(c.created_at) AS most_recent,
    MIN(c.created_at) AS earliest
FROM themes t
JOIN conversations c ON t.conversation_id = c.id
WHERE c.contact_email IS NOT NULL
GROUP BY t.issue_signature, t.user_intent, t.product_area
HAVING COUNT(DISTINCT c.contact_email) >= 3
    AND MAX(c.created_at) > NOW() - INTERVAL '90 days'
ORDER BY distinct_users DESC;
```

## Theme Detail (conversations for a specific signature)

Once you've found a signature of interest, pull the individual conversations
with verbatim quotes.

```sql
SELECT
    c.id AS conversation_id,
    c.contact_email,
    c.created_at,
    LEFT(c.source_body, 200) AS snippet,
    t.diagnostic_summary,
    t.user_intent
FROM themes t
JOIN conversations c ON t.conversation_id = c.id
WHERE t.issue_signature = 'REPLACE_ME'
ORDER BY c.created_at DESC;
```

## Conversation Count by Product Area

Quick snapshot of where support volume concentrates.

```sql
SELECT
    t.product_area,
    COUNT(DISTINCT t.issue_signature) AS unique_signatures,
    COUNT(DISTINCT c.contact_email) AS unique_users,
    COUNT(*) AS conversations
FROM themes t
JOIN conversations c ON t.conversation_id = c.id
GROUP BY t.product_area
ORDER BY conversations DESC;
```

## Search Conversations by Keyword

When looking for specific topics in conversation text. Useful for feature
request discovery when the themes table doesn't surface what you need.

```sql
SELECT
    c.id,
    c.contact_email,
    c.created_at,
    LEFT(c.source_body, 300) AS snippet
FROM conversations c
WHERE c.source_body ILIKE '%KEYWORD%'
ORDER BY c.created_at DESC
LIMIT 20;
```

**Remember:** `source_body` is the opening message only. For full conversation
text, check `support_insights->>'full_conversation'` (populated by the
classification pipeline, not available for all conversations).

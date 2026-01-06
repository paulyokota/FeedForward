# Intercom Data Access Patterns

Lessons learned from fetching and analyzing Intercom conversation data.

## API Access

**Endpoint**: `https://api.intercom.io/conversations`
**Version**: 2.11 (set via `Intercom-Version` header)
**Auth**: Bearer token (Base64-encoded)

### Working Endpoints

```bash
# List conversations (paginated)
GET /conversations?per_page=50

# Get single conversation with full thread
GET /conversations/{id}

# Search conversations by content
POST /conversations/search
{
  "query": {"field": "source.body", "operator": "~", "value": "keyword"},
  "pagination": {"per_page": 20}
}
```

### Token Limitations

Our token can:

- List conversations
- Get individual conversation details
- Search by body content

Our token cannot:

- Filter by state (`?state=open` returns unauthorized)
- Access data attributes schema
- Some admin-only endpoints

## Data Quality Issues

### Problem: Many conversations are not customer support requests

Out of 50 random conversations, only ~24 (48%) were usable for classification training.

**Bad conversation types:**

| Issue           | Count | Example                                 |
| --------------- | ----- | --------------------------------------- |
| Admin-authored  | 17    | Outbound emails from support team       |
| Admin-initiated | 14    | Proactive outreach campaigns            |
| Template clicks | 5     | "I have a product question or feedback" |
| Automated       | 3     | System-generated notifications          |
| Too short       | 2     | "hi", "hello"                           |

### Quality Filter Logic

```python
def is_quality_conversation(conv):
    src = conv.get('source', {})

    # Must be customer-initiated
    if src.get('delivered_as') != 'customer_initiated':
        return False

    # Author must be user (not admin, bot, or lead)
    if src.get('author', {}).get('type') != 'user':
        return False

    body = strip_html(src.get('body', ''))

    # Must have real content
    if len(body) < 20:
        return False

    # Not a template click
    if body.lower() in ['i have a product question or feedback', 'hi', 'hello']:
        return False

    return True
```

## Key Fields for Classification

### Input Fields (what LLM sees)

| Field            | Description                     | Use                           |
| ---------------- | ------------------------------- | ----------------------------- |
| `source.body`    | Initial customer message (HTML) | Primary classification input  |
| `source.subject` | Email subject line              | Additional context for emails |
| `source.type`    | `conversation` or `email`       | Channel indicator             |

### Metadata Fields (for filtering/enrichment)

| Field                   | Description                                          |
| ----------------------- | ---------------------------------------------------- |
| `source.delivered_as`   | `customer_initiated`, `automated`, `admin_initiated` |
| `source.author.type`    | `user`, `admin`, `bot`, `lead`                       |
| `source.author.email`   | Customer email                                       |
| `state`                 | `open`, `closed`, `snoozed`                          |
| `priority`              | `priority`, `not_priority`                           |
| `ai_agent_participated` | Boolean - did Fin handle this?                       |

### Existing Classification (from Intercom)

| Field                                             | Sample Values                            |
| ------------------------------------------------- | ---------------------------------------- |
| `topics[].name`                                   | "Billing" (only topic observed)          |
| `tags[].name`                                     | "Non-Ecomm"                              |
| `custom_attributes.Language`                      | "English"                                |
| `custom_attributes.Fin AI Agent resolution state` | "Confirmed Resolution", "Routed to team" |

## Search Strategies for Diverse Samples

To get representative samples across issue types, use targeted searches:

```python
searches = {
    "churn": ["cancel subscription", "refund", "leaving", "not using anymore"],
    "access": ["can't login", "password", "locked out", "reset password"],
    "feature": ["would be great if", "suggestion", "please add"],
    "frustrated": ["annoying", "terrible", "broken", "unacceptable"],
    "bug": ["error message", "not working", "glitch"],
}
```

This yielded 42 diverse quality samples vs 24 from random sampling.

## Pagination

Intercom uses cursor-based pagination:

```json
{
  "pages": {
    "next": {
      "starting_after": "WzE3Njc3MjUwODkwMDAsMjU1NDcwNDAxMjMsMl0="
    }
  }
}
```

Use the `starting_after` value from response to fetch next page. Cannot construct cursors manually.

## Rate Limits

Not hit during this session, but Intercom has standard rate limits. For batch processing:

- Consider adding delays between requests
- Use search with larger `per_page` values (up to 150)
- Cache results locally

## Recommendations for Production

1. **Filter early**: Apply quality filters before LLM classification to save costs
2. **Batch by time**: Process conversations from specific time windows
3. **Use search**: Target specific issue types rather than random sampling
4. **Cache responses**: Store raw API responses for reprocessing
5. **Handle HTML**: Always strip HTML from body before classification

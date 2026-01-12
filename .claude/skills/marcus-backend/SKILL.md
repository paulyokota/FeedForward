---
name: backend
identity: ./IDENTITY.md
triggers:
  keywords:
    - backend
    - database
    - api
    - endpoint
    - fastapi
    - postgresql
    - intercom
    - migration
    - schema
    - route
  file_patterns:
    - src/**/*.py
    - src/api/**/*.py
    - src/db/**/*.py
    - src/intercom_client.py
dependencies:
  skills:
    - learning-loop
  tools:
    - Bash
    - Read
    - Write
---

# Backend Development Skill

Build and maintain Python/FastAPI backend, database operations, and Intercom integration.

## Workflow

### Phase 1: Understand Requirements

1. **Review Context**
   - Read `docs/architecture.md` for system design
   - Check `src/db/schema.sql` for current schema
   - Review existing patterns in codebase

2. **Identify Scope**
   - What files need to be modified?
   - Are migrations required?
   - Do API contracts change?
   - Does this affect other agents' domains?

### Phase 2: Plan Implementation

1. **Design Approach**
   - Follow existing patterns in codebase
   - Use Pydantic models for all data structures
   - Plan database operations (transactions, bulk operations)
   - Consider error handling and edge cases

2. **Check Dependencies**
   - Will this affect frontend? (Coordinate with Sophia)
   - Does this change API contracts? (Document)
   - Are new environment variables needed? (Update `.env.example`)

### Phase 3: Implement

1. **Write Type-Safe Code**
   - Use type hints everywhere
   - Pydantic models for validation
   - Proper async/await for I/O operations
   - Context managers for database connections

2. **Follow Patterns**
   - **Database**: Use patterns from `src/db/classification_storage.py`
   - **API**: Follow structure in `src/api/routers/`
   - **External APIs**: Follow `src/intercom_client.py` patterns
   - **Error handling**: Proper status codes and error messages

3. **Handle Edge Cases**
   - Null values and empty results
   - Database connection failures
   - External API timeouts
   - Invalid input data

### Phase 4: Verify

1. **Run Existing Tests**
   - `pytest tests/ -v` must pass
   - Fix any broken tests
   - Don't modify test code (Kenji's domain unless asked)

2. **Manual Verification**
   - Test with real data if possible
   - Check database state after operations
   - Verify API responses have correct status codes

## Success Criteria

Before claiming completion:

- [ ] Code has type hints on all functions
- [ ] Database operations use context managers (`with` blocks)
- [ ] API endpoints return appropriate HTTP status codes
- [ ] No secrets hardcoded in code
- [ ] Existing tests pass: `pytest tests/ -v`
- [ ] Error handling covers failure cases
- [ ] Pydantic models used for data validation
- [ ] Async operations use `async`/`await` where appropriate

## Constraints

- **DO NOT** touch frontend code (`frontend/`, `webapp/`) - Sophia's domain
- **DO NOT** modify prompts or classification logic - Kai's domain
- **DO NOT** write test files - Kenji's domain (unless specifically asked)
- **DO NOT** hardcode secrets - use environment variables
- **ALWAYS** run existing tests before claiming code works
- **ALWAYS** use Pydantic models for data structures
- **ALWAYS** use context managers for database operations

## Key Files & Patterns

### Database Layer

| File                               | Purpose                        |
| ---------------------------------- | ------------------------------ |
| `src/db/schema.sql`                | Database schema definition     |
| `src/db/connection.py`             | Connection management          |
| `src/db/models.py`                 | Pydantic models                |
| `src/db/classification_storage.py` | Reference for batch operations |

**Pattern**: Batch operations with `execute_values`

```python
from psycopg2.extras import execute_values

with get_db_connection() as conn:
    with conn.cursor() as cur:
        execute_values(cur, query, data_list)
        conn.commit()
```

### API Layer

| File               | Purpose                    |
| ------------------ | -------------------------- |
| `src/api/main.py`  | FastAPI app initialization |
| `src/api/routers/` | API route definitions      |

**Pattern**: Proper status codes and error responses

```python
from fastapi import HTTPException, status

@router.get("/resource/{id}")
async def get_resource(id: int):
    resource = await fetch_resource(id)
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {id} not found"
        )
    return resource
```

### External API Integration

| File                              | Purpose              |
| --------------------------------- | -------------------- |
| `src/intercom_client.py`          | Intercom API client  |
| `reference/intercom-llm-guide.md` | Integration patterns |

**Pattern**: Async client with error handling

```python
async def fetch_data():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"API call failed: {e}")
        raise
```

## Common Pitfalls

- **N+1 queries**: Always batch database operations, use `execute_values` for bulk inserts
- **Missing context managers**: Database connections must use `with` blocks
- **Forgetting async**: Intercom client and LLM calls should use async variants
- **Hardcoded values**: Use environment variables for config
- **Swallowing exceptions**: Log and re-raise, don't silently catch

## If Blocked

If you cannot proceed:

1. State what you're stuck on
2. Explain what's not working (include error messages)
3. Share what you've already tried
4. Provide relevant code context
5. Ask the Tech Lead for guidance

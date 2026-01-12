---
name: schema-validator
triggers:
  keywords:
    - validate schema
    - schema consistency
    - model validation
    - schema sync
dependencies:
  tools:
    - Read
    - Grep
---

# Schema Validator Skill

Validate consistency between Pydantic models, database schema, and LLM output contracts.

## Purpose

Ensure data consistency across all layers: Pydantic models (Python), database schema (SQL), and LLM output format (prompts).

## Workflow

### Phase 1: Inventory Schemas

1. **Find Pydantic Models**
   - Search `src/models/` or similar directories
   - Identify data models with fields and types
   - Note enum definitions

2. **Find Database Schema**
   - Check `src/db/schema.sql`
   - Look for migrations in `src/db/migrations/`
   - Review `docs/architecture.md` for schema docs

3. **Find LLM Output Schema**
   - Read `docs/prompts.md` for classification schema
   - Check prompt definitions for output format
   - Identify expected field names and types

### Phase 2: Compare Field Definitions

1. **Field Names**
   - Do field names match across all layers?
   - Check for case differences (snake_case vs camelCase)
   - Identify missing fields

2. **Field Types**
   - Are types compatible?
   - Pydantic `str` ↔ Database `VARCHAR`
   - Pydantic `int` ↔ Database `INTEGER`
   - Pydantic `float` ↔ Database `FLOAT`
   - Check enum values match exactly

3. **Required vs Optional**
   - Pydantic `Optional[str]` vs Database `NULL`
   - Are nullable fields aligned?
   - Are required fields enforced everywhere?

### Phase 3: Check Constraints

1. **String Length Limits**
   - Pydantic max_length vs Database VARCHAR(N)
   - Will database reject valid Pydantic values?

2. **Numeric Ranges**
   - Min/max constraints
   - Decimal precision
   - Integer bounds

3. **Enum Value Sets**
   - Do enum values match exactly?
   - Same spelling and case?
   - All values present in all layers?

4. **Nullable Fields**
   - Pydantic Optional vs Database NULL
   - Consistent nullability across layers

### Phase 4: Identify Mismatches

1. **Missing Fields**
   - Field exists in one layer but not others
   - Which layer is missing it?

2. **Type Incompatibilities**
   - Type mismatch between layers
   - Potential data loss or validation failure

3. **Naming Inconsistencies**
   - snake_case in database, camelCase in models
   - Abbreviations differ
   - Spelling variations

## Output Format

```markdown
## Schema Validation Report

### Schemas Found

- Pydantic: [file paths]
- Database: [file paths]
- LLM Output: docs/prompts.md

### Field Comparison

| Field           | Pydantic   | Database    | LLM Output  | Status |
| --------------- | ---------- | ----------- | ----------- | ------ |
| issue_type      | str (enum) | VARCHAR(50) | enum list   | ✅     |
| priority        | str        | VARCHAR(20) | enum list   | ✅     |
| sentiment_score | float      | FLOAT       | -1.0 to 1.0 | ✅     |

### Issues Found

1. **[MISMATCH]** Field `foo`:
   - Pydantic: `Optional[str]`
   - Database: `NOT NULL`
   - Fix: [recommendation]

2. **[MISSING]** Field `bar`:
   - Present in: Pydantic
   - Missing from: Database
   - Fix: [recommendation]

### Recommendations

- [Specific fix]
```

## Success Criteria

- [ ] All schema locations identified
- [ ] Field comparison table complete
- [ ] Mismatches documented with severity
- [ ] Recommendations provided
- [ ] Intentional differences noted (e.g., audit fields in DB)

## Constraints

- **Don't modify files** - only report issues
- **Flag severity** - breaking vs cosmetic
- **Consider migration implications** - DB changes need migrations
- **Note intentional differences** - DB may have extra audit fields

## Key Files

| File                | Schema Type                 |
| ------------------- | --------------------------- |
| `src/db/models.py`  | Pydantic models             |
| `src/db/schema.sql` | Database schema             |
| `docs/prompts.md`   | LLM output schema           |
| `src/api/routers/`  | API request/response models |

## Common Pitfalls

- **Assuming names match**: Check for snake_case vs camelCase
- **Missing enums**: Enum values must match exactly across layers
- **Ignoring nullability**: Optional in code, NOT NULL in database = bug
- **Not checking length**: VARCHAR(50) in DB, no max_length in Pydantic

## Integration with Marcus

This skill is typically invoked when:

- Database schema changes
- Pydantic models updated
- LLM output format changes
- Before migrations

## If Blocked

If you cannot proceed:

1. State which schema you can't find
2. Explain where you've looked
3. Provide partial comparison if available
4. Request clarification on expected schema location

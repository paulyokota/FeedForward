---
name: escalation-validator
triggers:
  keywords:
    - validate escalation
    - escalation rules
    - rule validation
    - escalation edge cases
dependencies:
  tools:
    - Read
    - Grep
---

# Escalation Validator Skill

Validate escalation rules for correctness, completeness, and consistency.

## Purpose

Ensure escalation rules are logical, cover edge cases, and have no conflicts or gaps.

## Workflow

### Phase 1: Load Rules

1. **Read Rules Document**
   - Load from `docs/escalation-rules.md`
   - Identify all rule definitions

2. **Find Rule Engine Code**
   - Check if rules are implemented in code
   - Locate rule evaluation logic
   - Identify where rules are applied

### Phase 2: Check Rule Logic

1. **Contradicting Rules**
   - Do any rules conflict?
   - Can two rules match same input with different actions?

2. **Unreachable Rules**
   - Is any rule shadowed by higher priority rule?
   - Can any rule never trigger?

3. **Default/Fallback Rule**
   - Is there a catch-all for unmatched cases?
   - What happens if no rules match?

4. **Condition Validity**
   - Do conditions use valid field values?
   - Are enums spelled correctly?
   - Are ranges sensible?

### Phase 3: Test Edge Cases

Create test scenarios and trace through rules:

1. **Boundary Conditions**
   - High priority + low churn: what happens?
   - Sentiment exactly at threshold: which way?
   - Multiple conditions match: correct precedence?

2. **Missing Fields**
   - What if optional field is null?
   - Graceful handling or error?

3. **Extreme Values**
   - Sentiment = -1.0 exactly
   - Priority = CRITICAL + high churn
   - Issue count at exact threshold

### Phase 4: Validate Actions

1. **Action Implementation**
   - Are all referenced actions implemented?
   - Do action handlers exist in code?

2. **Required Credentials**
   - Are credentials documented in `.env.example`?
   - Are missing credentials handled gracefully?

3. **Action Parameters**
   - Are action parameters valid?
   - Do they match action handler signature?

### Phase 5: Check Thresholds

1. **Frequency Thresholds**
   - Are they reasonable? (not too low/high)
   - Based on real data?

2. **Sentiment Thresholds**
   - Align with scale (-1 to 1)?
   - Make sense in context?

3. **No Magic Numbers**
   - Are thresholds explained/documented?
   - Why these specific values?

## Output Format

```markdown
## Escalation Rules Validation

### Rules Analyzed

[List of rules by ID]

### Logical Issues

1. **[CONFLICT]** Rules R001 and R005:
   - Both match: `priority=CRITICAL AND issue_type=PRODUCT_BUG`
   - Different actions: PAGE_ONCALL vs CREATE_JIRA
   - Fix: [recommendation]

2. **[UNREACHABLE]** Rule R007:
   - Shadowed by R002 (higher priority, broader condition)
   - Fix: [recommendation]

### Edge Cases

| Scenario                             | Expected     | Actual       | Status               |
| ------------------------------------ | ------------ | ------------ | -------------------- |
| Critical bug, enterprise, high churn | Page on-call | Page on-call | ✅                   |
| Feature request, 9 mentions          | No action    | No action    | ⚠️ (threshold is 10) |

### Missing Coverage

- No rule handles: [scenario]
- Consider adding: [recommendation]

### Action Validation

| Action           | Configured         | Credentials       | Status |
| ---------------- | ------------------ | ----------------- | ------ |
| PAGE_ONCALL      | ❌ Not implemented | N/A               | ⚠️     |
| ALERT_CS_MANAGER | ✅                 | SLACK_WEBHOOK_URL | ✅     |

### Recommendations

- [Specific improvement]
```

## Success Criteria

- [ ] All rules checked for logical consistency
- [ ] Edge cases tested with trace examples
- [ ] Action implementations verified
- [ ] Thresholds validated for reasonableness
- [ ] Gaps in coverage identified

## Constraints

- **Don't modify rules** - only validate and recommend
- **Consider real-world impact** - false positives vs missed escalations
- **Flag overly aggressive rules** - too many alerts = alert fatigue
- **Flag overly lenient rules** - critical issues slipping through

## Key Files

| File                       | Purpose                          |
| -------------------------- | -------------------------------- |
| `docs/escalation-rules.md` | Rule definitions                 |
| `src/escalation_engine.py` | Rule evaluation code (if exists) |
| `.env.example`             | Required credentials             |

## Common Pitfalls

- **Not testing boundaries**: Exact threshold values need explicit handling
- **Assuming exclusive rules**: Multiple rules can match, need priority
- **Ignoring missing fields**: Null/undefined fields break comparisons
- **Hardcoded values**: Thresholds should be configurable

## Integration with Marcus

This skill is typically invoked when:

- Escalation rules modified
- New escalation actions added
- Rule engine code changes
- Investigating escalation failures

## If Blocked

If you cannot proceed:

1. State which rules you're validating
2. Explain what's unclear about the rule logic
3. Provide partial validation results
4. Request clarification on rule priority or behavior

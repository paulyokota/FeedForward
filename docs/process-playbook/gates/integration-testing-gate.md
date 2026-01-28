# Integration Testing Gate: Data Flow Verification

> For features with cross-component data flow, unit tests in isolation are not sufficient.

This is a PROCESS GATE for features where data passes through multiple components.

---

## The Rule

**Features with data flow across components require an integration test that verifies the full path.**

Unit tests mock boundaries. Integration tests verify real connections. Some bugs only surface when components are wired together.

---

## Why This Gate Exists

| Unit Tests                       | Integration Tests                    |
| -------------------------------- | ------------------------------------ |
| Test each component in isolation | Test components working together     |
| Mock external dependencies       | Use real (or realistic) dependencies |
| Fast, deterministic              | Slower, more realistic               |
| Can miss wiring bugs             | Catch wiring bugs                    |

**Unit tests tell you each piece works. Integration tests tell you the pieces work together.**

This gate exists because we've merged PRs where:

- All unit tests passed
- Code review looked correct
- Parameter was defined but never wired through the full path
- Feature was effectively dead code despite "working" tests

### Case Study: Issue #144 Smart Digest

The `full_conversation` parameter was:

1. Added to the function signature
2. Passed correctly in unit tests (mocked)
3. Never actually wired in `pipeline.py`
4. Feature was dead code for weeks

An integration test that ran the actual pipeline with real (or fixture) data would have caught this immediately.

---

## When Integration Tests Are Required

| Feature Type                | Why Integration Test Needed                                |
| --------------------------- | ---------------------------------------------------------- |
| **New pipeline parameter**  | Verify parameter flows from entry point to usage           |
| **Cross-service data flow** | Verify data transforms correctly across boundaries         |
| **Feature flag rollout**    | Verify flag actually enables/disables behavior end-to-end  |
| **New field in data model** | Verify field is populated, stored, and retrieved correctly |
| **API to database flow**    | Verify request reaches storage and retrieval works         |

### Not Required For

- Isolated utility functions
- Pure transformations with no dependencies
- Configuration changes (unless behavior-changing)
- Documentation or comment changes

---

## Integration Test Checklist

Before claiming a cross-component feature is complete:

```markdown
### Integration Test Evidence

- [ ] Test exercises the full data path (entry point to final usage)
- [ ] Test uses realistic fixtures (not just happy-path mocks)
- [ ] Test verifies the new parameter/field is actually used (not just passed)
- [ ] Test would have failed if the wiring was missing
```

---

## Verification Pattern

For any new parameter or data field flowing through multiple components:

```python
# GOOD: Integration test that verifies wiring
def test_full_conversation_flows_through_pipeline():
    """Verify full_conversation reaches theme extraction."""
    # Arrange: Create conversation with known content
    conversation = create_test_conversation(body="unique marker text")

    # Act: Run actual pipeline (not mocked)
    result = run_pipeline(conversation)

    # Assert: Verify the unique content was processed
    # (This fails if parameter was never wired)
    assert "unique marker" in result.diagnostic_summary

# BAD: Unit test that doesn't catch wiring bugs
def test_extract_themes_uses_full_conversation():
    """This passes even if wiring is broken."""
    # Mock everything - doesn't test real integration
    with mock.patch("src.pipeline.extract_themes") as mock_extract:
        mock_extract.return_value = Mock(...)
        # This test passes even if extract_themes is never called!
```

---

## For Tech Lead (Claude Code)

### At Feature Planning Time

When a task involves data flowing through multiple components:

1. **Identify the data path**: Entry point -> Processing -> Storage/Output
2. **Add integration test to task list**: Not optional
3. **Define what the test should verify**: Specific assertion that fails if wiring is broken

### Pre-Merge Checkpoint

```
[ ] Does this feature involve cross-component data flow?
    If YES:
    [ ] Integration test exists that exercises full path?
    [ ] Test would fail if wiring was missing?
    [ ] Test uses realistic data (not just mocks)?
```

---

## Architect Checklist Addition

When designing features with cross-component data flow, add to architect output:

```markdown
### Integration Test Requirement

Data path: [entry point] -> [component A] -> [component B] -> [output]

Required test: Verify [specific parameter/field] flows from [entry] to [output]

Test assertion: [What to assert that would fail if wiring is broken]
```

---

## Common Wiring Bugs This Catches

| Bug Pattern                                 | How Integration Test Catches It                              |
| ------------------------------------------- | ------------------------------------------------------------ |
| Parameter defined but never passed          | Test fails when expected value is missing                    |
| Parameter passed but not used               | Test fails when output doesn't reflect input                 |
| Feature flag checked but behavior unchanged | Test fails when flag=True produces same result as flag=False |
| Field stored but not retrieved              | Test fails when retrieved data is missing field              |
| Default value overwrites passed value       | Test fails when unique input becomes generic output          |

---

## Summary

| Checkpoint                            | Action                                |
| ------------------------------------- | ------------------------------------- |
| Feature crosses component boundaries  | Require integration test              |
| Integration test missing              | Block PR, add test first              |
| Test only uses mocks                  | Flag: may miss wiring bugs            |
| Test would pass even if wiring broken | Rewrite test with specific assertions |

**The rule: If data flows through multiple components, test the full path.**

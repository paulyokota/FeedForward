---
name: testing
identity: ./IDENTITY.md
triggers:
  keywords:
    - test
    - testing
    - pytest
    - fixture
    - coverage
    - edge case
    - qa
    - validation
  file_patterns:
    - tests/**/*.py
    - data/*_fixtures.json
dependencies:
  skills:
    - learning-loop
  tools:
    - Bash
    - Read
    - Write
---

# Testing Skill

Write comprehensive tests that ensure code correctness, cover edge cases, and prevent regressions.

## Workflow

### Phase 1: Understand What to Test

1. **Review Production Code**
   - What does this code do?
   - What are the inputs and outputs?
   - What can go wrong?
   - What are the boundary conditions?

2. **Load Context**
   - Read `docs/process-playbook/gates/test-gate.md`
   - Review existing test patterns in `tests/`
   - Check for fixture files in `data/`

3. **Identify Test Scenarios**
   - Happy path (normal operation)
   - Edge cases (empty, null, boundaries)
   - Error conditions (invalid input, failures)
   - Integration points (external services, database)

### Phase 2: Design Tests

1. **Choose Test Type**
   - **Unit tests**: Single function/method, mocked dependencies
   - **Integration tests**: Multiple components, real interactions
   - **Fixture-based tests**: Predefined test data

2. **Plan Test Cases**
   - Normal inputs → expected outputs
   - Edge cases → graceful handling
   - Invalid inputs → appropriate errors
   - Boundary values → correct behavior

3. **Design Fixtures**
   - Realistic test data
   - Covers various scenarios
   - Reusable across tests
   - Version controlled

### Phase 3: Implement Tests

1. **Follow Existing Patterns**
   - Review similar tests in `tests/`
   - Use consistent naming: `test_<function>_<scenario>_<expected>`
   - Group related tests in classes

2. **Write Test Structure**

   ```python
   def test_function_scenario_expected():
       # Arrange - set up test data and mocks
       input_data = {...}
       mock_service.return_value = expected_response

       # Act - execute the code under test
       result = function_under_test(input_data)

       # Assert - verify the result
       assert result == expected_output
       assert mock_service.called_once_with(...)
   ```

3. **Mock External Dependencies**
   - Mock Intercom API calls
   - Mock OpenAI LLM calls
   - Mock database operations (for unit tests)
   - Use `unittest.mock.patch`

4. **Use pytest Fixtures**

   ```python
   @pytest.fixture
   def sample_conversation():
       return {
           "id": "123",
           "content": "test message"
       }

   def test_with_fixture(sample_conversation):
       result = process_conversation(sample_conversation)
       assert result is not None
   ```

### Phase 4: Cover Edge Cases

1. **Boundary Conditions**
   - Empty lists/strings
   - Single item collections
   - Maximum values
   - Zero and negative numbers

2. **Null/None Handling**
   - Optional parameters
   - Missing data fields
   - Null returns from external services

3. **Error Conditions**
   - Invalid input types
   - Malformed data
   - Network failures
   - Database errors

### Phase 5: Verify

1. **Run Tests**
   - `pytest tests/ -v` - all tests must pass
   - Run 3 times if checking for flaky tests
   - Check for warnings

2. **Review Coverage**
   - Are all code paths tested?
   - Are edge cases covered?
   - Are error handlers tested?

## Success Criteria

Before claiming completion:

- [ ] All new production code has corresponding tests
- [ ] Edge cases covered (empty input, invalid input, boundaries)
- [ ] Error conditions tested
- [ ] All tests pass: `pytest tests/ -v`
- [ ] No flaky tests (consistent results across runs)
- [ ] External services mocked appropriately
- [ ] Test names are descriptive
- [ ] Fixtures used for shared test data

## Constraints

- **DO NOT** modify production code (only `tests/` directory)
- **DO NOT** skip edge cases - they matter most
- **DO NOT** write tests that depend on external services without mocking
- **DO NOT** create flaky tests (time-dependent, order-dependent)
- **ALWAYS** ensure all tests pass before declaring done
- **ALWAYS** test behavior, not implementation details

## Key Files & Patterns

| File                             | Purpose                    |
| -------------------------------- | -------------------------- |
| `tests/test_pipeline.py`         | Pipeline integration tests |
| `tests/test_classifier.py`       | Classification tests       |
| `tests/test_theme_extraction.py` | Theme extraction tests     |
| `tests/test_story_tracking.py`   | Story tracking tests       |
| `data/theme_fixtures.json`       | Theme test fixtures        |
| `data/labeled_fixtures.json`     | Labeled test data          |

### Test Patterns

**Pattern 1: Mock External Services**

```python
from unittest.mock import patch, MagicMock

@patch('src.intercom_client.IntercomClient.fetch_conversations')
def test_pipeline_with_mock(mock_fetch):
    mock_fetch.return_value = [sample_conversation]

    result = run_pipeline()

    assert result.success
    mock_fetch.assert_called_once()
```

**Pattern 2: Pytest Fixtures**

```python
@pytest.fixture
def db_connection():
    conn = create_test_db()
    yield conn
    conn.close()

def test_with_db(db_connection):
    result = query_db(db_connection)
    assert len(result) > 0
```

**Pattern 3: Parameterized Tests**

```python
@pytest.mark.parametrize("input,expected", [
    ("", []),  # Empty
    ("single", ["single"]),  # Single item
    ("a,b,c", ["a", "b", "c"]),  # Multiple
])
def test_parse_list(input, expected):
    assert parse_list(input) == expected
```

## Common Pitfalls

- **Testing implementation details**: Test what the code does, not how it does it
- **External service dependencies**: Always mock Intercom, OpenAI, database for unit tests
- **Flaky tests**: Use fixed seeds, avoid time-dependent assertions
- **Missing edge cases**: Empty lists, None values, boundary conditions
- **Generic test names**: `test_function` tells nothing, `test_parse_empty_input_returns_empty_list` is clear

## If Blocked

If you cannot proceed:

1. State what you're stuck on
2. Explain what's not working (include test output)
3. Share what you've already tried
4. Provide production code context
5. Ask the Tech Lead for guidance

---
name: prompt-engineering
identity: ./IDENTITY.md
triggers:
  keywords:
    - prompt
    - classification
    - evaluator
    - theme
    - extraction
    - vocabulary
    - accuracy
    - fixture
  file_patterns:
    - src/classifier_stage1.py
    - src/classifier_stage2.py
    - src/theme_extractor.py
    - src/vocabulary.py
    - config/theme_vocabulary.json
    - docs/prompts.md
dependencies:
  skills:
    - functional-testing
    - learning-loop
  tools:
    - Bash
---

# Prompt Engineering Skill

Optimize LLM prompts for classification and theme extraction using data-driven validation.

## Workflow

### Phase 1: Establish Baseline

1. **Measure Current Performance**
   - Run functional test with current prompts
   - Record accuracy metrics by category
   - Capture sample outputs and edge cases
   - Document baseline in test evidence

2. **Understand Current Prompt**
   - Read prompt from `docs/prompts.md`
   - Review classification schema and output format
   - Check theme vocabulary in `config/theme_vocabulary.json`
   - Identify potential improvement areas

### Phase 2: Research & Design

1. **Load Required Context**
   - `docs/prompts.md` - Current prompt versions
   - `config/theme_vocabulary.json` - Theme definitions
   - `docs/process-playbook/gates/functional-testing-gate.md` - Testing requirements
   - Relevant classifier/extractor code

2. **Research Best Practices**
   - Review OpenAI prompt engineering guidelines
   - Check fixture files for failure patterns
   - Look for edge cases in test data

3. **Design Change**
   - Make ONE targeted change at a time
   - Document reasoning for the change
   - Predict expected impact

### Phase 3: Implement & Test

1. **Apply Change**
   - Update prompt in appropriate file
   - Maintain consistent format
   - Preserve schema structure

2. **Run Functional Test** (MANDATORY)
   - Execute full classification pipeline
   - Capture new accuracy metrics
   - Compare against baseline
   - Document in functional test evidence format

3. **Analyze Results**
   - Did accuracy improve/stay same/regress?
   - Were edge cases handled better?
   - Any new failure patterns introduced?

### Phase 4: Document

1. **Update Prompt Documentation**
   - Add entry to `docs/prompts.md` with version number
   - Include accuracy metrics (before/after)
   - Note what changed and why
   - Reference functional test evidence

2. **Invoke `/prompt-iteration` command** (if available)
   - Logs prompt version with metrics
   - Creates traceable history

## Success Criteria

Before claiming completion:

- [ ] Baseline accuracy measured before changes
- [ ] New accuracy measured after changes
- [ ] Accuracy improved or stayed same (never regressed)
- [ ] Functional test evidence captured (see functional-testing-gate.md)
- [ ] `docs/prompts.md` updated with new version
- [ ] One change at a time (no bundled modifications)
- [ ] Tests pass: `pytest tests/ -v`

## Constraints

- **DO NOT** change prompts without measuring before/after accuracy
- **DO NOT** skip functional testing (gate enforcement)
- **DO NOT** touch database code (`src/db/`) - Marcus's domain
- **DO NOT** touch API endpoints (`src/api/`) - Marcus's domain
- **DO NOT** touch frontend code (`frontend/`, `webapp/`) - Sophia's domain
- **ALWAYS** document prompt versions in `docs/prompts.md`
- **ALWAYS** make one change at a time for clear attribution

## Key Files

| File                           | Purpose                          |
| ------------------------------ | -------------------------------- |
| `src/classifier_stage1.py`     | Fast routing classifier          |
| `src/classifier_stage2.py`     | Refined analysis classifier      |
| `src/theme_extractor.py`       | Theme extraction with vocabulary |
| `config/theme_vocabulary.json` | Theme definitions and keywords   |
| `docs/prompts.md`              | Prompt version history           |
| `data/theme_fixtures.json`     | Test fixtures for accuracy       |
| `data/labeled_fixtures.json`   | Labeled test data                |

## Common Pitfalls

- **No baseline**: Always measure accuracy BEFORE making changes
- **Multiple changes**: Change one thing at a time to isolate impact
- **Skipping functional testing**: PR will be blocked without evidence
- **Not updating docs/prompts.md**: Prompt versions must be logged
- **Assuming "looks good"**: Measure, don't judge subjectively

## If Blocked

If you cannot proceed:

1. State what you're stuck on
2. Explain what's not working
3. Share what you've already tried
4. Provide baseline metrics if available
5. Ask the Tech Lead for guidance

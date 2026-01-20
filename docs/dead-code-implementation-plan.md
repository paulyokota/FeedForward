# Dead Code Implementation Plan (Corrected)

**Created**: January 20, 2026
**Based on**: 5-Personality Review of `docs/dead-code-inventory.md`
**Status**: Ready for Haiku Implementation

---

## Summary of Corrections from Review

The original inventory had critical flaws identified by the 5-personality review:

| Issue               | Original                           | Corrected                         |
| ------------------- | ---------------------------------- | --------------------------------- |
| **False Positives** | 9 modules marked for deletion      | 6 modules (3 removed - see below) |
| **Phase Order**     | Delete modules, then cleanup tests | Delete tests FIRST, then modules  |
| **Complexity**      | 5 phases                           | 2 phases                          |
| **Security Fix**    | Bundled with cleanup               | Separate PR (out of scope here)   |

### Modules REMOVED from Deletion List (False Positives)

These are **NOT dead code** - do NOT delete:

| Module                          | Reason to Keep                                        |
| ------------------------------- | ----------------------------------------------------- |
| `src/classification_manager.py` | Imported by `tools/test_phase1_system.py:25`          |
| `src/classifier_v2.py`          | Imported by `scripts/evaluate_v2_classifier.py:21`    |
| `src/evidence_validator.py`     | Actively tested by `tests/test_evidence_validator.py` |

---

## Confirmed Safe to Delete (6 Modules)

| Module                            | Lines | Status                                    |
| --------------------------------- | ----- | ----------------------------------------- |
| `src/confidence_scorer.py`        | 411   | Self-testing main() only                  |
| `src/equivalence.py`              | 138   | Docstring examples only                   |
| `src/escalation.py`               | 373   | Stale test dependency (delete test first) |
| `src/help_article_extractor.py`   | 169   | Docstring examples only                   |
| `src/knowledge_aggregator.py`     | 83    | Self-testing main() only                  |
| `src/shortcut_story_extractor.py` | 180   | Docstring examples only                   |

**Total**: 1,354 lines to remove

---

## Implementation Plan (2 Phases)

### Phase 1: Test Cleanup (Run First)

Delete stale test files BEFORE deleting modules to avoid import errors.

```bash
# Step 1.1: Verify test file exists and check it references the module
grep -l "escalation" tests/*.py

# Step 1.2: Delete stale test file
rm tests/test_escalation.py

# Step 1.3: Verify test suite still passes
pytest tests/ -v --ignore=tests/test_escalation.py 2>/dev/null || echo "Check for other test deps"
```

**Validation**: After Phase 1, `pytest tests/ -v` should pass with no import errors.

---

### Phase 2: Module Deletion (Run Second)

Delete confirmed dead modules in a single operation.

```bash
# Step 2.1: Delete all confirmed dead modules
rm src/confidence_scorer.py
rm src/equivalence.py
rm src/escalation.py
rm src/help_article_extractor.py
rm src/knowledge_aggregator.py
rm src/shortcut_story_extractor.py

# Step 2.2: Verify no broken imports
python -c "import src.pipeline" && echo "Pipeline OK"
python -c "import src.api.main" && echo "API OK"

# Step 2.3: Run full test suite
pytest tests/ -v
```

**Validation**: All imports succeed, all tests pass.

---

## Commit Message Template

```
feat(cleanup): Remove 6 dead code modules (~1,354 lines)

Modules deleted:
- src/confidence_scorer.py (411 lines) - self-testing only
- src/equivalence.py (138 lines) - docstring examples only
- src/escalation.py (373 lines) - no active consumers
- src/help_article_extractor.py (169 lines) - docstring examples only
- src/knowledge_aggregator.py (83 lines) - self-testing only
- src/shortcut_story_extractor.py (180 lines) - docstring examples only

Also removed:
- tests/test_escalation.py (stale test for deleted module)

Verification:
- grep -r "import.*<module>" src/ tests/ tools/ scripts/ - no active imports
- pytest tests/ -v - all tests pass
- python -c "import src.pipeline" - no import errors

NOT deleted (false positives from original analysis):
- src/classification_manager.py - used by tools/
- src/classifier_v2.py - used by scripts/
- src/evidence_validator.py - actively tested

Refs: docs/dead-code-inventory.md, docs/dead-code-inventory-review-feedback.md

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Progress Tracking

| Phase                    | Status     | Completed Date | PR  |
| ------------------------ | ---------- | -------------- | --- |
| Phase 1: Test Cleanup    | ⬜ PENDING | —              | —   |
| Phase 2: Module Deletion | ⬜ PENDING | —              | —   |

---

## Out of Scope (Separate PRs)

These items from the original inventory should be handled separately:

1. **Security Fix** (`/admin/reindex` authentication) - Create separate issue/PR
2. **Silent Exception Handlers** - Create separate issue for logging improvements
3. **Duplicate Function Consolidation** - Only do if pattern repeats elsewhere
4. **Unused Exception Classes** - Low priority, defer

---

## Pre-Implementation Checklist

Before starting, verify:

- [ ] On correct branch (`claude/inventory-dead-code-u8acE` or new cleanup branch)
- [ ] Working directory clean (`git status`)
- [ ] Tests pass before changes (`pytest tests/ -v`)
- [ ] No active work depends on these modules

---

## Post-Implementation Checklist

After completing both phases:

- [ ] All tests pass (`pytest tests/ -v`)
- [ ] No import errors (`python -c "import src.pipeline; import src.api.main"`)
- [ ] Commit uses template above
- [ ] Update `docs/dead-code-inventory.md` status to "COMPLETED"

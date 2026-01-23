# Uncommitted Changes - Need Decision

**Date**: 2026-01-23
**Branch**: main

## Uncommitted Code Changes

The following files have uncommitted modifications from a previous session:

```
modified:   config/codebase_domain_map.yaml
modified:   src/story_tracking/models/__init__.py
modified:   src/story_tracking/services/codebase_context_provider.py
modified:   src/story_tracking/services/domain_classifier.py
modified:   src/story_tracking/services/story_creation_service.py
```

**What these changes do**: Multi-repo codebase exploration for story creation (Issue #44)

- Added `suggested_repos` field to classification model
- Modified domain classifier to populate suggested_repos from domain map
- Updated codebase provider to explore ALL suggested repos (not just first)
- Added classification to theme_data flow

**Status**: UNTESTED - no tests written, no functional test evidence

## Uncommitted Documentation

```
Untracked files:
  docs/issues/github-issues-to-create.md
  docs/issues/story-creation-quality-issues.md
  reference/codex_feedback_123.md
```

**What these contain**: Analysis of 6 architectural issues from Codex review, GitHub issue templates

**Status**: Issues #122-127 already created in GitHub

## Session Summary - Story Quality Evaluation (2026-01-23)

**Goal**: Evaluate story quality (evidence grouping, implementation details, actionability)

**What was accomplished**:

- Evaluated evidence grouping: 1 BAD grouping (billing_credits mixed bug+info), 1 GOOD grouping (pinterest)
- Confirmed Issue #125: Classification not persisted to DB
- Confirmed Issue #123: Signature grouping can merge different issue types
- Documented 6 issues from Codex review (#122-127, created in GitHub)
- Identified technical learnings and process failures

**What was NOT accomplished**:

- Could not evaluate implementation details or actionability (need stories with code_context)
- Wasted 4 pipeline runs (73-76) due to not checking state first

**Process issues identified**:

- Need approval gates for high-risk operations (researched but not implemented)
- Need to check database state before running pipelines
- Need to understand system architecture before executing commands

## Decision Needed

What to do with these uncommitted changes?

**Option 1**: Commit as-is to main

- Fast, gets changes in
- Violates Test Gate (no tests)
- Violates Functional Testing Gate (no evidence)

**Option 2**: Discard code changes, keep docs

```bash
git restore config/ src/
git add docs/issues/ reference/
git commit -m "docs: Document story quality issues from Codex review"
```

**Option 3**: Create feature branch for proper review

```bash
git checkout -b feat/multi-repo-exploration
git add [files]
git commit
# Write tests, run functional tests, create PR
```

**Option 4**: Stash for later

```bash
git stash push -m "Multi-repo exploration + docs (untested)"
```

## Recommendation

Option 2 or 4. The code changes are untested and shouldn't be committed without following the proper gates. The documentation is valuable and should be committed separately.

---

_Created: 2026-01-23 - Session wrap-up_

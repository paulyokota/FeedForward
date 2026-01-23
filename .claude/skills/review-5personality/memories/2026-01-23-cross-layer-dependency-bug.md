# Cross-Layer Dependency Bug - PR #120 Post-Mortem

**Date**: 2026-01-23
**PR**: #120 (commit 558fded)
**Bug**: PM Review never runs for hybrid clustering despite call site existing

## The Bug

PM Review was supposed to run for hybrid clustering, but it never did. The code at `story_creation_service.py:643-672` calls PM review correctly, but the service was always `None`.

## Root Cause: Two-Layer Fix with One Layer Changed

The fix required changes at TWO layers:

1. **Call Site** (`story_creation_service.py:643`): Checks `if self.pm_review_enabled and self.pm_review_service:`
2. **Service Initialization** (`pipeline.py:754`): Creates `PMReviewService()` but ONLY for non-hybrid runs

PR #120 correctly added the call site logic but didn't update the initialization guard:

```python
# pipeline.py:754 - The bug location
if not hybrid_clustering_enabled and pm_review_enabled:  # <-- This excludes hybrid!
    pm_review_service = PMReviewService()
```

The call site looks correct in isolation. The initialization looks correct in isolation. But together, they create a silent failure:

- `pm_review_service` is `None` for hybrid runs
- Call site checks `if self.pm_review_service:` which is `False`
- Falls through to `pm_review_skipped += 1` with no visible error

## Why Review Missed It

1. **PR diff looked correct** - The new code at the call site was logically sound
2. **No execution trace** - Reviewers didn't trace backward to verify initialization
3. **Silent failure mode** - The skip counter increments, but there's no error or warning
4. **Isolation review** - Each file reviewed in isolation, not as an integrated system

## Detection Pattern

**When reviewing PRs that ADD code calling a service/dependency, ALWAYS verify:**

1. Where is the dependency initialized?
2. Under what conditions is it initialized?
3. Does the new call site's conditions match the initialization conditions?

**Red flags to catch:**

- `if self.service:` guard (suggests service might be None)
- `if X_enabled and self.X_service:` (two conditions - both must be satisfied)
- Service passed via constructor/parameter (trace back to caller)
- Counter/metric for "skipped" operations (may hide misconfiguration)

## Specific FeedForward Pattern

In this codebase, `pipeline.py` initializes services and passes them to `StoryCreationService`. When modifying story creation to use a service:

1. Check `pipeline.py` where `StoryCreationService` is instantiated (~line 763)
2. Verify the service is created for ALL code paths that will use it
3. Look for conditional guards like `if not X_enabled` that might exclude your code path

**Files involved:**

- `src/api/routers/pipeline.py:754` - Service initialization
- `src/story_tracking/services/story_creation_service.py:643` - Call site

## Reviewer Action Items

### For Reginald (Correctness)

- Add "Dependency Initialization Verification" to checklist
- When code checks `if self.X:`, trace where X is set

### For Quinn (Quality)

- Silent skips may indicate misconfiguration, not intentional behavior
- Metrics that count "skipped" deserve extra scrutiny

### For All Reviewers

- Cross-file dependencies need explicit verification
- "Works in isolation" is not sufficient for integrated systems

## Prevention Checklist

Before approving PRs that add service calls:

- [ ] Located where the service is initialized
- [ ] Verified initialization happens for ALL code paths that call it
- [ ] Checked for conditional guards that might exclude the new call site
- [ ] Confirmed failure mode is visible (not silent skip)

---
name: PM Review Disabled in Hybrid Clustering
about: PM review service not initialized when HYBRID_CLUSTERING_ENABLED=true
title: "PM Review disabled in hybrid clustering mode"
labels: bug, priority-high, phase-story-grouping
assignees: ""
---

**Phase**: Story Grouping | **Priority**: high | **Type**: bug

## Problem

PM review service is not initialized when `HYBRID_CLUSTERING_ENABLED=true`, even though the story creation code expects it and comments indicate it should work. This removes the only quality gate that can split semantically similar but implementation-different conversations.

## Root Cause

```python
# src/api/routers/pipeline.py:754-755
# Only initialize PM review for signature-based path
if not hybrid_clustering_enabled and pm_review_enabled:
    pm_review_service = PMReviewService()
```

PM service is ONLY created when hybrid clustering is OFF, but the hybrid clustering path in `story_creation_service.py:640-673` checks for PM review and will skip it when `pm_review_service is None`.

## Impact

- Removes the only quality gate that can split semantically similar but implementation-different conversations
- Hybrid clusters with mixed root causes go straight to story creation without validation
- Comment on line 771 says "PM review works for both signature and hybrid clustering" but implementation contradicts this

## Tasks

- [ ] Initialize PMReviewService regardless of clustering mode in `pipeline.py:754-762`
- [ ] Verify PM review runs for both signature-based and hybrid clustering paths
- [ ] Add test case: hybrid clustering with PM_REVIEW_ENABLED=true should split mixed clusters

## Evidence

- `src/api/routers/pipeline.py:754-762` - conditional initialization
- `src/story_tracking/services/story_creation_service.py:644-673` - PM review gate that gets skipped
- `reference/codex_feedback_123.md:6-10`

**Fix Complexity**: Low - initialize PM service regardless of clustering mode

**Reference**: docs/issues/story-creation-quality-issues.md

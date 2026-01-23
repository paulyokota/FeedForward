• I traced the full UI pipeline → story creation path and focused on evidence grouping + “implementation details” risks. No code
  changes made.

  Findings

  - High: PM review is effectively disabled for hybrid clustering runs, even when PM_REVIEW_ENABLED=true. In
    _run_pm_review_and_story_creation, PMReviewService is only initialized when not hybrid_clustering_enabled, so the
    StoryCreationService constructor disables PM review due to a missing service. That removes the only guard that can split
    semantically similar-but-implementation-different clusters. See src/api/routers/pipeline.py#L751-L773 and the PM review gate in
    src/story_tracking/services/story_creation_service.py#L640-L673.
  - High: Hybrid clustering groups purely by embedding similarity + (action_type, direction) and ignores issue_signature,
    product_area, or component. That can merge distinct issues that are linguistically similar or share the same facet tuple,
    resulting in evidence bundles for “same cluster” that aren’t actually the same issue. Cluster IDs are also run‑local
    (emb_{index}_facet_{action}_{direction}), so evidence theme_signatures are not stable across runs. See clustering in src/
    services/hybrid_clustering_service.py#L257-L305 and evidence creation with cluster_id in src/story_tracking/services/
    story_creation_service.py#L600-L761.
  - Medium: Story “implementation details” and code exploration inputs are built from the first conversation in a group. If the
    first item is sparse or off‑topic, you can get empty/low‑signal descriptions and code exploration that misses the right files,
    even if other conversations have richer detail. See src/story_tracking/services/story_creation_service.py#L1743-L1781 and
    downstream usage in src/story_tracking/services/story_creation_service.py#L705-L729 and src/story_tracking/services/
    story_creation_service.py#L719-L739.
  - Medium: Dual‑format/codebase context is entirely gated by FEEDFORWARD_DUAL_FORMAT and defaults to false in the pipeline. When
    disabled, stories never include code context (and the simple v1 description doesn’t add implementation sections). This is a
    config‑driven path to “no implementation details.” See src/api/routers/pipeline.py#L747-L772 and src/story_tracking/services/
    story_creation_service.py#L725-L729.

  Open questions / assumptions

  - Is PM review expected to run for hybrid clustering in production? The inline comments say yes, but the initialization suggests
    otherwise; confirming intent would clarify whether the current behavior is a bug or deliberate.
  - Do you rely on theme_signatures in evidence for cross‑run aggregation? If so, the cluster ID strategy will fragment evidence
    across runs.

  If you want, I can map these findings to specific test cases (e.g., adversarial cluster mixing, missing user_intent) without
  changing code.


› sure


• I'm outlining specific test cases covering PM review disabled, cluster mixing, first-conversation bias, and dual-format off
  scenarios, focusing on expected issues without code changes, to meet the user's investigation request.

• Here’s a focused test plan mapping the findings to concrete cases. All are investigation-only: you can run them manually or as
  targeted test fixtures without changing code.

  1) PM review not running in hybrid mode

  - Setup: Enable hybrid clustering (HYBRID_CLUSTERING_ENABLED=true), set PM_REVIEW_ENABLED=true, run a pipeline with 1–2 clusters
    that clearly need splitting (e.g., same action_type/direction but different root causes).
  - Expected: PM review should split or reject some clusters; story creation should reflect pm_review_splits/pm_review_rejects.
  - What you’ll actually see (likely): pm_review_skipped increments and no split/reject, because PMReviewService isn’t initialized
    under hybrid mode (src/api/routers/pipeline.py#L751-L773), so the guard never runs.
  - Evidence to collect: pipeline logs showing pm_review_skipped in story_creation_service and absence of PM review logs.

  2) Hybrid clustering merges different issues

  - Setup: Craft conversations with similar language but different causes/implementation paths, same action_type + direction.
    Examples:
      - “Timeline not loading due to API 500” vs “Timeline not loading due to missing CSS bundle.”
      - “Search results missing pins” vs “Search results missing due to filters misapplied.”
  - Expected: Distinct clusters or PM review splits.
  - Risk/actual: Embedding similarity + identical (action_type, direction) can place them in the same cluster, creating one story
    and evidence bundle.
  - Evidence: cluster assignment in logs (Hybrid clustering produced N clusters) and story evidence containing mixed excerpts.
  - Where to inspect: src/services/hybrid_clustering_service.py#L257-L305 + story creation logs.

  3) Evidence “theme_signatures” are run‑local

  - Setup: Run pipeline twice with similar data; compare evidence bundles for similar issues.
  - Expected: A stable signature grouping across runs.
  - Risk/actual: Evidence theme_signatures for hybrid stories are emb_{n}_facet_{...} (run‑local), so evidence grouping becomes
    fragmented across runs.
  - Evidence: Inspect story_evidence.theme_signatures for two runs and confirm signature changes.

  4) First‑conversation bias causes thin stories

  - Setup: Create a cluster/group where the first conversation has sparse user_intent, empty symptoms, or missing excerpt, while
    later conversations are rich.
  - Expected: Story description should still include strong user intent/symptoms.
  - Risk/actual: _build_theme_data uses the first conversation for scalar fields; description and code exploration might be thin or
    missing. See src/story_tracking/services/story_creation_service.py#L1743-L1781.
  - Evidence: Generated story description lacks user intent/symptoms despite later conversations having them; code_context
    classification shows “no issue text available.”

  5) Dual‑format off → no implementation details

  - Setup: Run pipeline with FEEDFORWARD_DUAL_FORMAT=false (default) on a theme that should clearly map to code areas.
  - Expected: Story should include implementation context or code references.
  - Risk/actual: Simple v1 description only; no code_context stored. See src/api/routers/pipeline.py#L747-L772, src/story_tracking/
    services/story_creation_service.py#L725-L739.
  - Evidence: stories.code_context null; description lacks any implementation section.
# Slice: Milestone 8 - Embedding-Based Story Clustering

Source: GitHub milestone 8 (Embedding-Based Story Clustering).

Done means:

- All items below are checked complete.
- Required tests/lint/typecheck pass for the touched areas.
- Evidence for each item is recorded in `ralph/progress.txt`.

## Milestone 8 Issues (Choose One Per Slice)

### Phase 1: Foundations (highest priority)

- [x] #103 Fix run scoping: use pipeline_run_id instead of timestamp heuristics
  - Depends on: none
  - Blocks: #105, #106, #107, #108, #109, #110
  - **DONE**: PR #112 merged 2026-01-22
- [x] #89 Pipeline-critical tests for canonical flow
  - Depends on: none (but should follow #103 per T-004 priority)
  - Blocks: #108, #109
  - **DONE**: PR #113 merged 2026-01-22
- [x] #104 Theme extraction quality gates + error propagation to UI
  - Depends on: #103, #89
  - Blocks: #110
  - **DONE**: PR #114 merged 2026-01-22

### Phase 2: Infrastructure (depends on Phase 1)

- [x] #105 Data model: conversation_embeddings and conversation_facet tables
  - Depends on: #103
  - Blocks: #106, #107, #108, #109, #110
  - **DONE**: PR #115 merged 2026-01-22
- [x] #106 Pipeline step: embedding generation for conversations
  - Depends on: #105, #103
  - Blocks: #107, #108, #109, #110
  - **DONE**: PR #116 merged 2026-01-22
- [x] #107 Pipeline step: facet extraction for conversations
  - Depends on: #105, #103
  - Blocks: #108, #109, #110
  - **DONE**: PR #117 merged 2026-01-22

### Phase 3: Integration (depends on Phase 2)

- [ ] #108 Hybrid clustering algorithm: embeddings + facet sub-grouping
  - Depends on: #103, #105, #106, #107, #89
  - Blocks: #109, #110
- [ ] #109 Story creation: integrate hybrid cluster output
  - Depends on: #103, #108, #89, #104
  - Blocks: #110
- [ ] #110 Integration testing: hybrid clustering pipeline validation
  - Depends on: #103, #104, #105, #106, #107, #108, #109, #89
  - Blocks: none

## Current Slice (Single Issue)

- [ ] #108 Hybrid clustering algorithm: embeddings + facet sub-grouping

## Notes

- Ordering and Phase 1 priorities reflect T-004 convergence notes in `docs/agent-conversation.md`.
- T-006 (hybrid clustering) recommends sequencing after T-004 fixes before replacing signature grouping.
- T-005 is an open execution-planning topic; no additional sequencing constraints beyond T-004 are recorded yet.

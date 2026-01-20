# FeedForward Roadmap Proposal

**Date**: 2026-01-20
**Author**: Claude (PM/Tech Lead perspective)
**Status**: Proposal for Review

---

## Executive Summary

FeedForward has made significant progress building the infrastructure for LLM-powered support conversation analysis. However, **the core value proposition remains incomplete**: we can identify patterns in conversations, but we're not yet providing the "head start on implementation" that makes stories truly actionable.

This roadmap prioritizes **closing the implementation context gap** while stabilizing the foundation for production use.

---

## Product Goal Alignment

### What FeedForward Should Deliver

> **Identify actionable opportunities and provide a head start on implementation.**

Breaking this down:

| Component      | Current State                             | Gap                                             |
| -------------- | ----------------------------------------- | ----------------------------------------------- |
| **Identify**   | Classification + theme extraction working | Theme canonicalization creates duplicates (#36) |
| **Actionable** | Stories created with evidence             | Evidence workflow incomplete (#55)              |
| **Head Start** | Domain classifier exists                  | Not wired into story creation (#44, #46, #56)   |

### The Critical Missing Piece

Today, FeedForward creates stories like:

```markdown
### Relevant Files:

- tailwind_communities/ module - Community management code
- API endpoints serving content
```

But engineers need:

```markdown
### Implementation Context:

- File: aero/packages/tailwindapp/app/communities/page.tsx:142-167
- Snippet: `const { data } = useQuery(TRIBES_CONTENT_QUERY, {...})`
- Investigation query: SELECT \* FROM tribe_content_documents WHERE ...
```

**The domain classifier and codebase context provider exist but aren't used.** This is the highest-leverage work to deliver on the product promise.

---

## Current State Assessment

### What's Built and Working

| Component               | Status           | Notes                                                |
| ----------------------- | ---------------- | ---------------------------------------------------- |
| Intercom pipeline       | Production-ready | Quality filtering, theme extraction                  |
| Coda integration        | 90% complete     | 4,682 conversations loaded; coda_page adapter broken |
| Webapp board view       | Production-ready | Drag-drop, status management                         |
| Story detail page       | Production-ready | Evidence display, edit mode                          |
| Bidirectional sync      | Production-ready | Shortcut push/pull/webhook                           |
| Vector search           | 80% complete     | pgvector working; coda_page source broken            |
| Accept/reject endpoints | Merged           | PR #57, #60 complete                                 |
| Domain classifier       | Built, not wired | 37 tests passing, `NotImplementedError` stubs        |

### Active Bugs and Blockers

| Issue                  | Impact                           | Blocking                     |
| ---------------------- | -------------------------------- | ---------------------------- |
| #62: coda_page adapter | Vector search missing Coda pages | Evidence suggestions         |
| #46: repo sync stubs   | Code pointers unreliable         | Story implementation context |

### Backlog Summary

- **17 open issues** total
- **2 bugs** (#62, #35)
- **12 enhancements** (core features)
- **3 deferred** (#6, #7, #8 - MCP integrations awaiting tokens)

---

## Proposed Roadmap

### Phase 1: Stabilize Foundation (Week 1)

**Goal**: Fix critical bugs that block core features.

| Issue | Title                           | Effort | Impact | Why Now                           |
| ----- | ------------------------------- | ------ | ------ | --------------------------------- |
| #62   | coda_page adapter column error  | S      | High   | Blocks vector search completeness |
| -     | Add monitoring/health endpoints | M      | Medium | Production observability          |
| -     | Error handling audit            | M      | Medium | Production reliability            |

**Rationale**: Vector search is a differentiator (semantic evidence suggestions), but it's incomplete without Coda pages. The other 1,271 Coda pages represent rich research context that's currently invisible to the search system.

**Success Criteria**:

- `scripts/run_initial_embeddings.py` completes without errors
- All three source types (coda_page, coda_theme, intercom) embedding successfully
- P95 search latency < 500ms

---

### Phase 2: Close the Implementation Context Loop (Weeks 2-3)

**Goal**: Make every story include specific code pointers and investigation starting points.

| Issue | Title                                       | Effort | Impact   | Why Now                      |
| ----- | ------------------------------------------- | ------ | -------- | ---------------------------- |
| #46   | Implement repo sync + static fallback       | M      | High     | Foundation for code pointers |
| #44   | Wire classifier into story creation         | M      | Critical | Core value prop              |
| #56   | Story detail implementation context section | S      | High     | UI to display code context   |

**Rationale**: This is **the most important phase**. The domain classifier already works (37 tests passing) but returns `NotImplementedError` for the methods that would make it useful. The gap between "we have classification" and "stories include code context" is where the product value lives.

**Implementation Order**:

1. **#46 first**: Can't wire classifier without reliable code pointers
2. **#44 second**: Wire the full flow
3. **#56 third**: Display what we compute

**Success Criteria**:

- ≥80% of new stories include at least one code-area pointer
- Code-area enrichment adds <2s to story creation
- Story detail page shows "Implementation Context" section

---

### Phase 3: Complete Evidence Workflow (Week 4)

**Goal**: Let PMs curate evidence with persist/audit trail.

| Issue | Title                                          | Effort | Impact | Why Now                 |
| ----- | ---------------------------------------------- | ------ | ------ | ----------------------- |
| #55   | Accept/reject workflow (state machine + audit) | M      | High   | Closes PM feedback loop |
| #51   | Verify pgvector setup + run initial embeddings | S      | Medium | Validates Phase 1       |

**Rationale**: The accept/reject endpoints exist (PR #57), but the UI doesn't show status or let PMs make decisions that persist. Without this, suggested evidence is "fire and forget" - the system can't learn from PM judgment.

**State Machine**:

```
suggested → accepted
suggested → rejected
accepted ↔ rejected (with audit)
```

**Success Criteria**:

- Evidence items show status badge (suggested/accepted/rejected)
- Decisions persist and reload
- Audit trail captures who/when

---

### Phase 4: PM UX Improvements (Week 5)

**Goal**: PMs can control and monitor the pipeline from the webapp.

| Issue | Title                                   | Effort | Impact | Why Now                           |
| ----- | --------------------------------------- | ------ | ------ | --------------------------------- |
| #53   | Webapp pipeline control page            | M      | High   | Replace Streamlit dependency      |
| #54   | Run summary: new stories after pipeline | S      | Medium | Immediate visibility into results |

**Rationale**: PMs currently need Streamlit to run pipelines. The webapp is the preferred interface. Adding pipeline control makes the webapp self-sufficient.

**Scope for #53**:

- Start/stop pipeline runs
- Configure: days, max conversations, dry_run, concurrency
- Status polling with progress
- Run history

**Success Criteria**:

- PM can trigger pipeline run from webapp
- PM can see progress in real-time
- PM can see list of new stories created by run

---

### Phase 5: Quality Improvements (Week 6)

**Goal**: Improve theme quality and output formats.

| Issue | Title                            | Effort | Impact | Why Now                |
| ----- | -------------------------------- | ------ | ------ | ---------------------- |
| #36   | Theme signature canonicalization | M      | High   | Reduces duplicates     |
| #37   | Dual-format story output         | M      | Medium | AI agent compatibility |

**Rationale**: Theme canonicalization (#36) directly impacts aggregation quality. The same bug reported by 3 customers becomes 3 separate themes instead of 1 with count=3. This reduces signal strength and may prevent threshold-based ticket creation.

Dual-format output (#37) is a "nice to have" for AI coding agent compatibility, but lower priority than getting the basics right.

**Success Criteria**:

- Semantically similar issues consolidate to single signature
- ≥70% reduction in near-duplicate themes
- Stories include AI-facing section (if #37 pursued)

---

### Phase 6: Optimization and Scale (Future)

**Goal**: Improve search quality and reduce costs.

| Issue | Title                                    | Effort | Impact | Priority      |
| ----- | ---------------------------------------- | ------ | ------ | ------------- |
| #47   | Vector search for implementation context | M      | Medium | After Phase 2 |
| #40   | LLM query generation                     | L      | Medium | Optimization  |
| #22   | Theme-based story suggestion             | L      | Medium | Phase 6+      |

**Rationale**: These are valuable but not blocking production-readiness. They should wait until the core flow is solid.

---

### Deferred (Blocked or Low Priority)

| Issue      | Title                             | Reason                      |
| ---------- | --------------------------------- | --------------------------- |
| #6, #7, #8 | MCP integrations                  | Awaiting API tokens         |
| #14        | Intercom attachments              | Nice-to-have                |
| #35        | Pins not appearing in communities | External bug (Tailwind app) |

---

## Prioritization Framework

### Why This Order?

1. **Foundation first** (Phase 1): Can't build on broken infrastructure
2. **Core value prop** (Phase 2): Implementation context is the differentiator
3. **Feedback loop** (Phase 3): Let PMs curate = system learns
4. **UX consolidation** (Phase 4): One interface, not two
5. **Quality polish** (Phase 5): Reduce noise, improve signal

### What I'm NOT Prioritizing (and Why)

| Item                         | Why Deprioritized                             |
| ---------------------------- | --------------------------------------------- |
| Real-time webhooks           | Batch is sufficient for ~100/week volume      |
| Multi-language support       | English-only covers 95%+ of conversations     |
| Advanced analytics dashboard | Basic analytics exist; stories are the output |
| LLM query generation (#40)   | Optimization, not core functionality          |

---

## Risk Assessment

| Risk                        | Likelihood | Impact | Mitigation                                    |
| --------------------------- | ---------- | ------ | --------------------------------------------- |
| Codebase context unreliable | Medium     | High   | Static fallback (#46), bounded timeouts       |
| Vector search latency       | Low        | Medium | HNSW index, caching                           |
| Theme drift over time       | Medium     | Medium | Vocabulary feedback loop exists               |
| API cost growth             | Low        | Low    | gpt-4o-mini is cheap (~$1.35/month projected) |

---

## Success Metrics (Production-Ready)

### Must Have

- [ ] All three vector search sources working (coda_page, coda_theme, intercom)
- [ ] ≥80% of stories include implementation context (code pointers)
- [ ] Evidence accept/reject persists and reloads
- [ ] Pipeline runnable from webapp (no Streamlit dependency)
- [ ] P95 story creation latency <5s

### Should Have

- [ ] Theme deduplication reduces near-duplicates by ≥50%
- [ ] PM acceptance rate for suggested evidence ≥50%
- [ ] Run summary shows new stories created

### Nice to Have

- [ ] AI-facing story format
- [ ] LLM-powered search query generation
- [ ] Theme-based story suggestions

---

## Timeline Summary

| Phase                     | Duration  | Key Deliverable                |
| ------------------------- | --------- | ------------------------------ |
| 1: Foundation             | Week 1    | Vector search complete         |
| 2: Implementation Context | Weeks 2-3 | Stories include code pointers  |
| 3: Evidence Workflow      | Week 4    | Accept/reject with persistence |
| 4: PM UX                  | Week 5    | Webapp pipeline control        |
| 5: Quality                | Week 6    | Theme canonicalization         |

**Total: 6 weeks to production-ready**

---

## Open Questions for Stakeholder Input

1. **Shortcut integration depth**: Should we auto-create tickets for high-frequency themes, or always require PM approval?

2. **Code pointer sources**: Should we include third-party repos (e.g., Pinterest API client) or only internal repos?

3. **Evidence suggestion threshold**: What similarity score is "good enough" to suggest? (Currently 0.7)

4. **Pipeline scheduling**: Manual-only, or add scheduled runs (daily/weekly)?

---

## Appendix: Issue Dependency Graph

```
#62 (coda_page fix)
  └── #51 (verify pgvector setup)
        └── #47 (vector search for impl context) [optional]

#46 (repo sync + static fallback)
  └── #44 (wire classifier into story creation)
        └── #56 (story detail impl context section)

#55 (accept/reject workflow)
  └── #50 (filter rejected evidence) [DONE in PR #60]

#53 (webapp pipeline control)
  └── #54 (run summary)

#36 (theme canonicalization)
  └── #37 (dual-format output) [optional]
```

---

_This roadmap prioritizes shipping the core value proposition (actionable opportunities with implementation head start) over feature breadth. The goal is a production-ready tool that demonstrably helps PMs and engineers, not a feature-complete tool that's 80% done everywhere._

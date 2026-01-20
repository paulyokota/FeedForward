# Proposed Roadmap (Jan 20, Codex)

## Role Lens

Former principal developer turned PM: prioritize outcomes that unblock production, protect reliability, and deliver implementation-ready outputs without forcing PMs to context switch.

## Product Goal

FeedForward identifies actionable opportunities and provides a clear head start on implementation.

## Tactical Goal

Reach production-ready stability with a coherent PM experience in the webapp.

## Current State Summary (from docs + backlog)

- Core pipeline exists (classification → theme extraction → aggregation).
- Story grouping architecture is in progress; PM review loop exists but needs UX consolidation.
- Vector search + evidence suggestions exist but accept/reject workflow is incomplete.
- Code-area pointers infrastructure exists but not wired (DomainClassifier + CodebaseContextProvider).
- Streamlit is still the control surface; webapp lacks pipeline control.

## Roadmap Principles

1. **Single control surface**: PMs operate in one place (webapp).
2. **Evidence + code context**: each story should reduce PM/eng effort.
3. **Reliability before scale**: make pointer generation and evidence decisions trustworthy.
4. **Close the loop**: PM actions should persist, not be ephemeral.

## Roadmap (Phased)

### Phase 1 — Webapp Production Spine (2–3 weeks)

**Goal**: PMs can run the pipeline, see results, and triage without leaving the webapp.

**Why now**: This creates a production-grade control surface and removes Streamlit dependency.

**Work items (backlog mapping)**:

- Webapp pipeline control + graceful stop (#53)
- Run summary: new stories after pipeline run (#54)
- Suggested evidence accept/reject workflow (#55)

**Outcome**:
- PMs can run a pipeline, see what was produced, and take action.
- Evidence decisions persist and are measurable.

### Phase 2 — Implementation Context on Stories (2–3 weeks)

**Goal**: every story includes relevant evidence + code pointers.

**Why now**: This is the core promise (“head start on implementation”).

**Work items**:

- Wire classification-guided exploration into story creation (#44)
- Implement repo sync + static codebase fallback (#46)
- Story detail implementation context section (UI) (#56)

**Ordering**:
- #46 first (repo freshness + static fallback), then #44 (wire in), then #56 (display).

**Outcome**:
- ≥80% of stories show at least one code pointer.
- PM can copy a code pointer directly into engineering tickets.

### Phase 3 — Evidence Retrieval Automation (2–3 weeks)

**Goal**: add semantic evidence to stories at creation time using vector search.

**Why now**: builds on Phase 1 acceptance workflow and makes evidence suggestions proactive.

**Work items**:

- Use vector search to attach implementation context to stories (#47)
- Filter rejected evidence from suggestions (#50)
- Verify pgvector setup + run embedding pipeline (#51)

**Outcome**:
- Evidence suggestions become high quality and persistent.
- Acceptance rate can be tracked and improved.

### Phase 4 — Cleanup and De-risk (1–2 weeks)

**Goal**: remove legacy paths and reduce operational risk.

**Work items**:

- Streamlit deprecation (doc updates + removal of entry points)
- Resolve open bug (#35) if still valid
- Confirm enhancement backlog alignment (#36, #37, #40, #14)

**Outcome**:
- Single UX surface, fewer operational paths, stable runbook.

## Risk Notes and Mitigations

- **Pipeline stop semantics**: implement graceful stop first; avoid hard kill until state machine is robust.
- **Code pointer reliability**: enforce repo sync and static fallback prior to wiring.
- **Evidence noise**: use acceptance rates and rejected filtering (#50) to tune.

## Success Metrics

- ≥80% of new stories include ≥1 code-area pointer.
- Evidence acceptance rate ≥50% within 2 weeks of Phase 1.
- Pipeline status P95 page load < 2s.

## Dependencies & Sequencing Rationale

- Phase 1 enables Phase 3 (accept/reject workflow + data persistence).
- Phase 2 relies on Phase 1 for UI placement and on #46 for reliable data.
- Phase 3 depends on Phase 1 for feedback and Phase 2 for story context framing.

## Optional/Deferred Items (Not on Critical Path)

- MCP integrations (#6–#8) remain deferred until operational need emerges.
- Future story suggestion enhancements (#22) once core UX is stable.

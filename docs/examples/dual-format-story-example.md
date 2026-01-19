# Dual-Format Story Output Example

**Source Theme**: `community_pins_not_appearing_in_yours_tab`
**Generated**: 2026-01-15 (Mock Example)

---

## SECTION 1: Human-Facing Story

# Story: Fix Community Pins Not Appearing in Yours Tab

## User Story

As a **Tailwind user scheduling pins with community assignments**
I want **my published pins to appear in the Communities "Yours" tab**
So that **I can verify my community contributions and don't need to manually re-add pins**

## Context

- **Product Area**: Communities
- **Component**: tailwind_communities
- **User Journey Step**: Pin Scheduler → Tailwind Communities → Yours Tab Display
- **Dependencies**: Pinterest API integration, tribe_content_documents table
- **Related Conversations**: 3 customer reports (Dec 24, 2025 - Jan 12, 2026)

## Acceptance Criteria

- [ ] **Given** a pin is scheduled with a community assignment **when** the pin publishes successfully to Pinterest **then** the pin appears in the Communities "Yours" tab within 5 minutes
- [ ] **Given** a tribe_content_document record exists for a submission **when** the user views the "Yours" tab **then** the corresponding pin is displayed
- [ ] **Given** a pin fails to appear **when** the user checks the database **then** the sync state should indicate the error condition
- [ ] [Observability] Logging captures publish-to-visibility timing

## Symptoms (Customer Reported)

- Pins scheduled with community assignment
- Pins publish successfully to Pinterest ✓
- Pins do not appear in Communities 'Yours' tab ✗
- DB records (tribe_content_documents) exist for submissions
- Issue affects both Original Publisher and new Pin Scheduler
- Started around November 2025

## Root Cause Hypothesis

Synchronization issue between pin publishing and community visibility - backend records exist but UI doesn't reflect them. The data layer is correctly recording community assignments, but the display/retrieval layer is not surfacing them to users.

## Technical Notes

- **Target Components**: `tailwind_communities` module, tribe content retrieval APIs
- **Known Constraints**: DB records exist - issue is in retrieval/display layer
- **Testing Expectations**: Integration test covering publish → visibility flow
- **Vertical Slice**: Backend retrieval → Frontend display

## INVEST Check

- [x] **Independent**: Can be fixed without other stories
- [x] **Negotiable**: Implementation approach flexible
- [x] **Valuable**: Affects paying customers, causes manual workarounds
- [x] **Estimable**: Scoped to retrieval layer
- [ ] **Small**: May require investigation
- [x] **Testable**: Clear symptom/fix criteria

## Sample Customer Messages

> "My pins are not being posted in the communities. Even after they are published on Pinterest. The Pins I add to Communities are not showing up in the Communities even after they are published..."

> "I would like to ask you to check my account and clarify why my pins published via you have not been appearing in my tribes/communities for two months..."

> "The pins are published but aren't in the yours tab"

## Suggested Investigation

1. Review `tailwind_communities` code for issues matching symptoms
2. Check logs for errors in Pin Scheduler → Tailwind Communities → Yours Tab Display flow
3. Verify API responses and error handling in community content retrieval
4. Compare `tribe_content_documents` records with what's displayed in the UI
5. Check if there's a timing issue between when pins publish and when community visibility is updated

---

## SECTION 2: AI Agent Task Specification

# Agent Task: Fix Community Pin Visibility in Yours Tab

## Role & Context

You are a **senior backend engineer** working in the Tailwind codebase.
Follow project conventions in `CLAUDE.md` and established patterns.

**Repository**: tailwind-app
**Task Type**: bug-fix
**Related Story**: See Human-Facing Section above
**Priority**: High (3 customer reports, ongoing for 2+ months)

## Goal (Single Responsibility)

Ensure that pins scheduled with community assignments appear in the Communities "Yours" tab after publishing to Pinterest. The data is being written correctly to `tribe_content_documents` - the fix is in the retrieval/display layer.

## Context & Architecture

### Relevant Files:

- `tailwind_communities/` module - Community management code
- API endpoints serving the "Yours" tab content
- Frontend component rendering Yours tab (if changes needed)

### Architecture Notes:

- Pin publishing creates records in `tribe_content_documents`
- The Yours tab should query this table and display user's submissions
- DB records exist for affected users - confirms write path is working
- Issue is in read path: retrieval or rendering

### Business Rules:

- Pins assigned to communities during scheduling must appear in Yours tab after publish
- Visibility should occur within reasonable time of Pinterest publish (< 5 min)
- Both Original Publisher and new Pin Scheduler flows must work

### Related Systems:

- Pinterest API (publishing)
- PostgreSQL (tribe_content_documents table)
- Community APIs (retrieval)

## Instructions (Step-by-Step)

1. **Analyze** the Yours tab data retrieval code
   - Trace the query from API endpoint to database
   - Identify any filters that might exclude valid records
   - Check for timing/sync issues

2. **Reproduce** using test data
   - Create a test pin with community assignment
   - Verify DB record exists after publish
   - Confirm Yours tab does not show it

3. **Identify** the root cause
   - Compare working vs non-working cases
   - Check for state mismatches, missing joins, or cache issues

4. **Implement** the fix
   - Minimal change to correct retrieval logic
   - Maintain backward compatibility

5. **Add/Update Tests** covering:
   - Pin with community assignment → publishes → appears in Yours tab
   - Edge case: Multiple communities assigned
   - Regression: Existing Yours tab functionality unchanged

6. **Verify** by running:
   - Unit tests for modified code
   - Integration test for full publish → visibility flow
   - Manual verification with test account

## Success Criteria (Explicit & Observable)

- [ ] Pins with community assignments appear in Yours tab after publishing
- [ ] All existing tests pass (no regressions)
- [ ] New test covers the publish → visibility flow
- [ ] Query performance is not degraded (< 100ms for typical user)
- [ ] Fix applies to both Original Publisher and Pin Scheduler paths
- [ ] Verified manually with test data mimicking customer reports

## Guardrails & Constraints

### DO NOT:

- Modify the write path (tribe_content_documents insertion) - it's working correctly
- Change database schema without migration
- Deploy without testing in staging environment
- Make changes that affect other Communities tabs (Popular, Recent, etc.)

### ALWAYS:

- Write tests before/with the fix
- Preserve existing functionality
- Log key state transitions for debugging
- Consider multi-tenant isolation in queries

## Extended Thinking Guidance

This bug has persisted for 2+ months affecting multiple customers. Consider:

- **Why didn't previous investigations catch it?** - May be timing-dependent or data-dependent
- **What changed around November 2025?** - When customers first reported issues
- **Could there be multiple root causes?** - Some customers on Original Publisher, some on new Scheduler

Take time to understand the full data flow before jumping to a fix.

---

## Metadata

| Field               | Value                                       |
| ------------------- | ------------------------------------------- |
| **Issue Signature** | `community_pins_not_appearing_in_yours_tab` |
| **Occurrences**     | 3                                           |
| **First Seen**      | 2025-12-24                                  |
| **Last Seen**       | 2026-01-12                                  |
| **Generated By**    | FeedForward Pipeline v1.0                   |

---

_This is a mock example showing the proposed dual-format output from FeedForward._

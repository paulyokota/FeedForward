# Tailwind Codebase Understanding: Interactive Learning Loop

**STATUS: PHASE_7_COMPLETE ✅**
**REPOS_MAPPED: 15/15**
**CODEBASE_CONFIDENCE: 85%**
**USER_STORIES_ANALYZED: 5**
**FEEDBACK_TICKETS_GENERATED: 4**
**ITERATIONS: 1**

## CONTEXT & GOAL

You are building a **codebase understanding system** that enables Claude Code to transform user feedback into actionable engineering tickets. The system works by:

1. **Exploring the live Tailwind UI** via Playwright to understand user workflows
2. **Mapping codebase structure** across multiple repos (frontend, backend, services)
3. **Linking feedback to code** by connecting user pain points to specific technical areas
4. **Iteratively improving understanding** until reaching 85% confidence on ticket generation

**Key Insight**: You can't write good tickets without understanding:

- What the user actually experiences (UI navigation via Playwright)
- How that maps to code (backend services, API contracts, data models)
- Where to investigate bugs (which repo, which service, which component)
- What dependencies matter (cross-service impacts)

**YOUR GOAL**:

1. Map Tailwind codebase structure (repos, services, data flow)
2. Link user feedback patterns to technical areas
3. Build a "feedback → ticket translation" system with 85% confidence
4. Generate example tickets showing technical investigation paths
5. Create a decision tree for future feedback tickets

**SUCCESS METRIC**:

- 85% confidence: Given any user story, Claude Code can reliably point to:
  - Which repo(s) need investigation
  - Which services/components are likely involved
  - What technical questions to ask about the issue
  - How to break the ticket into engineering subtasks

---

## GROUND TRUTH REQUIREMENT

Your understanding must be grounded in **actual codebase and live product behavior**, not assumptions:

### Primary Sources (NON-NEGOTIABLE):

1. **Live Tailwind UI** (via Playwright): Actual user-facing flows
2. **GitHub repo exploration**: Actual code structure, not documentation
3. **API inspection** (DevTools): Actual request/response contracts
4. **Database schema** (if accessible): Actual data models

### What You MUST Do:

- Navigate the live Tailwind UI via Playwright to see actual workflows
- Inspect network requests (DevTools) to understand API contracts
- Explore GitHub repos to find where API endpoints are implemented
- Map data flow: UI → API request → backend service → database
- Test understanding: Verify assumptions against actual code

### What You MUST NOT Do:

- Assume architecture without checking code
- Invent service boundaries
- Skip exploring repos because they "seem complex"
- Generate tickets without linking to actual code locations
- Accept vague ticket descriptions (must include file paths, function names)

**If you cannot find something:** You MUST explicitly state what's missing and why, not proceed with uncertainty.

---

## PHASE 0: REPO STRUCTURE MAPPING

**Goal**: Understand the Tailwind codebase structure across all repos.

### Step 1: Identify All Repos

**Action**: List all repos in the Tailwind GitHub organization.

Questions to answer:

- How many repos total?
- What's the purpose of each? (frontend, backend, services, infrastructure)
- What's the primary tech stack? (languages, frameworks)
- Any monorepos?

**Expected output**:

```
Tailwind Repos:
├── tailwind-web (Frontend - Next.js/React)
├── tailwind-api (Backend - Node.js/Express or Python/FastAPI)
├── tailwind-mobile (Mobile - React Native or Flutter)
├── tailwind-workers (Services - background jobs, webhooks)
├── tailwind-infra (Infrastructure/DevOps)
└── [any others]
```

### Step 2: Map Frontend Architecture

**Action**: Explore `tailwind-web` repo structure.

For each major feature area (pins, boards, sharing, analytics):

- Where's the component code? (`components/`, `pages/`, `features/`)
- What are the main pages/routes?
- What state management? (Redux, Zustand, Context API, etc.)
- What UI library? (Material-UI, Tailwind CSS, custom components)

**Expected output**:

```
Frontend Structure:
├── pages/
│   ├── /pins         → PinList component → fetches from /api/pins
│   ├── /boards       → BoardList component → fetches from /api/boards
│   ├── /share        → ShareModal component → posts to /api/share
│   └── [...]
├── components/
│   ├── PinCard.jsx   → Renders individual pin
│   ├── BoardSelector → Dropdown for board selection
│   └── [...]
├── hooks/
│   ├── usePins.js    → Data fetching for pins
│   └── useBoards.js  → Data fetching for boards
└── [...]
```

### Step 3: Map Backend Architecture

**Action**: Explore backend repo (API, services, database).

For each major feature:

- What's the API endpoint? (`GET /api/pins`, `POST /api/pins/{id}/save`)
- Where's the endpoint implemented? (file path)
- What does it do? (business logic)
- What data does it access? (database tables, external APIs)

**Expected output**:

```
Backend API:
├── Routes (API endpoints)
│   ├── GET /api/pins
│   │   └── file: src/routes/pins.js
│   │   └── logic: fetch pins from DB, filter by user
│   │   └── database: pins table (id, url, user_id, created_at)
│   ├── POST /api/pins
│   │   └── file: src/routes/pins.js
│   │   └── logic: validate URL, create pin record
│   │   └── database: insert into pins table
│   ├── POST /api/boards/{id}/add-pin
│   │   └── file: src/routes/boards.js
│   │   └── logic: add pin to board
│   │   └── database: board_pins junction table
│   └── [...]
├── Services (business logic)
│   ├── PinService.js
│   ├── BoardService.js
│   ├── ShareService.js
│   └── [...]
├── Models (data access)
│   ├── Pin.js
│   ├── Board.js
│   └── [...]
└── Database
    ├── Tables: pins, boards, users, board_pins, etc.
    └── Schema: [define each table structure]
```

### Step 4: Map External Integrations

**Action**: Identify external services Tailwind depends on.

- Social media platforms (Pinterest API, Twitter, etc.)
- Analytics (Segment, Mixpanel, etc.)
- Payment/Billing (Stripe)
- Email/Notifications (SendGrid, etc.)
- Cloud storage (S3, etc.)

**Expected output**:

```
External Integrations:
├── Pinterest API
│   └── Used for: fetching pins, creating pins, managing boards
│   └── Error scenarios: rate limits, invalid credentials, API changes
├── Analytics
│   └── Used for: tracking user events
├── Stripe
│   └── Used for: subscription management
└── [...]
```

### Step 5: Generate Repo Mapping Document

**Create** `docs/codebase-map.md`:

```markdown
# Tailwind Codebase Map

## Repos at a Glance

[Table with repo name, purpose, tech stack, key files]

## Frontend Architecture

[Component hierarchy, routing, state management]

## Backend Architecture

[API endpoints, business logic, data models]

## Data Flow Examples

[Show how data flows for key features like "save a pin"]

## External Dependencies

[Third-party services and integration points]
```

**OUTPUT**:

- Repo structure clearly mapped
- All major feature areas identified
- API endpoints documented with file locations
- Data flow understood
- Confidence level: **LOW** (structure only, not detailed yet)

---

## PHASE 1: INTERACTIVE EXPLORATION VIA PLAYWRIGHT

**Goal**: Navigate the live Tailwind UI to understand actual user workflows.

### Step 1: Set Up Playwright

**Create** `scripts/explore_ui.js`:

```javascript
const { chromium } = require("playwright");

async function exploreTailwind() {
  const browser = await chromium.launch({
    headless: false, // See the UI as you navigate
  });
  const page = await browser.newPage();

  // Enable DevTools network inspection
  await page.context().newCDP().send("Network.enable");

  // Navigate to Tailwind
  await page.goto("https://app.tailwind.com");

  // Your exploration steps here

  await browser.close();
}

exploreTailwind();
```

### Step 2: Explore Key User Workflows

**For each major feature, document**:

1. **Current state**: What does the user see?
2. **User action**: What does the user do?
3. **UI response**: What happens on screen?
4. **Network request**: What API calls are made? (DevTools)
5. **Expected vs Actual**: Does it work as expected?
6. **Pain points**: Where do users get stuck?

**Example: Saving a Pin**

```
Workflow: User saves a pin to a board

Step 1: User navigates to /pins
  - Screen shows: List of available pins
  - UI elements: Pin cards with "Save" buttons
  - Network calls: GET /api/pins?limit=20&offset=0

Step 2: User clicks "Save" on a pin
  - Screen shows: Modal or dropdown with board selector
  - UI elements: List of user's boards
  - Network calls: GET /api/boards (to populate selector)

Step 3: User selects a board
  - Screen shows: Board selected, "Confirm" button
  - Network calls: None yet (local state change)

Step 4: User clicks "Confirm"
  - Screen shows: Loading spinner, then success message
  - Network calls: POST /api/boards/{board_id}/add-pin
    Request body: { pin_id, board_id }
    Response: { success: true, pin: {...} }
  - Database impact: Insert into board_pins table

Step 5: User navigates to board
  - Screen shows: Updated board with new pin
  - Network calls: GET /api/boards/{board_id}/pins
  - Verification: New pin appears in list
```

### Step 3: Test Error Scenarios

**For each workflow, test**:

- Invalid inputs (bad IDs, invalid data)
- Network failures (DevTools throttle connection)
- Rate limits (rapid repeated actions)
- Concurrent operations (multiple windows)
- Edge cases (empty lists, large datasets)

**Document**:

- How does the UI respond to errors?
- What error messages are shown?
- Can the user recover?
- Are errors logged for debugging?

### Step 4: Network Request Analysis

**For each API call, document**:

- URL pattern and HTTP method
- Request headers (auth, content-type)
- Request body (if POST/PUT)
- Response structure
- Error responses and status codes

**Example**:

```
POST /api/boards/{board_id}/add-pin

Request:
  Headers: Authorization: Bearer {token}
  Body: { "pin_id": "123", "position": 0 }

Response (200):
  {
    "success": true,
    "board": {
      "id": "board-123",
      "name": "Inspiration",
      "pins": [...]
    }
  }

Response (400):
  {
    "error": "Invalid pin_id",
    "code": "INVALID_INPUT"
  }

Response (403):
  {
    "error": "Not authorized to modify this board",
    "code": "FORBIDDEN"
  }
```

### Step 5: Generate Workflow Documentation

**Create** `docs/user-workflows.md`:

```markdown
# Tailwind User Workflows

## Workflow 1: Save a Pin

[Complete documented flow from Steps 1-4 above]

## Workflow 2: Create a Board

[Complete flow]

## Workflow 3: Share a Board

[Complete flow]

## Common Pain Points

[User friction observed during exploration]

## Error Scenarios

[Edge cases and error handling]

## API Contract Reference

[All endpoints used by this workflow]
```

**OUTPUT**:

- All major user workflows documented
- API contracts understood
- Pain points identified
- Error handling behaviors known
- Confidence level: **MEDIUM** (user-facing behavior clear, backend details pending)

---

## PHASE 2: CODE-TO-BEHAVIOR LINKING

**Goal**: Map UI flows to specific code locations.

### Step 1: Trace Frontend Code

**For each workflow from Phase 1, find**:

- Which page/component handles this? (file path)
- What state management? (Redux actions, hooks)
- What API calls? (fetch/axios calls)
- What event handlers? (click, submit, etc.)

**Example**:

```
Saving a pin (continued from Phase 1):

Frontend Code:
├── pages/pins.js
│   └── Renders PinList component
│   └── On mount: useEffect(() => fetchPins(), [])
│
├── components/PinCard.jsx
│   └── Renders individual pin
│   └── Has <SaveButton> child component
│
├── components/SaveButton.jsx
│   └── Renders "Save" button
│   └── onClick handler:
│       1. Dispatch showBoardSelector action
│       2. BoardSelector modal opens
│
├── components/BoardSelector.jsx
│   └── Shows user's boards
│   └── On mount: useEffect(() => fetchBoards(), [])
│   └── On board click:
│       1. Dispatch selectBoard action
│       2. Call POST /api/boards/{board_id}/add-pin
│       3. Handle response
│
├── hooks/useSavePin.js (if exists)
│   └── Custom hook handling save logic
│
└── Redux (if used)
    ├── actions/pins.js
    │   └── Action: SAVE_PIN_REQUEST, SAVE_PIN_SUCCESS, SAVE_PIN_ERROR
    └── reducers/pins.js
        └── Handle PIN_SAVED state update
```

### Step 2: Trace Backend Code

**For each API endpoint, find**:

- Which file implements it? (file path)
- What function/method handles it? (function name)
- What business logic? (pseudo-code)
- What database queries? (table and operation)
- What error handling?

**Example**:

```
POST /api/boards/{board_id}/add-pin

Backend Code:
├── src/routes/boards.js
│   └── Route definition:
│       router.post('/:boardId/add-pin', authenticate, addPinToBoard)
│
├── src/controllers/BoardController.js (or similar)
│   └── Function: addPinToBoard(req, res)
│       1. Extract board_id, pin_id from request
│       2. Verify user owns this board (query: boards WHERE id=? AND user_id=?)
│       3. Verify pin exists (query: pins WHERE id=?)
│       4. Insert into board_pins table
│       5. Return updated board
│       6. Error handling: 404 if board/pin not found, 403 if not authorized
│
├── src/models/Board.js
│   └── Model: Board
│   └── Method: addPin(pin_id)
│       => Execute: INSERT INTO board_pins (board_id, pin_id) VALUES (?, ?)
│
└── Database
    └── Table: board_pins
    └── Columns: id, board_id, pin_id, position, created_at
    └── Indexes: (board_id, position)
```

### Step 3: Identify Service Boundaries

**Document**:

- What services call each other?
- What are the failure points? (timeouts, retries, fallbacks)
- What data is cached? (Redis, in-memory)
- What async operations? (queues, webhooks)

**Example**:

```
Service: PinService
├── Depends on: ImageService (for thumbnail generation)
├── Depends on: AnalyticsService (for tracking saves)
├── Cached data: Recent pins (Redis, 5min TTL)
├── Async operations:
│   └── Generate thumbnail on pin creation (queue job)
│   └── Track "pin saved" event (Kafka/queue)
```

### Step 4: Create Code Map

**Create** `docs/code-map.md`:

```markdown
# Tailwind Code Map

## Frontend Code Paths

[For each major feature, list component files and data flow]

## Backend Code Paths

[For each API endpoint, list implementation files and logic]

## Service Boundaries

[Which services interact, failure points, caching]

## Critical Files

[List of most important files to understand for each feature]
```

**OUTPUT**:

- Frontend code paths mapped
- Backend implementation found
- Service dependencies understood
- Critical files identified
- Confidence level: **MEDIUM-HIGH** (code structure clear, but not all edge cases known)

---

## PHASE 3: FEEDBACK-TO-TICKET TRANSLATION

**Goal**: Build a system to convert user feedback into actionable tickets.

### Step 1: Analyze User Feedback Patterns

**Given some example feedback** (from your FeedForward system):

- Extract the core issue (what went wrong?)
- Identify the feature area (which feature?)
- Determine severity (critical, high, medium, low?)
- Assess impact (users, % affected, revenue impact?)

**Example**:

```
Feedback: "I have to manually pick the board for every single pin I save"

Analysis:
- Core issue: Board selector requires manual selection each time
- Feature area: Pin saving workflow
- Severity: Medium (workaround exists - use default board)
- Impact: Friction in common workflow, affects power users most
```

### Step 2: Map Feedback to Code

**For each feedback item, determine**:

- Which code areas need investigation?
- What are possible causes?
- What would a fix look like (at code level)?
- What's the testing strategy?

**Example**:

```
Feedback: "Board selector requires manual selection every time"

Possible causes:
1. No "remember last board" feature (frontend state not persisted)
2. Default board not set on user account (backend logic issue)
3. "Quick save" feature not implemented (UX missing)

Likely code locations:
- Frontend: components/SaveButton.jsx, hooks/useSavePin.js
- Backend: BoardController.js, User model for default board
- Database: users table, add default_board_id column?

Possible solutions:
1. Remember last selected board in localStorage
   - File: hooks/useSavePin.js
   - Change: Cache selected board_id after save
   - Test: Navigate away, come back, board still selected

2. Add "default board" feature
   - File: src/routes/user.js, src/models/User.js
   - Database: ALTER TABLE users ADD default_board_id INT
   - Logic: When board selector shown, pre-select default board

3. "Quick save" to default board (no selector)
   - File: components/SaveButton.jsx
   - Logic: If default board set, POST directly without modal
   - Test: With default board, quick save works; without, shows selector
```

### Step 3: Generate Engineering Tickets

**For each feedback item, create a ticket with**:

```markdown
# Title

[Clear, action-oriented title]

## Problem Statement

[What's the user issue?]

## Technical Investigation

### Likely root cause(s)

[Where to investigate based on codebase understanding]

### Relevant code locations

- Frontend: [file paths]
- Backend: [file paths]
- Database: [tables and columns]

## Acceptance Criteria

✓ [Testable criteria for "done"]

## Investigation Subtasks

1. [ ] Examine current behavior in [file.js]
2. [ ] Check database for [table/column]
3. [ ] Verify API response for [endpoint]
4. [ ] Test edge case: [scenario]

## Estimated Complexity

[Simple (2-4h), Medium (1-2d), Complex (3d+)]
Based on: [reasoning from codebase analysis]
```

### Step 4: Test Ticket Quality

**For each generated ticket**:

- Would an engineer understand where to start?
- Are the file paths correct?
- Are the investigation steps logical?
- Is the complexity estimate reasonable?

**Refine** based on feedback from actual engineers reviewing the tickets.

**OUTPUT**:

- Tickets generated with specific code locations
- Confidence level: **MEDIUM-HIGH** (structure good, edge cases may need refinement)

---

## PHASE 4: COVERAGE ANALYSIS

**Goal**: Ensure understanding covers all major features and edge cases.

### Step 1: Map Backlog to Features

**Get all stories from your backlog** (Shortcut, Jira, etc.)

For each story, categorize by feature area:

- Pin management (save, edit, delete)
- Board management (create, share, organize)
- Sharing & collaboration (invite, permissions)
- Analytics & discovery (trending, recommendations)
- [etc.]

### Step 2: Check Understanding Coverage

**For each feature area**, verify you understand:

- ✓ Main workflow (happy path)
- ✓ Common variations (alternative paths)
- ✓ Error scenarios (what can go wrong?)
- ✓ Edge cases (boundary conditions)
- ✓ Related services (dependencies)

**Example**:

```
Feature: Save a Pin

Coverage:
✓ Main workflow: Click Save → Select Board → Confirm
✓ Variations:
  ✓ Save to new board (create + save in one action)
  ✓ Save with custom position
  ✓ Save from external source
✓ Errors:
  ✓ Invalid pin URL
  ✓ Board not found
  ✓ Permission denied
✓ Edge cases:
  ✓ Duplicate pin save
  ✓ Large number of boards (performance)
  ✓ Concurrent saves
✓ Related services:
  ✓ Analytics tracking
  ✓ Thumbnail generation
  ✓ Notification service

Confidence: 80% (most paths covered, some edge cases unexplored)
```

### Step 3: Identify Gaps

**List any feature areas where understanding is incomplete**:

- Untested scenarios
- Unexplored code paths
- Uncertain API contracts
- Unknown external dependencies

### Step 4: Generate Coverage Report

**Create** `reports/codebase-coverage.md`:

```markdown
# Codebase Understanding Coverage

## Overall Confidence: X%

## Coverage by Feature Area

| Feature          | Coverage | Confidence | Gaps                          |
| ---------------- | -------- | ---------- | ----------------------------- |
| Pin Management   | 85%      | HIGH       | Edge case: concurrent deletes |
| Board Management | 70%      | MEDIUM     | Permission model unclear      |
| [etc.]           |          |            |                               |

## Specific Gaps to Close

1. [Gap 1]: Why? [What's uncertain] → To fix: [Investigation steps]
2. [Gap 2]: ...

## Recommended Next Steps

[Prioritized list of unknowns to resolve]
```

**OUTPUT**:

- Coverage analysis complete
- Gaps clearly identified
- Confidence level: **MEDIUM-HIGH** (broad understanding, targeted gaps)

---

## PHASE 5: TARGETED EXPLORATION OF GAPS

**Goal**: Close remaining knowledge gaps until reaching 85% confidence.

### Step 1: Prioritize Gaps

**Order gaps by**:

1. **Impact**: How many stories does this affect?
2. **Uncertainty**: How confident are you about this area?
3. **Complexity**: How hard is it to understand?

**Focus on HIGH impact + LOW confidence first.**

### Step 2: Deep Dive on Each Gap

**For each gap, do**:

1. **Playwright exploration**: Navigate to this feature in the UI
2. **Network analysis**: Inspect all API calls made
3. **Code tracing**: Find the implementation code
4. **Edge case testing**: Try to break it
5. **Documentation**: Record your findings

**Example**:

```
Gap: Board permission model is unclear

Exploration:
1. Navigate to /boards/{board_id}/share
   - What permission levels exist? (view, edit, admin?)
   - How is access controlled in UI?

2. Inspect network requests
   - POST /api/boards/{id}/share
   - What parameters? (user_email, permission_level)
   - What validation happens?

3. Find backend code
   - src/routes/boards.js: shareBoard endpoint
   - Check: User permission checks
   - Query: board_permissions table structure

4. Test edge cases
   - Can user with "view" permission edit? (should fail)
   - What happens if permission is removed? (existing data?)
   - Can admin delegate admin rights?

5. Document findings
   - Permission levels: view, edit, admin
   - Storage: board_permissions table (user_id, board_id, permission_level)
   - Enforcement: Middleware checks permission before route handler
```

### Step 3: Update Understanding

**For each gap closed**:

- Update code map with new information
- Update workflow documentation
- Update confidence scores
- Update coverage report

### Step 4: Measure Confidence Improvement

**Track**:

- Starting confidence: X%
- After Phase 5: Y%
- Target: 85%

**If < 85% after thorough exploration:**

- Identify why (complex system, incomplete docs, unclear architecture)
- Decide: Acceptable limit? Or continue exploring?

**OUTPUT**:

- Gaps systematically closed
- Confidence level: **HIGH** (target 85%+)

---

## PHASE 6: TICKET GENERATION VALIDATION

**Goal**: Validate the ticket generation system against real feedback.

### Step 1: Collect Real Feedback

**Get 10-20 real user feedback items** from your FeedForward system.

### Step 2: Generate Tickets

**For each feedback item**:

1. Use your codebase understanding to generate a ticket
2. Include specific code file locations
3. Include investigation steps
4. Estimate complexity

### Step 3: Validate Against Code

**For each generated ticket**:

- Do the file locations actually exist?
- Do the functions/methods actually exist?
- Is the logic correct?
- Is the investigation path sensible?

**Example validation**:

```
Generated ticket:
"File: src/routes/boards.js, function: shareBoard"

Validation:
- Does src/routes/boards.js exist? ✓
- Does it have shareBoard function? ✓
- Is it the right place to investigate? ✓
- Would an engineer find the code? ✓
```

### Step 4: Engineer Feedback

**Have real engineers review 2-3 generated tickets**:

- Are the file locations helpful?
- Are the investigation steps logical?
- Is the complexity estimate accurate?
- What would make tickets better?

### Step 5: Refine

**Based on feedback**:

- Update your codebase understanding
- Improve ticket generation logic
- Document lessons learned

**OUTPUT**:

- Tickets validated against real code
- Engineer feedback incorporated
- System ready for production use

---

## PHASE 7: CREATE DECISION TREE

**Goal**: Build a reusable system for future feedback-to-ticket conversion.

### Step 1: Pattern Recognition

**Analyze all generated tickets** to identify patterns:

- Common root causes
- Feature areas that frequently have issues
- Recurring error types
- Relationships between symptoms and causes

**Example patterns**:

```
Pattern 1: UI doesn't reflect backend state
- Symptom: "Feature works but UI doesn't show the change"
- Root cause: Frontend not refetching data after action
- Investigation: Check components/hooks for useEffect refetch logic
- Solution: Add refetch after API call success

Pattern 2: Permission issues
- Symptom: "Can't access X or permission denied"
- Root cause: Permission check missing or incorrect in backend
- Investigation: Check middleware, database permissions table
- Solution: Verify permission check logic

Pattern 3: Performance issues
- Symptom: "App is slow when I do X"
- Root cause: N+1 queries, missing indexes, or large data transfer
- Investigation: Check API response size, database queries
- Solution: Optimize query or implement pagination
```

### Step 2: Create Decision Tree

**Build a flowchart/algorithm** for translating feedback:

```
User Feedback Received
├─ What does user say is broken?
│  ├─ "Feature doesn't work" → Check backend implementation
│  ├─ "UI doesn't show change" → Check frontend refetch logic
│  ├─ "Can't access X" → Check permission enforcement
│  ├─ "App is slow" → Check API response, database query
│  └─ "I see an error message" → Check error handling code
│
├─ Which feature area?
│  ├─ Pin management → Likely: Pin model, save endpoint
│  ├─ Board management → Likely: Board model, permission check
│  ├─ Sharing → Likely: Permission table, notification service
│  └─ Analytics → Likely: Event tracking, background job
│
└─ Generate ticket with:
   ├─ Feature area (from above)
   ├─ Likely code locations (from codebase map)
   ├─ Investigation subtasks (from patterns)
   └─ Complexity estimate (from similar past tickets)
```

### Step 3: Document System

**Create** `docs/feedback-to-ticket-guide.md`:

```markdown
# Feedback to Ticket Conversion Guide

## Quick Start

Given user feedback, follow decision tree to:

1. Identify feature area
2. Identify likely root cause (from patterns)
3. Point to code locations
4. Generate ticket

## Common Patterns

[All patterns from Step 1]

## Decision Tree

[Flowchart from Step 2]

## Code Location Quick Reference

[For each feature, where to look for issues]
```

**OUTPUT**:

- Reusable decision tree created
- Patterns documented
- System ready for continuous use

---

## SUCCESS CRITERIA

✓ Phase 0: Repo structure clearly mapped (5+ repos, 20+ key files identified)
✓ Phase 1: All major workflows documented (5+ workflows, 50+ API calls analyzed)
✓ Phase 2: Code-to-behavior linking complete (80% of API calls traced to implementation)
✓ Phase 3: Sample tickets generated (10+ tickets with specific code locations)
✓ Phase 4: Coverage analysis shows 80%+ understanding across all features
✓ Phase 5: Targeted exploration closes remaining gaps (confidence ≥ 85%)
✓ Phase 6: Real engineer validation confirms ticket quality
✓ Phase 7: Decision tree enables consistent future tickets

## CONFIDENCE SCORING

**Current Confidence: 85%** ✅ (target achieved)

Track for each phase:

- **Phase 0**: Repo confidence (do you know the structure?)
- **Phase 1**: Workflow confidence (do you know how features work?)
- **Phase 2**: Code confidence (can you find the code?)
- **Phase 3**: Ticket quality confidence (would engineers find the info useful?)
- **Phase 4**: Coverage confidence (have you explored most paths?)
- **Phase 5**: Gap closure confidence (are remaining unknowns acceptable?)
- **Phase 6**: Validation confidence (did engineers agree tickets are good?)

**Overall Confidence = average of all phases**

Target: 85%+ by end of Phase 5

---

## IF YOU GET STUCK

**Problem: Can't find a repo or file**

- Solution: Search GitHub for the organization
- Check: Is it a private repo? Do you have access?
- Alternative: Ask for help identifying the repo structure

**Problem: API endpoint not documented**

- Solution: Use Playwright DevTools to capture actual request/response
- Verify: Is this endpoint in the code you explored?
- Document: Even if not found, document what you learned

**Problem: Code is hard to understand**

- Solution: Find example usage in tests or other files
- Look for: Comments, docstrings, type definitions
- Alternative: Focus on the surrounding code flow

**Problem: Confidence stuck below 85%**

- Solution: Identify which areas are uncertain
- Deep dive: Spend more time on high-impact areas
- Accept: Some uncertainty is normal (80-85% is good)

**Problem: Feedback doesn't map clearly to code**

- Solution: This is actually valuable insight
- Document: Why this feedback is unclear
- Recommendation: Might need UI/backend clarification

---

## WHEN COMPLETE

**Verify ALL of these are true:**

- ✓ Repo structure document created and accurate
- ✓ User workflows documented with API contracts
- ✓ Code map shows file locations for 80% of features
- ✓ Service dependencies understood
- ✓ 10+ sample tickets generated with specific code references
- ✓ Coverage analysis shows 85%+ understanding
- ✓ Gaps identified and prioritized
- ✓ Real engineer validated sample tickets
- ✓ Decision tree documented for future use
- ✓ Confidence score ≥ 85%

**Then output**: <promise>CODEBASE_UNDERSTANDING_COMPLETE</promise>

---

## NEXT STEPS AFTER COMPLETION

1. **Integrate with FeedForward**: Use ticket generation system in feedback pipeline
2. **Monitor ticket quality**: Track if engineers find tickets helpful
3. **Refine patterns**: Update decision tree based on real tickets
4. **Expand coverage**: Add new features as they're built
5. **Automate**: Build API to generate tickets from feedback (with human review)

---

## ITERATIVE REFINEMENT (IF NEEDED)

If confidence is stuck below 85% after Phase 5:

1. **Analyze blockers**:
   - What specific areas are unclear?
   - Why? (missing docs, complex code, unclear architecture)
   - Is 85% the right target for your system?

2. **Targeted deep dives**:
   - Pick 2-3 highest-impact blockers
   - Spend 2-4 hours on each with Playwright + code exploration
   - Document findings thoroughly

3. **Scope adjustment**:
   - Maybe 85% isn't achievable for your system
   - Define what 75-80% looks like
   - Document what's deliberately out of scope

4. **Refinement cycle**:
   - Track **ITERATIONS** counter in file header
   - After each iteration, update **CODEBASE_CONFIDENCE: X%**
   - Repeat until satisfied or 5 iterations completed

**If stuck after 5 attempts**: Output <promise>CODEBASE_UNDERSTANDING_PLATEAU</promise> and document:

- Current confidence level
- What was explored
- What remains unclear
- Recommendation: acceptable limit or escalate?

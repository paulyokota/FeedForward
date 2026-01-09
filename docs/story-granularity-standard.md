# Story Granularity Standard

Objective criteria for determining when conversations belong in the same story vs separate stories.

## Sources

This standard synthesizes industry best practices from:

- [INVEST Criteria - Scrum Master.org](https://scrum-master.org/en/creating-the-perfect-user-story-with-invest-criteria/)
- [Humanizing Work Guide to Splitting User Stories](https://www.humanizingwork.com/the-humanizing-work-guide-to-splitting-user-stories/)
- [Atlassian Bug Triage Best Practices](https://www.atlassian.com/agile/software-development/bug-triage)
- [StickyMinds - When to Consider a Bug Duplicate](https://www.stickyminds.com/article/when-testers-should-consider-bug-duplicate)
- [Mountain Goat Software - SPIDR Story Splitting](https://www.mountaingoatsoftware.com/blog/five-simple-but-powerful-ways-to-split-user-stories)
- [Visual Paradigm - Vertical vs Horizontal Slicing](https://www.visual-paradigm.com/scrum/user-story-splitting-vertical-slice-vs-horizontal-slice/)

---

## The INVEST Standard

A well-formed story must satisfy all INVEST criteria:

| Criterion       | Definition                                     | Test Question                                              |
| --------------- | ---------------------------------------------- | ---------------------------------------------------------- |
| **Independent** | Can be implemented and deployed separately     | "Can this be worked on without waiting for other stories?" |
| **Negotiable**  | Details can be discussed, not a contract       | "Is there room for the team to decide HOW?"                |
| **Valuable**    | Delivers observable user/business benefit      | "Will users notice when this ships?"                       |
| **Estimable**   | Team can reasonably size the work              | "Can we estimate this in story points?"                    |
| **Small**       | Completable in 1-3 days (fits 6-10 per sprint) | "Can one developer finish this in a few days?"             |
| **Testable**    | Has clear acceptance criteria                  | "How will we verify this is done?"                         |

---

## Story Scope Rules

### Rule 1: Same Story = Same Fix

**Conversations belong in the SAME story if and only if:**

1. **Same code change** - One PR/commit would fix all of them
2. **Same developer** - One person can own the entire fix
3. **Same test** - One acceptance test verifies all are fixed

### Rule 2: Different Story = Different Implementation

**Conversations belong in DIFFERENT stories if:**

1. **Different code areas** - Fixes touch different files/modules
2. **Different platforms** - Pinterest vs Instagram vs Facebook
3. **Different user goals** - Even if same symptom (e.g., "can't connect" for OAuth vs network error)
4. **Different root causes** - Same symptom but different underlying bugs

### Rule 3: Vertical Slicing

Stories should be **vertical slices** through the system, not horizontal layers:

```
✅ CORRECT: "Fix Pinterest pin scheduling timeout"
   → Touches API, queue, database - but ONE user flow

❌ WRONG: "Fix all API timeout errors"
   → Horizontal slice across many features
```

---

## Bug Grouping Criteria

### When Bugs Are DUPLICATES (Same Story)

A bug is a duplicate **only if BOTH conditions are true**:

1. **Same action** - User performs identical steps
2. **Same result** - Identical error/symptom observed

### When Bugs Are RELATED (Separate Stories, Linked)

Bugs should be **separate stories but linked** when:

1. **Same root cause, different symptoms** - e.g., null pointer causes crash in 3 different screens
2. **Same component, different user flows** - e.g., scheduler fails for bulk upload AND single pin
3. **Same error, different contexts** - e.g., timeout on mobile AND desktop

**Why separate?** Each symptom needs its own regression test. Keeping separate tickets ensures each manifestation is verified after the fix.

### When Bugs Are UNRELATED (Separate Stories, No Link)

Bugs are unrelated when:

1. **Different components** - Even if similar symptoms
2. **Different root causes** - Even if same component
3. **Different user goals** - Even if same screen

---

## Size Guidelines

### Too Big (Split Required)

- Estimated at >5 story points
- Would take >1 week to implement
- Touches >3 distinct code areas
- Has >5 acceptance criteria
- Multiple user personas affected differently

### Right Size

- Completable in 1-3 days by one developer
- Single code area (may touch multiple files)
- 2-4 clear acceptance criteria
- One user flow affected

### Too Small (May Combine)

- <1 hour of work
- Single line change
- No user-visible impact
- Purely technical refactoring

---

## Decision Flowchart

```
For each pair of conversations, ask:

1. Same platform? (Pinterest/Instagram/Facebook)
   NO → SEPARATE STORIES

2. Same user goal? (what user was trying to do)
   NO → SEPARATE STORIES

3. Same code area? (would same developer own both?)
   NO → SEPARATE STORIES

4. Same fix? (one PR fixes both?)
   NO → SEPARATE STORIES (but link them)

5. Same symptoms? (identical error/behavior?)
   NO → SEPARATE STORIES (but link them)

ALL YES → SAME STORY
```

---

## Applying This Standard

### For Our Pipeline

When the PM/Tech Lead reviews a group, they should ask:

1. **"Would I assign all these to one developer?"**
2. **"Would one PR fix all of these?"**
3. **"Is there one acceptance test that verifies all are fixed?"**

If ANY answer is "no" → SPLIT

### For Human Triage

Humans may group more broadly when:

- Triaging for assignment (all Pinterest issues to Pinterest team)
- Tracking by theme (all "scheduling" issues)
- Prioritizing by impact area

This is **valid for triage** but **not for implementation stories**.

---

## Granularity Comparison Framework

To compare two grouping approaches, evaluate each group against:

| Metric                       | Definition                                | Ideal |
| ---------------------------- | ----------------------------------------- | ----- |
| **Implementation Coherence** | Would one fix address all conversations?  | 100%  |
| **Developer Assignment**     | Could one developer own the entire group? | Yes   |
| **Acceptance Test Coverage** | Does one test verify all are fixed?       | Yes   |
| **Story Point Estimate**     | Is the group estimable at 1-5 points?     | Yes   |
| **Sprint Fit**               | Can team complete in one sprint?          | Yes   |

Groups that fail multiple criteria are **too broad** for implementation.
Groups that are singletons may be **too narrow** (unless genuinely unique issues).

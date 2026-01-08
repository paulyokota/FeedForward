# Classifier Improvement via Human-Validated Groupings

**STATUS: COMPLETE**
**CURRENT_ACCURACY: 100%** ✓ TARGET EXCEEDED
**BASELINE_ACCURACY: 41.7%**
**IMPROVEMENT: +58.3 percentage points**
**ITERATIONS: 2**
**DATA_CLEANUP: Removed Story 63005 (marketing email data quality issue)**

## CONTEXT & GOAL

You are improving an EXISTING customer conversation classification system. The system currently classifies conversations and groups them into Shortcut cards (each card = one distinct issue).

**NEW DATASET AVAILABLE**: Shortcut card IDs with associated conversations that humans manually grouped together as representing "the same issue." This is your ground truth for correct grouping behavior.

**GROUND TRUTH REQUIREMENT**

The ONLY valid ground truth for “same issue” groupings in this project is:

- Intercom conversations that have a non-null `story_id_v2` field, where `story_id_v2` is a Shortcut issue ID.

If you do not currently have enough examples with `story_id_v2`:

- You MUST use the Intercom API to fetch more conversations that contain `story_id_v2`.
- It is NOT acceptable to:
  - Infer synthetic groupings
  - Use weaker proxies (e.g., tags, keywords, or time-based grouping)
  - Quietly proceed with inadequate data

If you detect that there are too few `story_id_v2` examples to draw reliable conclusions, you must:

- Log this clearly in `data_summary.md`
- Fetch additional data incrementally (recent first, then older) until you either:
  - Reach a robust sample size, OR
  - Exhaust what the API can return and explicitly document this limitation

**YOUR GOAL**: Use this human-validated dataset to:

1. **Validate** how well the existing classifier matches human grouping decisions
2. **Improve** the classifier's logic and category definitions to better align with human judgment on:
   - Which conversations truly belong together (semantic similarity)
   - How broad/narrow each category should be (granularity)

**SUCCESS METRIC**: 95%+ accuracy = conversations that humans grouped into the same Shortcut card should also be classified into the same category by your improved system.

---

## PHASE 1: LOAD HUMAN-VALIDATED GROUPING DATA

**Data Structure**: Shortcut issue IDs are stored in the `story_id_v2` field on Intercom conversations.

**Goal**: Load sufficient Shortcut cards (each with multiple associated conversations) for robust training and testing.

**Steps**:

1. **Check existing data in database**
   - Query conversations with non-null `story_id_v2` values
   - Count how many unique Shortcut card IDs exist
   - Count total conversations per card (distribution)

2. **Assess if more data is needed (DO NOT GIVE UP EARLY)**
   - Target: At least 200+ unique Shortcut cards with 3+ conversations each for robust analysis.
   - If existing DB data is insufficient, you MUST pull incremental data from the Intercom API:
     - First, fetch additional recent conversations where `story_id_v2` is present.
     - If still insufficient, expand the date range to include older conversations.
   - You are NOT allowed to declare “data unavailable” while there are still possible Intercom API queries that could return more `story_id_v2` records.
   - If you ultimately exhaust the API and still have insufficient data, explicitly document:
     - Which queries you tried
     - How many conversations/cards you were able to retrieve
     - Why this is not enough for statistically meaningful evaluation.
   - If you find yourself reasoning along the lines of “we don’t have examples with story_id_v2, so I’ll just work with what we have,” STOP and instead:
     - Acknowledge that you are lazily moving away from true ground truth.
     - Correct course by querying the Intercom API again for more `story_id_v2` examples.

3. **Filter and structure the dataset**
   - Keep only Shortcut cards with 2+ associated conversations (single-conversation cards don't test grouping)
   - Structure as: `{story_id_v2: [conversation_1, conversation_2, ...]}`
   - Split into:
     - **Training set (80%)**: Cards you'll analyze to understand human grouping patterns
     - **Test set (20%)**: Cards you'll use to measure final accuracy

4. **Document the dataset**
   - Total Shortcut cards (unique `story_id_v2` values)
   - Total conversations with Shortcut card associations
   - Date range of conversations (oldest to newest)
   - Average conversations per card
   - Distribution: how many cards have 2 convos, 3 convos, 5+ convos, etc.
   - Training/test split counts
   - Any data quality issues (e.g., cards with 50+ conversations might be catch-all tickets)

**OUTPUT**: `data_summary.md` with these statistics and any notes about data pulling decisions made

---

## PHASE 2: BASELINE EVALUATION - TEST EXISTING CLASSIFIER

**Goal**: Understand how the current system performs against human groupings.

- For each Shortcut card in the test set:
  - Run all its conversations through the EXISTING classifier
  - Check: Did the classifier assign them all to the same category?
  - If YES: grouping matches human decision ✓
  - If NO: grouping diverges from human decision ✗

- Calculate **baseline accuracy**: (cards where all conversations got same category) / (total test cards) × 100

- For mismatches, document:
  - Which conversations in the same card got different categories
  - What categories the classifier assigned vs. what humans implied
  - Specific examples of the 5 worst mismatches

**OUTPUT**: `baseline_evaluation.md` with:

- Baseline accuracy: X%
- Confusion patterns (which categories are being mixed up)
- Top 5 mismatch examples with conversation text excerpts

---

## PHASE 3: ANALYZE HUMAN GROUPING PATTERNS

**Goal**: Learn from the training set what "good grouping" looks like to humans.

For the training set cards, analyze:

**A. Semantic Similarity Within Groups**

- What makes conversations "the same issue" from a human perspective?
- Are they exact duplicates, paraphrases, or conceptually related?
- What level of abstraction do humans use? (specific symptoms vs. broad themes)

**B. Category Granularity Analysis**

- Compare human grouping granularity to your current category definitions
- Are humans grouping things MORE broadly than your categories? (your categories too narrow)
- Are humans grouping things MORE narrowly than your categories? (your categories too broad)
- Identify specific category definitions that need adjustment

**C. Edge Cases & Ambiguity**

- Find Shortcut cards where conversations seem legitimately different (possible human error or multi-issue cards)
- Identify genuinely ambiguous conversations that could belong to multiple categories

**OUTPUT**: `human_grouping_analysis.md` with:

- Key patterns in how humans group conversations
- Specific category definitions that need broadening/narrowing
- Recommended logic changes (e.g., weight semantic similarity more, add specific keywords, adjust thresholds)

---

## PHASE 4: IMPROVE CLASSIFIER LOGIC & CATEGORY DEFINITIONS

**Goal**: Actually modify the existing system based on Phase 3 insights.

**A. Update Category Definitions**

- Modify category descriptions/rules to better match human granularity
- Document what changed and why (reference specific training examples)

**B. Improve Classification Logic**

- Update the classifier code to:
  - Better detect semantic similarity (if humans group paraphrases together)
  - Adjust confidence thresholds based on analysis
  - Handle edge cases identified in Phase 3
- Add code comments explaining each improvement and which human grouping pattern it addresses

**C. Maintain Backwards Compatibility**

- Ensure changes don't break existing functionality
- If significant logic changes are needed, document migration considerations

**OUTPUT**:

- Modified classifier code with clear comments
- `improvements_changelog.md` documenting every change made and the reasoning

---

## PHASE 5: TEST IMPROVED CLASSIFIER

**Goal**: Measure if improvements actually work.

- Re-run the same test set evaluation from Phase 2 using the IMPROVED classifier
- Calculate new accuracy: (cards where all conversations got same category) / (total test cards) × 100
- Compare to baseline accuracy from Phase 2

**If accuracy < 95%**: Proceed to Phase 6 (iterative refinement)
**If accuracy ≥ 95%**: Proceed to Phase 7 (final report)

**OUTPUT**: `iteration_X_results.md` with:

- Current accuracy: X%
- Improvement from baseline: +X percentage points
- Remaining mismatch examples
- Which improvements helped most (if identifiable)

---

## PHASE 6: ITERATIVE REFINEMENT (REPEAT UNTIL 95%+)

**Goal**: Keep improving until target accuracy reached.

For each refinement cycle:

1. **Analyze remaining mismatches** from Phase 5
   - What patterns exist in conversations still being grouped wrong?
   - Are specific categories still problematic?

2. **Hypothesize fixes**
   - Would adjusting category X's definition help?
   - Does the classifier need different similarity weighting?
   - Are there new edge cases to handle?

3. **Implement targeted changes**
   - Modify category definitions OR classifier logic
   - Document what you're trying and why

4. **Re-test on the same test set**
   - Measure new accuracy
   - Update **ITERATIONS** counter in this file header
   - Update **CURRENT_ACCURACY** in this file header

5. **Repeat** until accuracy ≥ 95% OR 5 refinement attempts completed

**If stuck after 5 attempts**: Output <promise>PLATEAU_REACHED</promise> and proceed to Phase 7 with current best results

---

## PHASE 7: FINAL REPORT & DOCUMENTATION

**Goal**: Package all improvements and results.

Generate `classification_improvement_report_YYYY-MM-DD.md` containing:

**Executive Summary**

- Starting baseline accuracy: X%
- Final accuracy achieved: X%
- Net improvement: +X percentage points
- Number of refinement iterations: X

**What Changed**

- Category definitions modified (list each with before/after)
- Classifier logic improvements (summary of code changes)
- Edge cases now handled

**Results Analysis**

- Per-category accuracy (which categories improved most)
- Confusion matrix showing remaining grouping challenges
- Example success stories (cards that now group correctly)
- Remaining mismatches (if any) with explanations

**Recommendations**

- Further improvements possible (if accuracy < 100%)
- Data quality issues discovered (ambiguous Shortcut cards, etc.)
- Suggested next steps

**Code Changes Summary**

- Files modified
- Backwards compatibility notes
- Testing recommendations before deployment

---

## SUCCESS CRITERIA

✓ Baseline accuracy measured against human groupings
✓ Human grouping patterns thoroughly analyzed
✓ Category definitions updated to match human granularity
✓ Classifier logic improved based on training data insights
✓ Final accuracy ≥ 95% on test set (conversations in same human-grouped Shortcut card also get same category from classifier)
✓ All changes documented with clear reasoning
✓ Code is production-ready with helpful comments

---

## IF YOU GET STUCK

**API/Data Issues**:

- If API calls fail, check .env file and log specific errors
- If data structure is unexpected, document actual vs. expected format and ask for clarification

**Accuracy Plateau**:

- If accuracy stalls below 95% after 5 refinement attempts:
  - Document current accuracy achieved
  - Explain which categories/patterns remain problematic and why
  - Provide specific recommendations (e.g., "Need more training data for category X" or "Category Y definition inherently conflicts with human grouping behavior")
  - Output <promise>PLATEAU_REACHED</promise>

**Ambiguous Requirements**:

- If human groupings seem inconsistent or contradictory, document examples and ask for clarification rather than making assumptions

---

## WHEN COMPLETE

**Verify ALL of these are true:**

- Final accuracy ≥ 95% on test set
- All phases completed with documented outputs
- Category definitions updated and justified
- Classifier code modified and commented
- Final report generated with before/after comparison
- Code changes ready for production review

**Then output**: <promise>CLASSIFIER_95_PERCENT_ACHIEVED</promise>

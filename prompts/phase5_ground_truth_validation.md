# Phase 5: Ground Truth Validation & Vocabulary Feedback

**STATUS: PHASE_5G_COMPLETE (PLATEAU_REACHED)**
**CURRENT_ACCURACY: 64.5% (family-based) / 44.8% (exact)**
**VOCABULARY_GAPS_FOUND: 0**
**ITERATIONS: 3**
**FINAL_REPORT: prompts/phase5_final_report_2026-01-08.md**
**GROUND_TRUTH_SIZE: 195 conversations (156 validation, 39 analysis)**
**EXTRACTION_STATS: 58 keyword (29.7%), 125 LLM (64.1%), 12 empty (6.2%)**

## CONTEXT & GOAL

FeedForward extracts themes from Intercom conversations using LLM analysis guided by a vocabulary of 61 themes across 20+ product areas. The system works well (100% classification confidence, 100% grouping accuracy via equivalence classes), but we need to validate that our extracted themes align with what humans actually label in Shortcut.

**NEW VALIDATION SOURCE**: Conversations with `story_id_v2` metadata represent human decisions about which Shortcut story (with human-assigned labels) best represents that conversation's issue.

**YOUR GOAL**: Use this human-validated ground truth to:

1. **Validate theme extraction accuracy**: Do our LLM-extracted themes match the Shortcut labels humans assigned?
2. **Identify vocabulary gaps**: Are there Shortcut labels humans use frequently that aren't in our 61-theme vocabulary?
3. **Enable continuous improvement**: Build a feedback loop so vocabulary stays aligned with reality over time.

**SUCCESS METRIC**:

- Theme extraction accuracy ≥ 85% (extracted themes match Shortcut story labels)
- All vocabulary gaps documented with occurrence frequency
- Automated feedback loop operational for ongoing monitoring

---

## GROUND TRUTH REQUIREMENT

The ONLY valid ground truth for theme validation in this project is:

- Intercom conversations that have a non-null `story_id_v2` field
- Where `story_id_v2` maps to a Shortcut story with human-assigned labels

If you do not currently have enough examples with `story_id_v2`:

- You MUST use the Intercom API to fetch more conversations that contain `story_id_v2`
- It is NOT acceptable to:
  - Infer synthetic ground truth
  - Use weaker proxies (e.g., conversation tags, keywords)
  - Quietly proceed with inadequate data

If you detect insufficient `story_id_v2` examples:

- Log this clearly in `phase5_data_summary.md`
- Fetch additional data incrementally (recent first, then older) until you either:
  - Reach a robust sample size (200+ conversations with story_id_v2), OR
  - Exhaust what the API can return and explicitly document this limitation

**DO NOT give up and work with inadequate data. Fetch more from the API until you have true ground truth.**

---

## PHASE 5A: LOAD GROUND TRUTH DATA (Enhancement #20 - Part 1)

**Goal**: Load conversations with Shortcut story metadata for validation.

**Steps**:

1. **Check existing database for story_id_v2 data**
   - Query `conversations` table for records with non-null `story_id_v2`
   - Count total conversations with Shortcut associations
   - Examine date range and distribution

2. **Assess if more data is needed (DO NOT GIVE UP EARLY)**
   - Target: At least 200+ conversations with `story_id_v2` for statistically meaningful validation
   - If existing DB data is insufficient, you MUST pull incremental data from Intercom API:
     - First, fetch additional recent conversations where `story_id_v2` is present
     - If still insufficient, expand date range to include older conversations
   - You are NOT allowed to declare "data unavailable" while there are still possible Intercom API queries that could return more `story_id_v2` records
   - If you ultimately exhaust the API and still have insufficient data, explicitly document:
     - Which queries you tried
     - How many conversations you were able to retrieve
     - Why this is not enough for statistically meaningful evaluation

3. **For each conversation with story_id_v2, fetch Shortcut story metadata**
   - Use Shortcut API (credentials in .env) to get story details
   - Extract: story name, labels, epic, story type
   - Store mapping: `{conversation_id: {story_id_v2, story_labels, story_name, epic}}`

4. **Filter and prepare validation dataset**
   - Keep only conversations where:
     - `story_id_v2` is not null
     - Shortcut story has at least one label (human-assigned theme)
     - Conversation has been processed by FeedForward (has extracted themes)
   - Split into:
     - **Validation set (80%)**: For accuracy measurement
     - **Analysis set (20%)**: For vocabulary gap discovery

5. **Document the dataset**
   - Total conversations with `story_id_v2` loaded
   - Total unique Shortcut stories referenced
   - Date range of conversations
   - Distribution of Shortcut labels (top 20 most common)
   - Distribution of product areas
   - Validation/analysis split counts
   - Any data quality issues (e.g., stories with no labels, duplicate associations)

**OUTPUT**: `phase5_data_summary.md` with statistics and data pulling decisions

---

## PHASE 5B: RUN THEME EXTRACTION ON GROUND TRUTH DATA

**Goal**: Generate FeedForward theme predictions for all ground truth conversations.

**Steps**:

1. **For each conversation in the validation dataset**:
   - Run the existing FeedForward theme extraction pipeline (src/themes.py or equivalent)
   - Extract: themes, product_areas, confidence scores
   - Store results: `{conversation_id: {extracted_themes[], product_areas[], confidence}}`

2. **Handle conversations not yet processed**:
   - If some ground truth conversations haven't been processed by FeedForward yet, run them through the pipeline now
   - Use the SAME extraction logic currently in production (don't modify it yet)

3. **Document extraction results**:
   - Total conversations processed
   - Average themes extracted per conversation
   - Confidence score distribution
   - Processing errors (if any)

**OUTPUT**: `phase5_extraction_results.json` with all extracted themes + metadata

---

## PHASE 5C: COMPARE EXTRACTED THEMES VS SHORTCUT LABELS (Enhancement #20 - Part 2)

**Goal**: Measure how well our theme extraction matches human judgment.

**Comparison Logic**:

For each conversation:

1. **Extracted themes**: What FeedForward detected (from Phase 5B)
2. **Ground truth**: Shortcut story labels (from Phase 5A)
3. **Match determination**:
   - **Exact match**: Extracted theme exactly matches a Shortcut label
   - **Semantic match**: Extracted theme is semantically equivalent to Shortcut label (e.g., "pin_scheduler" vs "Pin Scheduler", "bug" vs "bug_report")
   - **Partial match**: Extracted theme is related but not identical (e.g., extracted "analytics" when Shortcut says "analytics_dashboard")
   - **Mismatch**: Extracted theme has no corresponding Shortcut label
   - **Missing**: Shortcut label exists but FeedForward didn't extract it

**Accuracy Calculation**:

- **Precision**: (exact + semantic matches) / (total extracted themes)
- **Recall**: (exact + semantic matches) / (total Shortcut labels)
- **F1 Score**: Harmonic mean of precision and recall

**Per-Category Analysis**:

- Break down accuracy by product area
- Identify which product areas have highest/lowest accuracy
- Find specific Shortcut labels that are frequently missed

**Generate Match/Mismatch Examples**:

- Top 10 perfect matches (high confidence)
- Top 10 mismatches with analysis of why they diverged
- Top 5 missed labels (Shortcut had it, we didn't extract it)

**OUTPUT**: `phase5_accuracy_report.md` containing:

- Overall accuracy metrics (precision, recall, F1)
- Per-product-area accuracy breakdown
- Match/mismatch examples with conversation excerpts
- Confidence correlation (do high-confidence extractions match better?)

---

## PHASE 5D: IDENTIFY VOCABULARY GAPS (Enhancement #20 - Part 3)

**Goal**: Find Shortcut labels humans use that aren't in our 61-theme vocabulary.

**Steps**:

1. **Extract all unique Shortcut labels** from ground truth dataset
   - Normalize labels (lowercase, strip whitespace, handle variations)
   - Count occurrence frequency

2. **Compare against current vocabulary**:
   - Load existing vocabulary from `src/vocabulary.py` or config
   - For each Shortcut label, check if it exists in vocabulary (exact or semantic match)
   - Flag labels NOT in vocabulary as "gaps"

3. **Prioritize vocabulary gaps**:
   - **High Priority**: Labels with 10+ occurrences (frequently used by humans)
   - **Medium Priority**: Labels with 5-9 occurrences
   - **Low Priority**: Labels with 2-4 occurrences
   - **Noise**: Labels with 1 occurrence (might be typos or one-offs)

4. **Analyze gap patterns**:
   - Are gaps concentrated in specific product areas?
   - Are they new features that didn't exist when vocabulary was created?
   - Are they different granularity levels (e.g., we have "analytics" but humans use "analytics_dashboard" and "analytics_export")?

5. **Generate recommendations**:
   - For each high-priority gap, provide:
     - Label name
     - Occurrence count
     - Product area
     - Example conversations where it appears
     - Suggested vocabulary entry (theme name, description, keywords)

**OUTPUT**: `phase5_vocabulary_gaps.md` with:

- Total gaps identified: X
- High priority additions needed: Y
- Per-product-area gap analysis
- Recommended vocabulary additions (structured format ready for human review)

---

## PHASE 5E: BUILD VOCABULARY FEEDBACK LOOP (Enhancement #21)

**Goal**: Automate ongoing vocabulary monitoring so gaps are detected continuously.

**What to Build**:

1. **Feedback Loop Script** (`src/vocabulary_feedback.py`):
   - Periodically fetch recent Shortcut stories from conversations (e.g., last 30 days)
   - Aggregate story labels and epics
   - Compare against current vocabulary
   - Detect new labels not in vocabulary
   - Rank by occurrence frequency
   - Generate gap report

2. **Human Review Interface** (CLI or simple report):
   - Present high-priority vocabulary gaps
   - For each gap, show:
     - Label name
     - Occurrence count
     - Example conversations
     - Suggested vocabulary entry
   - Allow human to: Approve | Reject | Modify | Skip
   - Approved additions → update vocabulary config

3. **Scheduling / Trigger Mechanism**:
   - CLI command: `python -m src.vocabulary_feedback --days 30`
   - Optional: Cron job or scheduled task for weekly checks
   - Optional: GitHub issue auto-creation for high-priority gaps

4. **Version Control for Vocabulary**:
   - Track vocabulary changes in git
   - Include change log: "Added 'analytics_dashboard' - 15 occurrences in Nov 2025"

**OUTPUT**:

- `src/vocabulary_feedback.py` - Functional feedback loop script
- `docs/vocabulary_feedback_guide.md` - How to run and interpret reports
- Updated vocabulary config with any approved additions from Phase 5D

---

## PHASE 5F: ITERATIVE REFINEMENT (IF ACCURACY < 85%)

**Goal**: If theme extraction accuracy is below 85%, improve it.

**Refinement Approach**:

1. **Analyze mismatches from Phase 5C**:
   - Are mismatches due to vocabulary gaps? (Add missing themes)
   - Are mismatches due to extraction logic issues? (Refine prompts or matching rules)
   - Are mismatches due to granularity differences? (Shortcut uses more specific labels)

2. **Implement targeted fixes**:
   - **For vocabulary gaps**: Add high-priority themes from Phase 5D
   - **For extraction issues**: Refine LLM prompts or matching logic in `src/themes.py`
   - **For granularity issues**: Add hierarchical vocabulary (parent/child themes)

3. **Re-test on validation set**:
   - Re-run theme extraction with updated vocabulary/logic
   - Recalculate accuracy metrics
   - Update **ITERATIONS** and **CURRENT_ACCURACY** in this file header

4. **Repeat** until accuracy ≥ 85% OR 3 refinement attempts completed

**If stuck after 3 attempts**: Output <promise>PHASE5_PLATEAU_REACHED</promise> and proceed to Phase 5G with current best results

---

## PHASE 5G: FINAL REPORT & DELIVERABLES

**Goal**: Package all validation findings and improvements.

Generate `phase5_final_report_YYYY-MM-DD.md` containing:

**Executive Summary**

- Theme extraction accuracy achieved: X%
- Vocabulary gaps identified: Y high-priority, Z total
- Feedback loop operational: Yes/No
- Recommendations for next steps

**Accuracy Analysis**

- Overall precision, recall, F1 score
- Per-product-area accuracy breakdown
- Best-performing product areas (and why)
- Worst-performing product areas (and why)
- Example matches and mismatches

**Vocabulary Gap Analysis**

- High-priority additions recommended: [list]
- Medium/low-priority additions: [list]
- Patterns in gaps (new features? granularity? product areas?)
- Proposed vocabulary additions (structured format)

**Feedback Loop Documentation**

- How to run: `python -m src.vocabulary_feedback --days 30`
- Interpreting reports
- Approval workflow for vocabulary changes
- Recommended monitoring cadence (weekly? monthly?)

**Code Changes**

- Files created: `src/vocabulary_feedback.py`, validation scripts
- Files modified: vocabulary config (if additions made)
- Testing recommendations

**Next Steps**

- Immediate actions (approve high-priority vocabulary additions)
- Ongoing monitoring (schedule feedback loop runs)
- Future improvements (if accuracy < 100%)

---

## SUCCESS CRITERIA

✓ Ground truth dataset loaded (200+ conversations with `story_id_v2`)
✓ Theme extraction run on all ground truth conversations
✓ Accuracy measured: precision, recall, F1 ≥ 85%
✓ Vocabulary gaps identified and prioritized
✓ Feedback loop script operational and documented
✓ All deliverables generated (reports, code, documentation)
✓ Clear recommendations for vocabulary improvements

---

## IF YOU GET STUCK

**API/Data Issues**:

- If Intercom API fails, check .env credentials and rate limits
- If Shortcut API fails, verify story_id_v2 values are valid
- Document any data structure surprises

**Accuracy Below 85%**:

- If accuracy plateaus after 3 refinement attempts:
  - Document current accuracy and remaining mismatch patterns
  - Explain which issues are solvable vs. fundamental limitations
  - Provide specific recommendations (e.g., "Need human review of Shortcut labeling consistency")
  - Output <promise>PHASE5_PLATEAU_REACHED</promise>

**Insufficient Ground Truth Data**:

- If API is exhausted and you have <100 conversations with `story_id_v2`:
  - Document exactly how many you found
  - Explain why this limits statistical validity
  - Recommend alternative validation approaches (manual spot-checking, synthetic tests)
  - Do NOT proceed with fake data

**Ambiguous Shortcut Labels**:

- If Shortcut labels are inconsistent or unclear, document examples
- Flag for human review rather than making assumptions

---

## WHEN COMPLETE

**Verify ALL of these are true:**

- Accuracy ≥ 85% (or plateau documented with <promise>PHASE5_PLATEAU_REACHED</promise>)
- All phases completed with documented outputs
- Vocabulary gaps identified and prioritized
- Feedback loop script operational
- Final report generated with actionable recommendations
- Code changes ready for production review

**Then output**: <promise>PHASE5_VALIDATION_COMPLETE</promise>

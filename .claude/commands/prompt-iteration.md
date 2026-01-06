---
description: Log a new prompt version with accuracy metrics
argument-hint: [version-number]
---

# Prompt Iteration

Document a new classification prompt version in docs/prompts.md.

## Version: $ARGUMENTS

## Steps

1. **Read current prompt state** from docs/prompts.md

2. **Gather information about the new version**:
   - What changed from the previous version?
   - Why was this change made?
   - What accuracy metrics were measured?

3. **Update docs/prompts.md**:

   a. If this is the production prompt, update "Current Production Prompt" section

   b. Add entry to "Prompt Iteration History":
   ```markdown
   ### v[VERSION] (YYYY-MM-DD)
   - Changes: [what changed]
   - Rationale: [why]
   - Accuracy: [X]% vs human baseline
   - Notes: [any observations]
   ```

   c. Update "Accuracy Metrics" table with new measurement

4. **If accuracy improved significantly**, consider:
   - Updating the production prompt
   - Noting what worked in CLAUDE.md for future reference

5. **Report**:
   - Summary of changes
   - Comparison to previous version
   - Recommendation (adopt as production / needs more testing / revert)

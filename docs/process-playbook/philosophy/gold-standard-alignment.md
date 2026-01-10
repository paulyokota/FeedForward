# Gold Standard Alignment

> The gold standard document is the source of truth. Evaluators are proxies that should measure what the gold standard defines, not substitute heuristics.

---

## The Principle

**When authoritative documentation exists, implementation must match.**

If your code says `25` but your design doc says `6-10`, that's a bug, not a judgment call.

---

## The Problem

When building automated quality checks, it's tempting to use simple heuristics (regex patterns, percentage targets, keyword matching). These work for initial implementation but can diverge from what the gold standard actually defines.

**Signs you're gaming evaluators instead of improving quality:**
- Guidance includes "include these signal words so the evaluator detects..."
- Improvements come from keyword placement, not content structure
- Gold standard defines something by PURPOSE but evaluator uses regex patterns
- Targets are arbitrary numbers not from any specification

---

## The Fix

When evaluator scores don't improve despite tuning, or when improvements feel like "teaching to the test":

1. **Read the gold standard document**
2. **Compare what it ACTUALLY says vs what the evaluator measures**
3. **If they diverge, fix the EVALUATOR to match the gold standard**
4. **Then tune implementation to genuinely align with the gold standard**

---

## Case Study: Content Type Detection

### Problem

**Gold standard said**:
- How-To content: PURPOSE is "showing how to achieve a specific result"
- Comparison content: PURPOSE is "helping someone choose between options"

**Evaluator did**:
```
// Regex-based detection
const howToPatterns = /\b(how\s+to|guide|tutorial|step(?:-by-step)?)\b/i;
```

**What went wrong**:
- "How to fix login errors" matched but is actually problem-solution content
- Tuning focused on "include 'how to' in titles" = keyword stuffing
- Scores improved but we were gaming the test

**Fix**: Purpose-based detection that evaluates INTENT, not keywords. Scores jumped significantly.

---

## Case Study: Made-Up Metrics

### Problem

**Gold standard said**: Content types belong in appropriate funnel stages

**Evaluator did**:
```
const FUNNEL_TARGETS = {
  TOFU: { target: 40, tolerance: 30 },
  MOFU: { target: 35, tolerance: 30 },
  BOFU: { target: 25, tolerance: 25 },
};
```

**What went wrong**:
- 40/35/25% targets were implementation defaults, not from any specification
- Evaluator penalized content that didn't match arbitrary percentages
- Good content could score poorly just for having "wrong" distribution

**Fix**: Renamed metric, now checks if content TYPE matches funnel stage assignment, not percentages.

---

## Cross-Document Tensions

When multiple gold standards exist, they can conflict. Resolution order:

1. **Core requirements win** - Foundational docs over style guides
2. **Style guides inform HOW, not WHAT** - Personality within structure, not structure override

### Example: Structure vs Style

| Document | What It Says |
|----------|--------------|
| Core Framework | "Lead with direct answer in first 40-60 words" |
| Style Guide | "Hook the reader first - open with story/question" |

Four documents say "answer first." One document might say "hook first." This isn't close.

**Resolution**: Answer-First wins. Style guide's job is to make the answer *engaging*, not to *delay* the answer.

---

## Primary Sources Over Secondary Sources

When gold standards drift, trace back to PRIMARY sources.

**The Problem**: Secondary sources (processed guides, derived docs) accumulate interpretation. Each person who touches the doc adds their understanding. Over time, "short sentences" becomes "15-20 word average" - a completely different claim.

**The Fix**:
1. **Store primary sources separately** - Original samples in a dedicated location
2. **Trace the provenance chain** - Which doc was derived from which?
3. **Separate evidence from extrapolation** - What samples show vs how to scale
4. **When auditing, start at primary** - Don't just check the processed guide

**Example of Evidence vs Extrapolation**:

```json
{
  "sourceMetrics": {
    "_note": "Derived from original samples",
    "sentenceLength": { "average": 8.9 }
  },
  "scaledTargets": {
    "_note": "EXTRAPOLATION for longer content format",
    "sentenceLength": { "target": "12-15" }
  }
}
```

The first section is evidence. The second is inference. Keeping them separate prevents future drift.

---

## When to Apply This

- **Writing new evaluators**: Start from gold standard, not from "easy to implement"
- **Tuning implementations**: If you're adding keywords for detection, stop and check the evaluator
- **Debugging low scores**: Before blaming the content, verify the evaluator measures the right thing
- **Reviewing others' work**: Ask "does this measure what the gold standard defines?"

---

## Checklist for Evaluator Work

Before adding or modifying any evaluator:

- [ ] **What's the actual goal?** (Not "pass the check" - what reader/user value?)
- [ ] **What does the gold standard say?** (Quote the specific text)
- [ ] **Does this evaluator measure that?** (Be honest)
- [ ] **Could this be gamed without improving quality?** (Keyword stuffing, etc.)
- [ ] **What happens when it fails?** (Fail fast, not silent degradation)

---

## Code Review Questions

When reviewing evaluator changes, ask:

1. **"Does this measure the actual thing, or a proxy?"**
   - If proxy: is it validated against real quality?

2. **"What happens when content fails?"**
   - Does it surface the gap? Or hide it?

3. **"Could content game this check?"**
   - If keyword-based: could prompts just add keywords?
   - If threshold-based: could we lower it when convenient?

4. **"Is this threshold from the gold standard or invented?"**
   - If invented: document the rationale
   - If from gold standard: cite the source

---

## Customization

### Setting Up Gold Standard Tracking

1. **Identify your gold standards** - Which docs are authoritative?
2. **Document the hierarchy** - Which wins when they conflict?
3. **Store primary sources** - Keep originals separate from processed versions
4. **Add provenance** - Mark where numbers/targets come from
5. **Regular audits** - Quarterly check that implementation matches docs

### Example Gold Standard Registry

```markdown
## Gold Standard Documents

| Document | Authority | Last Verified |
|----------|-----------|---------------|
| Core Requirements Doc | HIGHEST | YYYY-MM-DD |
| Technical Spec | HIGH | YYYY-MM-DD |
| Style Guide | MEDIUM | YYYY-MM-DD |
| Team Conventions | LOW | YYYY-MM-DD |
```

---

## Related

- `proxy-metrics.md` - Decision tree for when proxies fail
- `../gates/test-gate.md` - Tests as quality gate
- `../review/five-personality-review.md` - Quality Champion's role

---

## Summary

| Situation | Action |
|-----------|--------|
| Evaluator score not improving | Check if evaluator matches gold standard |
| Adding keywords to pass checks | STOP - you're gaming the evaluator |
| Two docs conflict | Check resolution hierarchy |
| Threshold seems arbitrary | Trace back to gold standard source |
| Auditing quality | Start from primary sources |

**The rule: Gold standard document is the source of truth. Evaluators serve it, not replace it.**

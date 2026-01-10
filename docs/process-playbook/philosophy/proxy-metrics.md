# Proxy Metrics Philosophy

> Passing evaluator checks is NOT the goal. Gold standard output quality IS the goal. Evaluators are servants of that goal, not masters.

---

## The Core Problem

We build proxy metrics (word counts, detection patterns, evaluator scores) to measure quality. But then:

1. The system optimizes for passing proxies rather than achieving quality
2. When proxies fail, we lower thresholds instead of fixing root causes
3. Goodhart's Law kicks in: "When a measure becomes a target, it ceases to be a good measure"

---

## Research Findings

### Goodhart's Law in AI/ML Systems

[OpenAI's research](https://openai.com/index/measuring-goodharts-law/) shows that when optimizing against a proxy, there's a critical point where further optimization *decreases* performance on the true objective.

Key insight: **The more you optimize a proxy, the worse it becomes as a measure of the real thing.**

### Gaming Manifests Everywhere

From [AI leaderboard research](https://blog.collinear.ai/p/gaming-the-system-goodharts-law-exemplified-in-ai-leaderboard-controversy):
- Models optimized for BLEU scores produce worse translations
- AI agents learn to game reward signals rather than accomplish tasks
- Systems optimize for detectable signals rather than actual quality

---

## Warning Signs: Approaching Goodhart Territory

### Warning Sign 1: Evaluator Divergence from Gold Standard

The first signal is usually a gap between what the evaluator rewards and what the gold standard defines.

**Example**:
- **Gold standard**: Content types defined by PURPOSE
- **Evaluator**: Detects keywords in titles
- **Gap**: Content passes keyword check without matching PURPOSE
- **Risk**: System optimizes for keywords instead of actual content type

**How to catch it**: Periodically run samples through both evaluator AND manual gold standard check. If scores diverge, the evaluator is drifting.

### Warning Sign 2: Metric Improvement Without Quality Improvement

The system passes more checks, but output quality is flat or declining.

**How to catch it**:
- Track: evaluator score over time vs human-reviewed quality samples
- Alert if: evaluator score up but quality match down
- Action: Recalibrate evaluator, don't lower thresholds

### Warning Sign 3: Threshold Creep

Thresholds get quietly lowered without documented rationale.

**Example**:
- Original: `min: 2`
- After first failure: `min: 1.5`
- After second failure: `min: 1`
- After third failure: `min: 0.5`

Each change justified as "realistic," but cumulatively you've drifted 75% off the gold standard.

**How to catch it**:
- All threshold changes require documented rationale
- Thresholds below gold standard baseline need explicit approval
- Maintain a changelog for threshold history

### Warning Sign 4: Conditional Logic That Hides Failure

Code that looks like "graceful degradation" but is actually failure masking.

**Danger patterns**:
```
// "Close enough" logic
if (count > target * 0.8) return { pass: true };

// Silent overrides
if (passRate < 0.7) {
  scores = scores.map(s => s * fudgeFactor);
}

// Accumulated tolerance
const tolerance = 0.9 * 0.9 * 0.9; // Multiple "small" tolerances = 72% of target
```

Any of these means you're hiding quality gaps instead of fixing them.

---

## Decision Tree: When Standards Aren't Met

```
Standards not met
       |
       v
+------------------------------------------------------+
| 1. QUESTION THE MEASUREMENT                          |
|    Is our proxy measuring the right thing?           |
|    - Detection pattern vs "actual quality signal"    |
|    - Word count vs "comprehensive coverage"          |
|    - Evaluator score vs "reader value"               |
+------------------------------------------------------+
       | If proxy is valid...
       v
+------------------------------------------------------+
| 2. TRY CREATIVE ALTERNATIVES                         |
|    Different approaches to achieve the actual goal   |
|    - Different detection methods                     |
|    - Additional steps in the pipeline                |
|    - Different sources or inputs                     |
+------------------------------------------------------+
       | If alternatives exhausted...
       v
+------------------------------------------------------+
| 3. FAIL FAST WITH CLEAR SIGNAL                       |
|    Reject output, surface the gap, fix upstream      |
|    - Task shows "quality gap" status                 |
|    - Root cause gets tracked as issue                |
|    - Don't hide failure behind "pass"                |
+------------------------------------------------------+
       |
       v
+------------------------------------------------------+
| 4. NEVER: SILENTLY LOWER THE BAR                     |
|    X Reduce thresholds so things "pass"              |
|    X Hide quality gaps behind overrides              |
|    X Optimize for green checkmarks                   |
+------------------------------------------------------+
```

---

## Anti-Gaming Evaluation Design Patterns

### Pattern 1: Purpose-Based, Not Keyword-Based

**Vulnerable design**:
```
// GAMEABLE: Just add keywords
if (title.includes("how to")) {
  contentType = "instructional";
}
```

**Anti-gaming design**:
```
// RESISTANT: Evaluate PURPOSE
const contentType = classifyByPurpose(content);
// Determines: "teaches HOW" vs "helps CHOOSE" based on content
```

### Pattern 2: Multimodal Validation

**Vulnerable design**:
```
// GAMEABLE: Format in specific patterns
const count = text.match(/"[^"]+"/g).length;
```

**Anti-gaming design**:
```
// RESISTANT: Multiple signals
const signal1 = countPattern1(text);
const signal2 = countPattern2(text);
const signal3 = semanticCheck(text);

if (signal1 + signal2 + signal3 < threshold) {
  // Fail - can't game with single trick
}
```

### Pattern 3: Outcome Comparison, Not Input Inspection

**Vulnerable design**:
```
// GAMEABLE: Check if prompt mentions the thing
if (prompt.includes("use more quotes")) {
  // Trust it
}
```

**Anti-gaming design**:
```
// RESISTANT: Measure actual behavior
const before = measureMetric(v1);
const after = measureMetric(v2);

if (after < before * threshold) {
  // Revision didn't actually improve
}
```

### Pattern 4: Hardcoded Baseline Thresholds

**Vulnerable design**:
```
// GAMEABLE: Adjustable thresholds drift lower
const MIN = config.get("min"); // Can be changed
```

**Anti-gaming design**:
```
// RESISTANT: Baseline hardcoded, can only increase
const GOLD_STANDARD_MIN = 2; // From gold standard, never reduced
const configMin = Math.max(GOLD_STANDARD_MIN, config.get("min"));

if (count < GOLD_STANDARD_MIN) {
  throw new Error("Falls below gold standard baseline");
}
```

### Pattern 5: Transparent Decay Signals

**Vulnerable design**:
```
// GAMEABLE: Hide the decay
if (cycle > 5) {
  // Silently reduce requirements
  return adjusted > 0.4;
}
```

**Anti-gaming design**:
```
// RESISTANT: Make decay visible
if (passRate < threshold && cycle > 8) {
  return {
    status: "QUALITY_GAP",
    passRate: passRate,
    reason: "Failed to converge despite 8 cycles",
    signal: "INVESTIGATE_ROOT_CAUSE"
  };
}
```

---

## Mitigation Strategies

From [ML metrics research](https://www.sciencedirect.com/science/article/pii/S2666389922000563):

1. **Use multiple metrics** - No single metric captures quality
2. **Combine quantitative with qualitative** - Numbers need human validation
3. **Test on sliced data** - Global metrics mask fine-grained problems
4. **Verify causality** - Correlation with quality != causing quality
5. **Early stopping** - Know when optimization starts hurting
6. **Design for resistance** - Use the anti-gaming patterns above

---

## Fail Fast vs. Degrade Gracefully

From [RAG evaluation research](https://www.evidentlyai.com/llm-guide/rag-evaluation):

- **Fail fast** when: The proxy is measuring the core goal (quality, safety)
- **Degrade gracefully** when: Edge cases and unusual inputs
- **Never degrade silently** - Always surface the gap

A "passed" output with poor quality is worse than a failed task that surfaces the quality gap.

---

## Examples: Right vs. Wrong Response

### Detection Pattern Failing

**Wrong**: Lower detection threshold
```
// BAD: Hides quality gap
min: 1  // was 2
```

**Right**: Question the measurement
- Is the pattern detecting the right thing?
- Should the pipeline explicitly generate what we're detecting?
- Are we looking in the right places?

**Right**: Creative alternative
- Different detection approach
- Additional pipeline step
- Different data sources

**Right**: Fail fast if alternatives exhausted
```
if (detected < GOLD_STANDARD_MIN) {
  throw new QualityError("Insufficient - needs improvement");
}
```

### Word Count Under Target

**Wrong**: Accept below-target output
```
// BAD: "Close enough"
if (wordCount > targetMin * 0.7) return { pass: true };
```

**Right**: Question the measurement
- Is word count the right proxy for "comprehensive"?
- Should we measure topic coverage instead?

**Right**: Creative alternative
- Require specific subtopics to be covered
- Use outline completeness as primary metric

**Right**: Fail and fix
- Return to generation with specific gaps identified
- "Output needs: [missing topic 1], [missing topic 2]"

---

## Checklist for Evaluator/Threshold Work

Before adding or modifying any evaluator or threshold:

- [ ] **What's the actual goal?** (Not "pass the check" - what user value?)
- [ ] **Is this proxy valid?** Does it correlate with actual quality?
- [ ] **What happens when it fails?** Fail fast? Creative alternative? Never silent degradation.
- [ ] **Is there a floor?** Minimum threshold that can never be lowered?
- [ ] **Is the gap visible?** Quality gaps must surface, not hide behind "pass"
- [ ] **Is it gaming-resistant?** Can content game this check without improving quality?
- [ ] **Multiple metrics?** Does this work alongside other checks, not in isolation?

---

## Key Principle

> **"When a proxy fails repeatedly, suspect the proxy before lowering the bar."**

Ask:
- Is the proxy measuring what we actually care about?
- Is there a better signal for the true goal?
- What creative approaches could achieve the goal differently?

---

## Customization

### Setting Up Proxy Monitoring

1. **Identify your proxies** - What automated checks do you have?
2. **Map to gold standards** - What is each proxy trying to measure?
3. **Set baselines** - What's the minimum threshold from gold standard?
4. **Track changes** - Log all threshold modifications with rationale
5. **Regular audits** - Compare proxy scores to manual quality assessment

### Threshold Change Log Template

```markdown
## Threshold Changes

| Date | Metric | Old | New | Rationale | Approved By |
|------|--------|-----|-----|-----------|-------------|
| YYYY-MM-DD | [metric] | X | Y | [why] | [who] |
```

---

## Related

- `gold-standard-alignment.md` - When evaluators diverge from gold standard
- `../review/reviewer-profiles.md` - Quality Champion's proxy metrics focus
- `../gates/test-gate.md` - Tests as quality gate

---

## Sources

Research informing this document:
- [OpenAI - Measuring Goodhart's Law](https://openai.com/index/measuring-goodharts-law/)
- [Collinear AI - Gaming the System](https://blog.collinear.ai/p/gaming-the-system-goodharts-law-exemplified-in-ai-leaderboard-controversy)
- [ScienceDirect - Reliance on Metrics is a Fundamental Challenge for AI](https://www.sciencedirect.com/science/article/pii/S2666389922000563)
- [Google Cloud - Guidelines for High-Quality ML Solutions](https://cloud.google.com/architecture/guidelines-for-developing-high-quality-ml-solutions)
- [Evidently AI - RAG Evaluation Guide](https://www.evidentlyai.com/llm-guide/rag-evaluation)

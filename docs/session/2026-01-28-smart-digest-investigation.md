# Session: Smart Digest Investigation

**Date**: 2026-01-28
**Branch**: main
**Duration**: ~2 hours
**Output**: GitHub Issue #144

## Goal

Investigate PM Review excerpt quality and plan improvements for story coherence.

## Investigation Flow

### 1. PM Review Deep Dive

Started by explaining what PM Review does (validates theme groups using "SAME_FIX test"). Discovered PM Review receives `source_body[:500]` - just the first customer message truncated.

### 2. Digest Discovery

Found `customer_digest` exists in `conversations.support_insights` JSONB column. It combines first message + "most specific" message selected by keyword scoring. But PM Review doesn't query it - that's the gap.

### 3. Digest Creation Analysis

Traced `build_customer_digest()` in `digest_extractor.py`. Uses heuristic scoring:

- +3 for quoted errors
- +2 for error keywords
- +2 for error codes
- +1 for feature nouns
- -2 for generic text

Crude but fast (no LLM). Misses context, multiple relevant messages, support response hints.

### 4. A/B Testing

Ran PM Review on real `pinterest_video_upload_failure` group (4 conversations):

| Test | Excerpt           | Confidence |
| ---- | ----------------- | ---------- |
| A    | source_body[:500] | 0.4        |
| B    | digest[:500]      | 0.7        |
| C    | digest[:800]      | 0.8        |

Same decisions but confidence doubled. LLM could cite specific error messages vs vague inferences.

### 5. Theme Extraction Limitation

Discovered theme extraction also only sees heuristic digest, not full conversation:

```python
source_text = customer_digest.strip()  # or source_body fallback
```

So signature assignment, symptom extraction, root cause hypotheses - all from limited context.

### 6. Product Context Truncation

Disambiguation docs total 68K chars but only 10K passed to theme extraction prompt. Most scheduler disambiguation (Pin Scheduler vs Multi-Network vs legacy) gets chopped.

## Key Decisions

1. **Unified LLM call** - Theme extraction + smart digest in one call seeing full conversation. Already paying for LLM call, just give it better input.

2. **Preserve raw evidence** - Output `diagnostic_summary` (interpretation) AND `key_excerpts` (verbatim quotes). Addresses concern about single point of failure if summarizer makes bad assumptions.

3. **Let LLM decide excerpt count** - No arbitrary cap on key_excerpts. Some conversations have one key message, others have many.

4. **Separate optimized context doc** - Create `pipeline-disambiguation.md` for LLM consumption. Keep canonical product docs static as reference.

5. **Context usage instrumentation** - Log `context_used` and `context_gaps` to build feedback loop for iterating on disambiguation doc.

## What Was Considered But Not Chosen

- **Improving heuristics** - Incremental, cheap, but fundamentally limited. Still picking ONE message by surface patterns.
- **Separate digest LLM call** - Adds latency and cost for something that can be combined with existing theme extraction.
- **Hard cap on excerpts** - Would lose signal for conversations with multiple relevant details.
- **Modifying canonical product docs** - Want stable reference, tune separately.

## Artifacts Created

- **GitHub Issue #144** - Full implementation plan with:
  - Investigation journey
  - 6 design decisions with rationale
  - 4-phase implementation plan
  - Open questions
  - Files to modify
  - Success criteria
  - Scheduler disambiguation table

## Follow-Up Items

1. Trace story evidence flow before implementation (backwards compatibility)
2. Measure p99 conversation length (token limit edge cases)
3. Decide on backfill strategy for existing themes
4. Consider A/B validation (parallel pipelines)

## Session Stats

- No code written (investigation/planning session)
- 1 GitHub issue created
- Voice mode used for collaborative discussion
- Multiple real pipeline runs examined (Run 91)

# Issue #153: Phase 2 Complete

**Date**: 2026-01-30
**Status**: Phase 2 DONE, Phase 3 ready to start

---

## What Was Accomplished

### Phase 1 (Previously Complete)

- Extracted terms from 543 themes
- Found 325 candidate pairs with semantic similarity
- Output: `data/vocabulary_enhancement/phase1_terms.json`

### Phase 2 (Just Completed)

- **Processed ALL 325 pairs** (critical - previous attempts only did 3-6)
- Used 5 parallel agents to validate against codebase map
- Applied SAME_FIX test: Would one code change fix both objects?
- Output: `data/vocabulary_enhancement/phase2_validations.json`

**Results:**

- DISTINCT: 292 pairs (different services/implementations)
- SAME: 33 pairs (same service)

---

## Key Validated Distinctions for Phase 3

| Pair                                   | Service A              | Service B            | SAME_FIX |
| -------------------------------------- | ---------------------- | -------------------- | -------- |
| draft vs scheduled_pin                 | bach/bachv3 (DynamoDB) | tack (Pinterest API) | NO       |
| draft vs turbo_pin                     | bachv3 /drafts         | bachv3 /turbo        | NO       |
| scheduled_pin vs turbo_pin             | tack                   | bachv3 turbo         | NO       |
| scheduled_pin vs smartpin              | tack                   | scooby + bach        | NO       |
| pinterest_account vs instagram_account | tack                   | zuck                 | NO       |

---

## Service Mapping Reference

```
tack: pin, scheduled_pin, board, pinterest_account, keyword
bach/bachv3: draft, smartpin, turbo_pin, smartloop, community, time_slot
zuck: instagram_account, facebook_page
pablo: image, video
scooby: url, link, website, smartpin
gandalf: token, account
dolly: design, template
aero: smart.bio
```

---

## Ambiguous Terms (Need Clarification in Prompts)

- **pin**: Could mean draft, scheduled_pin, smartpin, or turbo_pin
- **account**: Could mean pinterest_account, instagram_account, or tailwind_account
- **post**: Platform-agnostic term
- **content**: Very generic

---

## Next Step: Phase 3

**Goal**: Codify validated distinctions into `config/theme_vocabulary.json`

From GitHub Issue #153:

```json
"term_distinctions": {
  "object_type": {
    "drafts_vs_pins": {
      "why_different": "Drafts are in DynamoDB, pins are in scheduled posts API",
      "guidance": "When users mention bulk delete, ask: drafts or scheduled pins?"
    }
  }
}
```

**Input**: `data/vocabulary_enhancement/phase2_validations.json`
**Output**: Updated `config/theme_vocabulary.json` with term_distinctions section

---

## Files

**Phase 1 output**: `data/vocabulary_enhancement/phase1_terms.json`
**Phase 2 output**: `data/vocabulary_enhancement/phase2_validations.json`
**Target for Phase 3**: `config/theme_vocabulary.json`

---

## Critical Lesson Learned

Previous attempts failed because I arbitrarily limited scope (3 pairs, then 6 pairs) when the spec said "all 325 pairs". The user had to repeat "process all 325 pairs" many times before I got it right. The successful approach used 5 parallel agents to process all pairs.

---

_Session state for Issue #153 continuation_

# Issue #153: Phase 2 COMPLETE (Code Path Verified)

**Date**: 2026-01-29
**Status**: Phase 2 DONE, Phase 3 ready

---

## What Was Done

Phase 2 validated ALL 325 candidate pairs by **reading actual code and tracing execution paths** - not by applying rules to assumptions.

### Method

1. Launched 6 explore agents to trace code paths for all 28 unique objects
2. For each object, found: handler function, what it calls, what storage it uses
3. Applied SAME_FIX test: "Would ONE code change fix bugs in BOTH objects?"

### Results

- **SAME_FIX=true: 6 pairs**
- **SAME_FIX=false: 270 pairs**
- **AMBIGUOUS: 49 pairs**

---

## SAME_FIX=true Pairs (verified by code tracing)

| Pair                       | Why Same                                |
| -------------------------- | --------------------------------------- |
| post vs scheduled_pin      | Both use `PostFacet.put()` in tack      |
| scheduled_pin vs draft     | Both use `PostFacet.put()` in tack      |
| post vs draft              | Both use `PostFacet.put()` in tack      |
| SmartPin vs smartpin       | Case variant - same code                |
| title vs description       | Both use `parseResult()` in ghostwriter |
| pinterest_account vs token | Both use `TokenV5Facet.put()` in tack   |

---

## Key Findings from Code Tracing

### TACK (Pinterest)

- **pin**: READ-ONLY from Pinterest API. Created as side effect when post is published.
- **scheduled_pin**: Post with status='queued' -> `PostFacet.put()`
- **draft**: Post with status='draft' -> `PostFacet.put()`
- **post**: -> `createPost()` -> `PostFacet.put()`
- **board**: READ-ONLY from Pinterest API
- **pinterest_account**: -> `TokenV5Facet.put()`
- **keyword**: READ-ONLY from Pinterest Trends API
- **token**: -> `TokenV5Facet.put()`

### ZUCK (Facebook/Meta)

- **instagram_account**: NOT a real object - boolean field from Graph API `getAccounts()`
- **facebook_page**: String literal for postType, actual storage is `Repository.post.put()`

### AERO (Backend)

- **turbo_pin**: `Postgres.BoostedPins` table
- **smartpin/SmartPin**: `Datastore.smartPinSettings` (MySQL)
- **time_slot**: `Datastore.publisherTimeSlots` (MySQL)
- **community**: External API to `tribe_content_documents`
- **design**: Updates destinationless drafts
- **smart.bio**: `Instagram.linkInBioPages` (MySQL)
- **account**: `Datastore.userAccounts` (MySQL)
- **feature**: `Datastore.userOrganizationFeatures` (MySQL)
- **smartloop**: NOT FOUND in codebase
- **content**: AMBIGUOUS - no dedicated table

### SCOOBY (URL scraping)

- **url**: `GET /scrape` -> `performScrape()` -> `scrapeHttp()`
- **link**: `GET /blogs-page` -> `getAllBlogs()` -> WordPress API
- **website**: `GET /detect` -> `detectPlatformV2()`

### PABLO (Media)

- **image**: `transformImage()` -> Sharp library (SYNC)
- **video**: `transformVideo()` -> MediaConvert (ASYNC)

### GHOSTWRITER (AI text)

- **title**: `parseResult()` extracts from JSON
- **description**: `parseResult()` extracts from JSON (SAME FUNCTION)

---

## Critical Distinction: pin vs scheduled_pin

**These are DIFFERENT despite both being in tack:**

- `pin` = Result AFTER publishing. Read from Pinterest API. PinFacet.
- `scheduled_pin` = Queue item BEFORE publishing. Stored in DynamoDB. PostFacet.

A bug in PostFacet would NOT affect pin retrieval. A bug in Pinterest API integration would NOT affect scheduled_pin storage.

---

## Files

- **Phase 1 output**: `data/vocabulary_enhancement/phase1_terms.json` (325 pairs)
- **Phase 2 output**: `data/vocabulary_enhancement/phase2_validations.json`
- **Code paths**: `data/vocabulary_enhancement/code_paths.json`

---

## Phase 3 Requirements

**Goal**: Codify validated distinctions into `config/theme_vocabulary.json`

**Input**: `data/vocabulary_enhancement/phase2_validations.json`

**Output structure** (from GitHub Issue #153):

```json
"term_distinctions": {
  "object_type": {
    "drafts_vs_pins": {
      "why_different": "Drafts stored in PostFacet (DynamoDB), pins read from Pinterest API",
      "guidance": "When users mention bulk operations, ask: saved drafts or published pins?"
    }
  }
}
```

**Key distinctions to codify**:

1. draft vs pin (PostFacet vs Pinterest API)
2. scheduled_pin vs pin (PostFacet vs Pinterest API)
3. scheduled_pin vs turbo_pin (tack vs aero, DynamoDB vs Postgres)
4. image vs video (Sharp sync vs MediaConvert async)
5. pinterest_account vs instagram_account (tack vs zuck)
6. instagram_account vs facebook_page (Graph API field vs Post storage)

---

## Lesson Learned

The SAME_FIX test requires **tracing actual code execution**, not:

- Grepping for where terms appear
- Assuming "same service = same fix"
- Assuming "same table = same fix"
- Building mappings and applying rules

The only valid approach: Read the handler, see what function it calls, follow the calls to storage.

---

_Session state for Issue #153 Phase 3_

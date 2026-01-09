# Coda Research Repository Analysis

**Document**: Tailwind Research Ops
**Doc ID**: `c4RRJ_VLtW`
**Analysis Date**: 2026-01-09

## Overview

The Coda research repository contains UX research data from user interviews, including synthesized insights, proto-personas, pain points, and feature requests. This document analyzes the repository structure and content to inform a theme extraction strategy for FeedForward.

## Repository Structure

### Content Types

| Type                      | Count | Content Format                                      | Value for Themes |
| ------------------------- | ----- | --------------------------------------------------- | ---------------- |
| **AI Summary**            | 27    | Structured markdown with quotes, personas, insights | **HIGH**         |
| **Note/Debrief**          | 16    | Templates (mostly unfilled)                         | LOW              |
| **Contact (participant)** | 21    | Interview session pages                             | MEDIUM           |
| **Discovery Learnings**   | 1     | Synthesized product insights                        | **HIGH**         |
| **Research Questions**    | 1     | Research priorities/questions                       | MEDIUM           |
| **Research Plans**        | 2     | Study methodology docs                              | LOW              |
| **Moderator Guides**      | 4     | Interview scripts                                   | LOW              |

### Page Hierarchy

```
Start Here!
├── UXR Visual Roadmap
│   └── Quarterly Planning
│       ├── Cycle 7 & 8 UXR Planning
│       └── Bank of Research Questions
└── Research Overview
    ├── Research Roadmap
    │   └── Dashboard
    ├── Epics/Phases
    └── Projects/Studies
        └── Content Library / Site Pinner
            └── Phases
                ├── Discovery/Generative
                │   ├── Research Plan
                │   ├── Methods
                │   │   ├── Interviews (with participant pages)
                │   │   └── Email/Chat
                │   └── Discovery Learnings ← RICH CONTENT
                └── Evaluative (Pre-Launch)
                    ├── Research Plan
                    └── Methods
                        └── Interviews (with participant pages)
```

### Tables (100 total)

All 100 tables contain data. Key research tables include:

| Table                                     | Columns | Content                              | Value    |
| ----------------------------------------- | ------- | ------------------------------------ | -------- |
| **Participant: Research Synthesis**       | 11      | Takeaways, WTP data, user feedback   | **HIGH** |
| **Call Tracker_Master: Tailwind Members** | 29      | Email, recordings, business info     | **HIGH** |
| **P4 Synth**                              | 7       | Goals, themes, takeaways             | **HIGH** |
| **Beta Call Synthesis**                   | 15      | Shockers, wish list, confusion areas | **HIGH** |
| **Cycle Research Overview**               | -       | Research cycle tracking              | MEDIUM   |
| **Research Streams**                      | -       | Research stream tracking             | MEDIUM   |

**Sample Table Data** (P4 Synth):

- Goals: "Increase sales, Expand target demographic"
- Takeaways: "Mostly weekly sales/new product releases, those are planned a year in advance"
- Keep in Mind: "Look at it (SEO, keywords, etc) as a guide to see how we're doing"

**Sample Table Data** (Beta Call Synthesis):

- Shockers (Game Changers)
- Wish List
- Areas of Confusion
- Chosen Plan Price/MVP Features
- Creation Time Before/After

## High-Value Content Sources

### 1. AI Summary Pages (27 pages)

AI-generated summaries of user interviews. When populated, they contain:

- **User quotes** with specific pain points
- **Proto-personas** with characteristics and segments
- **Feature requests** framed as problems
- **Workflow analysis** showing friction points
- **Metric impact** analysis
- **Loves/Values** - What users appreciate
- **Needs/Opportunities** - What needs improvement

**Sample content** (from jfahey.cpc@gmail.com):

```
## Friction, Trust, and Learning Curve
"The biggest thing for me — I have to pick the board manually for every single pin."
"It's a very repetitive task. Not exciting. Just something that has to be done."
"I didn't realize I was losing my credits so fast… monthly posts vs monthly designs — that wasn't clear."

## Feature Requests → Problem Framing
- Automated board selection: Help me avoid repetitive board picking so I can schedule faster
- Credit clarity: Help me understand my usage so I don't run out unexpectedly
- Bulk AI copy: Help me generate descriptions in-app so I don't need ChatGPT
```

### 2. Discovery Learnings (1 page, ~10k chars)

Synthesized product insights including:

- **Key user decisions** and what info they need
- **Jobs to be done** (JTBD) framework
- **MVP feature priorities** (critical vs nice-to-have)
- **Information requirements** for users
- **Action requirements** for users

**Sample content**:

```
## What needs/jobs do users have?
[Need] Knowing how much work I have done/have left to do
  - How many [more] Pins do I need to create?
  - Which URL have I not Pinned from in a while?

[Job] Reduce the time/effort needed to identify my next most important task

[Need] Knowing which URLs to create Pins for
  - Which content is going to resonate with my audience?
  - Which content will give me the ROI I'm looking for?
```

### 3. Bank of Research Questions (1 page)

Research priorities and open questions:

- **Analytics** - How users understand/use analytics
- **Mobile** - Pain points, usability
- **Create Pillar** - Content creation pain points
- **Churn prevention** - Understanding why users leave

## API Access

### Content Endpoint

```python
GET /docs/{doc_id}/pages/{page_id}/content
```

Returns structured content with:

- `style`: h1, h2, h3, paragraph, bulletedListItem, numberedListItem
- `content`: Plain text content
- `lineLevel`: Indentation level

### Rate Limits

Standard Coda API limits apply. For bulk extraction, implement:

- Pagination (limit parameter)
- Rate limiting (respect 429 responses)
- Caching for repeated access

## Theme Extraction Strategy

### High-Priority Sources

1. **AI Summaries with content** - 5-10 pages have rich synthesized insights
2. **Discovery Learnings** - Comprehensive product-level insights
3. **Research Questions** - Context for what themes are valuable

### Extractable Theme Types

From this repository, we can extract:

| Theme Type            | Source                       | Example                                                    |
| --------------------- | ---------------------------- | ---------------------------------------------------------- |
| **Pain Point**        | AI Summary quotes            | "I have to pick the board manually for every single pin"   |
| **Feature Request**   | AI Summary feature sections  | "Help me generate descriptions in-app"                     |
| **Workflow Friction** | AI Summary workflow sections | "20 times a minute switching between ChatGPT and the tool" |
| **User Need/Job**     | Discovery Learnings          | "Knowing how much work I have done/left to do"             |
| **Usability Issue**   | AI Summary friction sections | "Credit bucket confusion is a silent churn risk"           |

### Extraction Approach

1. **Fetch AI Summary pages** with >500 chars of content
2. **Parse structured sections** (Loves, Pain Points, Feature Requests, etc.)
3. **Extract quotes** as evidence for themes
4. **Classify by theme type** (bug, feature request, usability, etc.)
5. **Map to product areas** using vocabulary
6. **Deduplicate** against existing Intercom-sourced themes

### Integration with FeedForward Pipeline

```
Coda Research Repo          FeedForward Pipeline
       │                           │
       ▼                           ▼
  AI Summaries ──────────► Theme Extraction
       │                           │
       ▼                           ▼
 Structured Insights ─────► Shortcut Stories
       │                           │
       ▼                           ▼
 User Quotes ─────────────► Evidence in Stories
```

## Content Quality Assessment

| Source                       | Populated | Quality | Ready for Extraction |
| ---------------------------- | --------- | ------- | -------------------- |
| AI Summary (jfahey)          | Yes       | HIGH    | Yes                  |
| AI Summary (krunk02)         | Yes       | HIGH    | Yes                  |
| AI Summary (chris@biohacker) | Yes       | MEDIUM  | Yes                  |
| Discovery Learnings          | Yes       | HIGH    | Yes                  |
| Research Questions           | Yes       | MEDIUM  | Yes                  |
| Debrief pages                | No        | N/A     | No (templates only)  |
| Tables                       | No        | N/A     | No (all empty)       |

## Next Steps

1. **Build Coda client** (`src/coda_client.py`)
   - Fetch pages by type (AI Summary, Learnings)
   - Parse structured content
   - Extract quotes and insights

2. **Create theme extractor** for Coda content
   - Map Coda sections to theme types
   - Extract user quotes as evidence
   - Classify by product area

3. **Integrate with pipeline**
   - Add Coda as data source
   - Merge with Intercom themes
   - Track source attribution

4. **Define refresh cadence**
   - Monitor for new AI Summaries
   - Re-process updated pages

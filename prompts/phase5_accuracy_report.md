# Phase 5C: Accuracy Report

**Generated**: 2026-01-08 14:23:06

## Executive Summary

| Metric | Value |
|--------|-------|
| **Overall Accuracy** | **46.4%** |
| Total Evaluated | 183 |
| Correct Matches | 85 |
| Empty/Skipped | 12 |

**Target**: 85% accuracy
**Status**: NEEDS IMPROVEMENT

---

## Accuracy by Ground Truth Product Area

| Product Area | Total | Correct | Accuracy |
|--------------|-------|---------|----------|
| Pin Scheduler | 30 | 11 | 37% |
| Next Publisher | 22 | 17 | 77% |
| Legacy Publisher | 21 | 15 | 71% |
| Create | 20 | 8 | 40% |
| Analytics | 15 | 6 | 40% |
| Billing & Settings | 13 | 9 | 69% |
| Smart.bio | 13 | 2 | 15% |
| Extension | 11 | 3 | 27% |
| Made For You | 10 | 2 | 20% |
| GW Labs | 8 | 2 | 25% |
| Product Dashboard | 6 | 4 | 67% |
| SmartLoop | 5 | 1 | 20% |
| Communities | 4 | 2 | 50% |
| CoPilot | 2 | 1 | 50% |
| Email | 1 | 1 | 100% |
| Ads | 1 | 0 | 0% |
| Jarvis | 1 | 1 | 100% |

## Accuracy by Extraction Method

| Method | Total | Correct | Accuracy |
|--------|-------|---------|----------|
| llm | 125 | 61 | 49% |
| keywords | 58 | 24 | 41% |

## Accuracy by Confidence Level

| Confidence | Total | Correct | Accuracy |
|------------|-------|---------|----------|
| high | 115 | 60 | 52% |
| low | 1 | 0 | 0% |
| medium | 67 | 25 | 37% |

---

## Example Correct Matches (Top 10)

### Match 1
- **Conversation**: 760511900437
- **Extracted**: scheduling -> **Ground Truth**: Legacy Publisher
- **Method**: llm | **Confidence**: high
- **Preview**: _my scheduled stories files are not showing up on text link..._

### Match 2
- **Conversation**: 760512026956
- **Extracted**: ai_creation -> **Ground Truth**: Create
- **Method**: llm | **Confidence**: high
- **Preview**: _I don't think create is working properly or I'm doing something wrong. I am trying to make multiple pin images at once, it creates designs for me but ..._

### Match 3
- **Conversation**: 760511316286
- **Extracted**: analytics -> **Ground Truth**: Analytics
- **Method**: llm | **Confidence**: high
- **Preview**: _Hi, I help manage the account for Will &amp; Atlas - we have scheduled pins going live through Tailwind, but they're not showing up in Tailwind's repo..._

### Match 4
- **Conversation**: 760511548313
- **Extracted**: analytics -> **Ground Truth**: Analytics
- **Method**: llm | **Confidence**: high
- **Preview**: _I see you big notice about the Pin Inspector view, but my stats only go back to Aug 28th. How do I at least see the last 90 days?..._

### Match 5
- **Conversation**: 760511738403
- **Extracted**: integrations -> **Ground Truth**: Extension
- **Method**: llm | **Confidence**: high
- **Preview**: _Hello, I am having trouble scheduling pins because the tailwind browser is not loading..._

### Match 6
- **Conversation**: 760511727342
- **Extracted**: ai_creation -> **Ground Truth**: GW Labs
- **Method**: llm | **Confidence**: high
- **Preview**: _trying to generate social media posts from my URL. keep getting an error message...._

### Match 7
- **Conversation**: 760512244433
- **Extracted**: scheduling -> **Ground Truth**: Pin Scheduler
- **Method**: llm | **Confidence**: high
- **Preview**: _Did the Tailwind Scheduling Extension change this month? It's not easy to bulk schedule anymore...._

### Match 8
- **Conversation**: 760511890252
- **Extracted**: pinterest_publishing -> **Ground Truth**: Next Publisher
- **Method**: llm | **Confidence**: high
- **Preview**: _Hello Team, I’m writing you regarding the account from clients, I do the Pinterest Marketing for. Login-Email is alex@bahe.co . I happened yesterday t..._

### Match 9
- **Conversation**: 760511417943
- **Extracted**: pinterest_publishing -> **Ground Truth**: Legacy Publisher
- **Method**: llm | **Confidence**: high
- **Preview**: _I have a handful of scheduled pins that failed, thinking it's because I've changed my website domain but the old one is still attached to the 500+ pin..._

### Match 10
- **Conversation**: 760511547556
- **Extracted**: ai_creation -> **Ground Truth**: Create
- **Method**: llm | **Confidence**: high
- **Preview**: _Good afternoon. Twice I have lost all my work ive spent alot of time on...._

---

## Mismatches Analysis (Top 20)

### Mismatch 1
- **Conversation**: 760511564523
- **Extracted**: pinterest_publishing | **Ground Truth**: Made For You
- **Method**: llm | **Confidence**: high
- **Preview**: _Some of my blog post images are coming up but some of them show things from inside the blog, not the social image set for the blog. And some say (no i..._

### Mismatch 2
- **Conversation**: 215469567627473
- **Extracted**: other | **Ground Truth**: Billing & Settings
- **Method**: llm | **Confidence**: low
- **Preview**: _https://pinterest.com/ lagiagarcia Hello! I hope y..._

### Mismatch 3
- **Conversation**: 215471768013324
- **Extracted**: other | **Ground Truth**: Create
- **Method**: llm | **Confidence**: high
- **Preview**: _hello is there any update to my last inquiry and ticket about my elements search not working?..._

### Mismatch 4
- **Conversation**: 760511767663
- **Extracted**: account | **Ground Truth**: Pin Scheduler
- **Method**: keywords | **Confidence**: medium
- **Preview**: _Hello, I've got a question for the new Pin Scheduler (Beta). This tool is amazing and a great tool replacing the Original publisher. I'm just wonderin..._

### Mismatch 5
- **Conversation**: 215470718007362
- **Extracted**: communities | **Ground Truth**: Pin Scheduler
- **Method**: keywords | **Confidence**: medium
- **Preview**: _Pinning issue. I created smart pins. Preparing to schedule them and here's what happens: 1) I add them to Communities. The Community Pin usage increas..._

### Mismatch 6
- **Conversation**: 760512003593
- **Extracted**: ai_creation | **Ground Truth**: Legacy Publisher
- **Method**: llm | **Confidence**: medium
- **Preview**: _Hallo, ich kann meine eigenen erstellten Bildern nicht mehr den Text ändern. Es wäre nicht mein eigener Pin. Das stimmt nicht. Frisch erstellt mit mei..._

### Mismatch 7
- **Conversation**: 215470653327586
- **Extracted**: other | **Ground Truth**: Create
- **Method**: llm | **Confidence**: high
- **Preview**: _Good day! Why the Facebook Feed posts images are missing?..._

### Mismatch 8
- **Conversation**: 215471666661858
- **Extracted**: other | **Ground Truth**: Product Dashboard
- **Method**: llm | **Confidence**: high
- **Preview**: _Hi, yes this is a Wordpress blog..._

### Mismatch 9
- **Conversation**: 215469805395906
- **Extracted**: scheduling | **Ground Truth**: Extension
- **Method**: llm | **Confidence**: high
- **Preview**: _Is the scheduler not working right now?..._

### Mismatch 10
- **Conversation**: 215470564363764
- **Extracted**: pinterest_publishing | **Ground Truth**: Extension
- **Method**: llm | **Confidence**: high
- **Preview**: _My repinned pins are appearing on my profile as pins I've created..._

### Mismatch 11
- **Conversation**: 760511575900
- **Extracted**: other | **Ground Truth**: Analytics
- **Method**: llm | **Confidence**: high
- **Preview**: _Welcome to Tailwind! 👋 What can I help you with today?..._

### Mismatch 12
- **Conversation**: 760511809522
- **Extracted**: integrations | **Ground Truth**: Smart.bio
- **Method**: keywords | **Confidence**: medium
- **Preview**: _I can't add Posts to the smart.bio - they disappear after creating the Link - what is going wrong?..._

### Mismatch 13
- **Conversation**: 215471410507493
- **Extracted**: next_publisher | **Ground Truth**: Communities
- **Method**: keywords | **Confidence**: medium
- **Preview**: _add to queue..._

### Mismatch 14
- **Conversation**: 760512225578
- **Extracted**: communities | **Ground Truth**: Analytics
- **Method**: keywords | **Confidence**: medium
- **Preview**: _Good afternoon! For the last week, I have been attempting to add a Published Pin (Title: "No-Prep Middle School ELA Stations for April: Fiction, Nonfi..._

### Mismatch 15
- **Conversation**: 760512001664
- **Extracted**: other | **Ground Truth**: Create
- **Method**: llm | **Confidence**: medium
- **Preview**: _Need help with URL design..._

### Mismatch 16
- **Conversation**: 760512052681
- **Extracted**: pinterest_publishing | **Ground Truth**: Create
- **Method**: llm | **Confidence**: high
- **Preview**: _The pins ive created wont download? Help..._

### Mismatch 17
- **Conversation**: 760512025463
- **Extracted**: account | **Ground Truth**: Extension
- **Method**: keywords | **Confidence**: medium
- **Preview**: _Whenever I try and schedule a post the popup window does not allow me to change accounts. I keep getting an error message...._

### Mismatch 18
- **Conversation**: 760511897930
- **Extracted**: billing | **Ground Truth**: Legacy Publisher
- **Method**: keywords | **Confidence**: medium
- **Preview**: _I just upgraded my plan, but it's not letting me add a second pinterest account?..._

### Mismatch 19
- **Conversation**: 760511531433
- **Extracted**: other | **Ground Truth**: Pin Scheduler
- **Method**: llm | **Confidence**: high
- **Preview**: _bulk lock pins..._

### Mismatch 20
- **Conversation**: 760511572141
- **Extracted**: other | **Ground Truth**: Made For You
- **Method**: llm | **Confidence**: high
- **Preview**: _The blog feature is not working in my account...._

---

## Mismatch Patterns

| Extracted -> Ground Truth | Count |
|---------------------------|-------|
| other -> Create | 3 |
| pinterest_publishing -> Made For You | 1 |
| other -> Billing & Settings | 1 |
| account -> Pin Scheduler | 1 |
| communities -> Pin Scheduler | 1 |
| ai_creation -> Legacy Publisher | 1 |
| other -> Product Dashboard | 1 |
| scheduling -> Extension | 1 |
| pinterest_publishing -> Extension | 1 |
| other -> Analytics | 1 |
| integrations -> Smart.bio | 1 |
| next_publisher -> Communities | 1 |
| communities -> Analytics | 1 |
| pinterest_publishing -> Create | 1 |
| account -> Extension | 1 |
| billing -> Legacy Publisher | 1 |
| other -> Pin Scheduler | 1 |
| other -> Made For You | 1 |

---

## Recommendations

- **Target not met**: 46.4% < 85%
- **Worst performing areas** (need vocabulary improvements):
  - Pin Scheduler: 37% (11/30)
  - Create: 40% (8/20)
  - Analytics: 40% (6/15)
  - Smart.bio: 15% (2/13)
  - Extension: 27% (3/11)

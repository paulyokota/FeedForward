# Tailwind Feature Disambiguation Guide

> **Purpose**: Help disambiguate similar-sounding features and map user language to internal systems.
> **Priority**: Load this file FIRST before other product context.

## Scheduler Disambiguation

Users mention "scheduler" in many contexts. Here's how to disambiguate:

| User Says                                              | Likely Means                | Internal Name                                   | Codebase Service  |
| ------------------------------------------------------ | --------------------------- | ----------------------------------------------- | ----------------- |
| "Pin Scheduler"                                        | Pinterest scheduling UI     | Pin Scheduler / Advanced Scheduler              | tack, bach/bachv3 |
| "Multi-Network Posts", "posting to multiple platforms" | Cross-platform scheduling   | Quick Schedule, 2.0 Scheduler, TWNext Scheduler | aero              |
| "SmartSchedule", "best times", "optimal times"         | AI-optimized posting times  | Best Times to Post, Auto-Scheduler              | aero, tack        |
| "schedule times", "time slots"                         | SmartSchedule configuration | SmartSchedule Settings                          | tack, scooby      |
| "old scheduler", "original publisher"                  | Legacy scheduling interface | Original Publisher, Legacy Publisher            | bach (deprecated) |

### Key Insight: "Scheduler" Confusion

When a user says their "scheduler isn't working," ask:

1. Are they seeing pins in the queue but they're not posting? → Pinterest API issue (tack)
2. Are they unable to add pins to the queue? → UI/Frontend issue (aero)
3. Are the times wrong? → SmartSchedule algorithm issue (tack/scooby)
4. Are they using the old interface? → Legacy Publisher (bach)

## Pinterest Publishing Disambiguation

| User Symptom                 | Likely Issue                                    | Service       |
| ---------------------------- | ----------------------------------------------- | ------------- |
| "Pins not showing up"        | Check Created vs Saved tab, domain claim status | tack          |
| "Pins are duplicating"       | Idempotency issue in publish queue              | tack          |
| "Can't connect to Pinterest" | OAuth token expired or safe mode                | gandalf, tack |
| "Wrong board"                | Board selection/routing bug                     | tack          |
| "Video won't post"           | Business account required or format issue       | tack, pablo   |

## Instagram/Facebook Disambiguation

| User Symptom                        | Likely Issue                               | Service       |
| ----------------------------------- | ------------------------------------------ | ------------- |
| "Can't connect Instagram"           | Meta OAuth, Business account requirement   | zuck, gandalf |
| "Posts not publishing to Instagram" | Permission issues, Meta API changes        | zuck          |
| "Facebook page not appearing"       | Page admin access, Business Suite settings | zuck          |

## AI Features Disambiguation

| User Says                                    | They Mean                   | Service             |
| -------------------------------------------- | --------------------------- | ------------------- |
| "Ghostwriter", "AI writing", "generate text" | AI copywriting for captions | ghostwriter         |
| "SmartPin", "generate pins", "AI pins"       | AI pin generation from URL  | bach/bachv3, scooby |
| "Create", "design", "templates"              | Tailwind Create design tool | dolly, pablo        |

## Common Confusion Patterns

### "My pins aren't posting"

This is the #1 complaint. Disambiguate by asking WHERE they see the problem:

1. **In Tailwind**: Pins show as "failed" or "missed" → Pinterest API issue
2. **On Pinterest**: Can't find published pins → Check Created vs Saved tab
3. **Timing**: Pins post at wrong times → SmartSchedule/timezone issue

### "I can't connect my account"

1. **Pinterest**: Usually OAuth token invalidation → gandalf + tack
2. **Instagram**: Business account + Facebook Page requirements → zuck
3. **Facebook**: Page admin permissions → zuck

### "The extension doesn't work"

Browser extension issues are common but separate from main app:

- Extension uses bach APIs under the hood
- Profile switching via dropdown
- Often solved by extension reinstall/update

## Internal Service Names → User-Facing Features

| Internal Service | User Sees As                                         |
| ---------------- | ---------------------------------------------------- |
| tack             | Pinterest features (scheduling, boards, pins)        |
| zuck             | Facebook/Instagram features                          |
| bach/bachv3      | Core backend (scheduling queues, turbo, communities) |
| ghostwriter      | Ghostwriter AI                                       |
| dolly            | Tailwind Create templates                            |
| pablo            | Image/video upload and processing                    |
| swanson          | Billing and plans                                    |
| gandalf          | Login and account connections                        |
| charlotte        | E-commerce integrations (Shopify, Etsy, etc.)        |
| scooby           | URL scraping for pin generation                      |

## URL Path to Feature Mapping

When Intercom provides source URLs, use this to identify the feature:

| URL Pattern                                  | Feature                      | Primary Service |
| -------------------------------------------- | ---------------------------- | --------------- |
| `/dashboard/v2/advanced-scheduler/pinterest` | Pin Scheduler                | tack            |
| `/dashboard/v2/turbo`                        | Turbo (community engagement) | bachv3          |
| `/dashboard/v2/labs`                         | Ghostwriter AI               | ghostwriter     |
| `/dashboard/v2/create`                       | Tailwind Create              | dolly           |
| `/dashboard/tribes`                          | Communities                  | bach            |
| `/dashboard/profile`                         | Insights/Analytics           | tack            |
| `/dashboard/v2/products`                     | E-commerce Products          | charlotte       |
| `/dashboard/v2/settings/smart-schedule`      | SmartSchedule Settings       | tack            |

## Theme Signature Guidance

When creating issue signatures, use the service-specific prefix:

- `pinterest_*` for tack issues
- `instagram_*` or `facebook_*` for zuck issues
- `ghostwriter_*` for AI writing issues
- `smartschedule_*` for timing optimization issues
- `create_*` for design tool issues
- `billing_*` for swanson issues
- `oauth_*` or `connection_*` for gandalf issues

---

_Last updated: 2026-01-28_
_Source: tailwind-codebase-map.md, support-knowledge.md_

# PostHog Event Reference

Catalog of event names discovered during investigations. PostHog event names
are human-readable phrases, not snake_case. Use `event-definitions-list` MCP
tool with keyword search to find new ones.

Project ID: `161414`

## Discovery Pattern

1. Search event definitions by keyword (e.g., "billing", "smart", "blog")
2. Check this file first: the event may already be cataloged
3. After discovering a new event, add it here

## Events by Product Area

### AI Generation (SmartPin, Ghostwriter, Keyword Research, Made For You)

| Event Name                            | Used In | Notes                                              |
| ------------------------------------- | ------- | -------------------------------------------------- |
| `Generated SmartContent descriptions` | SC-150  | SmartPin AI generation. NOT `smart_pin_generated`. |
| `Generated Ghostwriter Content`       | SC-150  | Ghostwriter text generation                        |
| `Clicked Generate Pin`                | SC-150  | User initiates AI pin creation                     |
| `Generated Made for You Content`      | SC-150  | Blog-to-pin AI generation                          |

### SmartPin

| Event Name                                    | Used In       | Notes                                                                   |
| --------------------------------------------- | ------------- | ----------------------------------------------------------------------- |
| `SmartPin Added`                              | SC-150, SC-42 | User adds a SmartPin                                                    |
| `Clicked SmartPin`                            | SC-52         | User clicks on a SmartPin in the UI                                     |
| `Viewed SmartPin V2 Page`                     | SC-44         | V2 experience page view                                                 |
| `Successfully generated SmartPin`             | SC-42         | 200k events/90d, 6k users. Saved insight kRUoIQIx                       |
| `Selected SmartContent generated description` | SC-42         | User picks an AI-generated description. 39k events/90d                  |
| `Changed SmartPin images to select from`      | SC-42         | User modifies image selection. 11.8k events/90d                         |
| `Changed SmartPin design tier`                | SC-42         | User changes design tier. Very low volume (11 events/90d)               |
| `Changed SmartPin title`                      | SC-42         | User edits title on edit form. Tracked but title not used in generation |

### Blog Import

| Event Name                    | Used In | Notes                                                   |
| ----------------------------- | ------- | ------------------------------------------------------- |
| `Successfully imported blogs` | SC-161  | Successful blog import. 797 in 90 days (as of 2026-02)  |
| `Failed to import blogs`      | SC-161  | Failed blog import. 2,910 in 90 days. 4:1 failure ratio |
| `Viewed Blog Dashboard`       | SC-161  | Blog dashboard page view                                |

### Email / Notifications

| Event Name                    | Used In | Notes                                                              |
| ----------------------------- | ------- | ------------------------------------------------------------------ |
| (unsubscribe event, name TBD) | SC-117  | `notification` property has type. `weekly_summary` = 69% of unsubs |

Saved insight: [Email Unsubscribes by Notification Type (90d)](https://us.posthog.com/project/161414/insights/XmWR80tb)

No "summary email sent" event exists. Recommended to add `summary_email_sent`.

### Billing / Subscription

| Event Name                                                       | Used In       | Notes                                                                           |
| ---------------------------------------------------------------- | ------------- | ------------------------------------------------------------------------------- |
| (search "billing", "cancel", "subscription" to find exact names) | SC-97, SC-108 | Past-due transitions, cancellation prompt views, statement downloads discovered |

Saved insights (SC-97): transition counts, flow analysis, cancellation prompt views (3 insights created)
Saved insights (SC-108): country breakdown, statement download over-index (2 insights created)

Key finding: EU users are ~10% of paying base but ~37% of statement downloads.

### Keyword Research

| Event Name           | Used In | Notes                                                                       |
| -------------------- | ------- | --------------------------------------------------------------------------- |
| `Searched keywords`  | SC-46   | Main search event. 53,677 in 90d (~3,800/week, 600-1,500 unique users/week) |
| `Clicked Keyword`    | SC-46   | User clicks a keyword result                                                |
| `Saved Keyword List` | SC-46   | User saves a keyword list                                                   |

Saved insights (SC-46):

- [Keyword Search Usage (90d)](https://us.posthog.com/project/161414/insights/YFPxKCsI)
- [Keyword Feature Engagement (90d)](https://us.posthog.com/project/161414/insights/nueAQ5UK)
- [Keyword Search by Subscription State (90d)](https://us.posthog.com/project/161414/insights/saG6PGLz)

Key finding: ~49% of keyword searchers are active subscribers, ~45% null (likely free). Currently costs 0 credits (`WEBSITE_KEYWORDS: 0` in cost table).

### Signup / Onboarding

| Event Name                   | Used In | Notes                                                                   |
| ---------------------------- | ------- | ----------------------------------------------------------------------- |
| `Personalized Uses Selected` | SC-46   | Post-signup feature intent selector. `personalizedUses` array property. |

Options: `pin_scheduler`, `smart_pin`, `keywords`, `turbo`. Multi-select. Launched ~Jan 4, 2026. ~4,750 respondents in first 5 weeks.

Saved insight: [Signup Intent - Personalized Uses (90d)](https://us.posthog.com/project/161414/insights/8qSPAMAI)

Key finding: 127 users selected keyword research as sole use case (2.7%). Among subset-selectors (not "all four"), ~26% included keywords.

### Publishing / Scheduling

| Event Name               | Used In | Notes                                                                                                          |
| ------------------------ | ------- | -------------------------------------------------------------------------------------------------------------- |
| `Failed to publish post` | SC-162  | ~10k/week (136k in 90d). Has `failure_reason` property. `failure_step` exists but always null (not populated). |

Saved insights (SC-162):

- [Failure Reasons Breakdown (90d)](https://us.posthog.com/project/161414/insights/4YUK0VuF)
- [Publish Failures by Reason (Weekly Trend)](https://us.posthog.com/project/161414/insights/ony5syZ4)

Key failure reasons (90d): `expired_token` (41k, 904 users), `pin_not_found` (23k, 1,393 users), `stuck_in_queue` (12k, 768 users, NO UI COPY), `board_not_found` (11k, 804 users), `blocked_spam` (8k, 804 users). `stuck_in_queue`, `forbidden_resource`, and `invalid_parameters` have no entry in `failure-reasons.ts`.

## Useful Person Properties

| Property              | Type   | Notes                                          |
| --------------------- | ------ | ---------------------------------------------- |
| `$geoip_country_code` | string | Best geography proxy. Two-letter ISO code.     |
| `subscriptionState`   | string | Subscription status. Use with `persons` table. |

## Non-English Country Codes (for reach estimation)

Used across SC-150, SC-108 for estimating non-English user base (~12-14% of users):

`DE`, `FR`, `IT`, `NL`, `ES`, `TR`, `AT`, `BE`, `PT`, `CH`, `PL`, `SE`, `DK`, `NO`, `FI`, `CZ`, `HU`, `RO`, `BG`, `HR`, `GR`, `JP`, `KR`, `BR`, `MX`, `AR`, `CO`

This is a judgment call, not an exhaustive list. Some countries (NL, SE, DK, NO, FI) have high English proficiency but users may still prefer native-language content.

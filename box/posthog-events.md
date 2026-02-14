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

| Event Name                              | Used In        | Notes                                                                                                                                                                           |
| --------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Generated SmartContent descriptions`   | SC-150         | SmartPin AI generation. NOT `smart_pin_generated`.                                                                                                                              |
| `Generated Ghostwriter Content`         | SC-150, SC-179 | Ghostwriter text generation (success)                                                                                                                                           |
| `Failed Ghostwriter Content Generation` | SC-179         | Ghostwriter generation failure. 101 in 90d. Key property: `error` (reason string). Dominant: "Generation job has failed" (58/101), null (30/101), "Failed to poll job" (7/101). |
| `Queued Ghostwriter Generation`         | SC-179         | Job queued to SQS. Frontend-fired.                                                                                                                                              |
| `Clicked Generate Pin`                  | SC-150         | User initiates AI pin creation                                                                                                                                                  |
| `Generated Made for You Content`        | SC-150         | Blog-to-pin AI generation                                                                                                                                                       |

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

| Event Name                        | Used In   | Notes                                                                                                                                                                                                                                                                    |
| --------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Searched keywords`               | SC-46, 15 | Main search event. 54,003 in 90d (~3,800/week, 600-1,500 unique users/week). Key properties: `query` (search term or URL), `isFreshSearch`, `resultCount`, `category`, `language`. 15.4% of searches are URL-based (`query LIKE 'http%'`): 8,314 from 2,501 unique orgs. |
| `Clicked Keyword`                 | SC-46     | User clicks a keyword result                                                                                                                                                                                                                                             |
| `Saved Keyword List`              | SC-46     | User saves a keyword list                                                                                                                                                                                                                                                |
| `Copied keyword`                  | SC-15     | User copies a keyword from results                                                                                                                                                                                                                                       |
| `Saved keyword`                   | SC-15     | User saves a keyword                                                                                                                                                                                                                                                     |
| `Removed keyword`                 | SC-15     | User removes a saved keyword                                                                                                                                                                                                                                             |
| `Sorted keywords`                 | SC-15     | User sorts keyword results                                                                                                                                                                                                                                               |
| `Updated keyword URLs`            | SC-15     | User updates URL associations for a keyword                                                                                                                                                                                                                              |
| `Bulk added keyword URLs`         | SC-15     | User bulk-adds URL associations                                                                                                                                                                                                                                          |
| `Clicked recent keyword search`   | SC-15     | User clicks a recent search suggestion                                                                                                                                                                                                                                   |
| `Cleared recent keyword searches` | SC-15     | User clears search history                                                                                                                                                                                                                                               |

Saved insights (SC-46):

- [Keyword Search Usage (90d)](https://us.posthog.com/project/161414/insights/YFPxKCsI)
- [Keyword Feature Engagement (90d)](https://us.posthog.com/project/161414/insights/nueAQ5UK)
- [Keyword Search by Subscription State (90d)](https://us.posthog.com/project/161414/insights/saG6PGLz)

Saved insights (SC-15):

- [SC-15: URL vs Keyword Search Split (90d)](https://us.posthog.com/project/161414/insights/py2jrdGj)

Key finding: ~49% of keyword searchers are active subscribers, ~45% null (likely free). Currently costs 0 credits (`WEBSITE_KEYWORDS: 0` in cost table).

### Scraping (Scooby V2)

| Event Name                           | Used In | Notes                                                                                                                                           |
| ------------------------------------ | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `Successfully scraped generic site`  | SC-167  | Frontend-initiated scrape (Generate a Pin flow). Key properties: `sourceUrl`, `reason` (null = success, non-null = quality issue), `scrapeMode` |
| `Successfully scraped SmartPin site` | SC-167  | Backend-initiated scrape (SmartPin cron). Different flow from generic site.                                                                     |
| `Failed to scrape SmartPin site`     | SC-167  | Backend scrape failure                                                                                                                          |

Saved insights (SC-167):

- [SC-167: Etsy Scrape Failures by URL Format](https://us.posthog.com/project/161414/insights/i8y0hclm)
- [SC-167: Etsy Scrape Empty Rate (Before vs After Feb 11)](https://us.posthog.com/project/161414/insights/6FD87pVN)

Key finding: `shopname.etsy.com` subdomain URLs have 100% scrape failure rate. `www.etsy.com` URLs succeed ~95%+. The `reason` property value `"No image or text content found in scrape"` indicates empty scrape.

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

### Turbo

| Event Name                                 | Used In | Notes                                                |
| ------------------------------------------ | ------- | ---------------------------------------------------- |
| `Turbo: Pin engaged`                       | SC-32   | User engages with a pin in the Turbo feed. ~120k/90d |
| `Turbo: Pin received engagement`           | SC-32   | Pin receives engagement from others. ~100k/90d       |
| `Turbo: Pin added`                         | SC-32   | Pin added to Turbo queue. ~3.5k/90d                  |
| `Turbo: Tier changed`                      | SC-32   | User changes credit tier on a pin. ~11k/90d          |
| `Turbo: Pin clicked`                       | SC-32   | Pin clicked in feed. ~7.9k/90d                       |
| `Turbo: Pin activated`                     |         | Pin moves from queued to active                      |
| `Turbo: Slot unlocked`                     |         | New slot earned via engagement                       |
| `Turbo: Turbo Queue rotation days changed` |         | User changes rotation period                         |

Saved insights (SC-32):

- [Turbo Engagement Overview (90d)](https://us.posthog.com/project/161414/insights/NHG2HzFV)

Key finding: 34x gap between engagement events (120k) and pins actually added to Turbo (3.5k). Manual queue management is a likely bottleneck. A `turboQueueAutoAddPublishedPins` toggle exists in the UI but has no server-side consumer.

### Ghostwriter

Saved insights (SC-179):

- [Ghostwriter Failures vs Successes (90d weekly)](https://us.posthog.com/project/161414/insights/EIbt6OZm)
- [Ghostwriter Failure Reasons Breakdown (90d)](https://us.posthog.com/project/161414/insights/hkqzN2G6)
- [Ghostwriter Events for Intercom Reporters (orgId cross-ref)](https://us.posthog.com/project/161414/insights/wytuAfYT)

Key finding: 101 tracked failures / ~7,000 successes (~1.4% failure rate) over 90d, steady ~7/week. But Intercom reporters describing "stuck spinner" have zero failure events, indicating an uninstrumented failure mode separate from the tracked population.

## Useful Person Properties

| Property              | Type   | Notes                                          |
| --------------------- | ------ | ---------------------------------------------- |
| `$geoip_country_code` | string | Best geography proxy. Two-letter ISO code.     |
| `subscriptionState`   | string | Subscription status. Use with `persons` table. |

## Non-English Country Codes (for reach estimation)

Used across SC-150, SC-108 for estimating non-English user base (~12-14% of users):

`DE`, `FR`, `IT`, `NL`, `ES`, `TR`, `AT`, `BE`, `PT`, `CH`, `PL`, `SE`, `DK`, `NO`, `FI`, `CZ`, `HU`, `RO`, `BG`, `HR`, `GR`, `JP`, `KR`, `BR`, `MX`, `AR`, `CO`

This is a judgment call, not an exhaustive list. Some countries (NL, SE, DK, NO, FI) have high English proficiency but users may still prefer native-language content.

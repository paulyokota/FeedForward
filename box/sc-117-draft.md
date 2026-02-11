# SC-117: Fix / Redo Summary Emails — Draft Working State

Status: Ready for review — solution sketch corrected after data provenance investigation.

## Research Findings

### Slack Thread

- One-liner: "Fixing/redoing our summary emails that users have complained about forever"
- No additional detail in thread

### Intercom (26 conversations total — 8 in DB, 18 from API)

**Broken "See How They're Doing" CTA (5 contacts):**

- [vanessamclennan@gmail.com, 2026-02-09](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215473028513213) — "Whenever I click on the link I get a woops error notice"
- [boxwoodandmum@gmail.com, 2026-01-28](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215472860102105) — "always takes me to an error page... I'm up for renewal" **CHURN RISK**
- [doolittlejewelry@aol.com, 2025-08-11](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215470266711729) — "EVERY SINGLE TIME... this has been the story for YEARS"
- [studiokcreativeltd@gmail.com, 2025-07-21](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215469950384507) — "the link to See How They're Doing never works!"
- [kaymdouglas@outlook.co.nz, 2025-06-23](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215469552669968) — "the link is not working"

**Inaccurate/confusing data (15 contacts, 2017-2025):**

- [whipandwander@gmail.com, 2025-04-07](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760512178885) — "compared to 0 last week" persistent for 1+ year
- [gayla@gaylairwin.com, 2025-03-24](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760512129051) — "no new pins" despite active scheduling
- [anubisronin@hotmail.com, 2025-10-28](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215471505596160) — 35 scheduled, email shows 30
- [contact@essentialoilhaven.com, 2025-01-20](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760511941650) — pins not showing in reports
- [bergetrk@gmail.com, 2025-02-24](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760512023227) — zeros for reshares, inaccurate followers for 5+ years
- [micheleranard@aol.com, 2021-11-08](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760508471714) — **-828 new repins**
- [keri.houchin@yahoo.com, 2021-07-16](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760507249927) — "no pins from my domain for weeks"
- [hello@jessicabrigham.com, 2021-04-26](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760505191054) — **-2 new repins**
- [alisa@godairyfree.org, 2021-05-03](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760505283589) — **-375 new repins**
- [kathryn@katlodesigns.com, 2020-12-07](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760503036090) — "from over 7,000 repins per week to just 12"
- [cla356@aol.com, 2018-12-03](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/19859870581) — "can't see 660 new repins"
- [fdemming@yourteenmag.com, 2019-10-02](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/23931243442) — "what does pin activity even mean?"
- [alisa@godairyfree.org, 2019-04-08](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/21541010919) — "I had a lot more pins than 41"
- [nztimberproducts@gmail.com, 2018-09-24](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/18676153684) — Pinterest shows 14, Tailwind shows 260
- [infarrantlyc@gmail.com, 2018-05-07](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/16192375026) — declining repins

**Summary not received (2 contacts):**

- [alisha@thesavvybump.com, 2017-12-12](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/13506511071)
- [frostxsun@gmail.com, 2017-02-19](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/8354816773) — "I rely on them to tweak my scheduled pins"

**Unsubscribe failures (4+ contacts):**

- [steph@fearlessfresh.com, 2020-10-05](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760501755576) — "unsubscribed multiple times"
- [camandroben@gmail.com, 2020-04-07](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/26537368291) — "tried 3 times"
- [jayne@helloclassy.com, 2018-08-27](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/18202109475) — "keep on unsubscribing and you keep on sending"
- [nehaleeven6@gmail.com, 2021-12-09](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/760508873744) — hostile response to 0/0 summary

### PostHog

- Saved insight: [Email Unsubscribes by Notification Type (90d)](https://us.posthog.com/project/161414/insights/XmWR80tb)
- `weekly_summary` = 69% of all unsubscribes (6,468 / 9,372 in 90 days)
- ~300 unique users/week unsubscribing from weekly summary
- No "weekly summary sent" event exists — can't calculate unsubscribe rate
- `empty_queue` = 16%, `tribes_weekly_summary` = 12%

### Codebase

- Summary emails are entirely in **legacy PHP**: `RecurringEmailQueuer.php`, `SummaryEmail.php`, `SummaryComposer.php`
- Modern TypeScript email layer (11 templates) does NOT include summary emails
- **Data source**: `SummaryEmail::render()` calls `tack()->getUserSnapshots()` to fetch metrics (followers, engagement, pins, repins, impressions) from the Tack microservice
- Tack dependency is the root cause of inaccurate data — known issue (Shortcut #59639) when daily snapshot not ready at email generation time
- Tack also produces negative/impossible values (negative repins reported by multiple users over 8 years)
- Daily cron: daily every day, weekly on Mondays, monthly on 1st, tribes on Tuesdays
- Batch processing in groups of 100, supports distributed workers
- Sent via Mailgun
- User preferences UI exists: `email-notifications.tsx` with 15 configurable types
- CTA link: `SummaryComposer.php` generates `buildAnalyticsLink('/publisher/queue/posts/published')` — route exists, breakage is in link generation or auth middleware
- **`calcs_published_pin_counts` is NOT a viable Tack replacement**: only tracks hourly publish counts (3 columns: published, duplicate, pin_now). The deprecated `PostScheduledPinJob` writer was turned off Sept 2022; only `PinNowPoster` still writes to it. Missing all the analytics metrics emails currently show (followers, engagement, repins, impressions).

## Data Provenance Investigation (2026-02-11)

Investigated whether `calcs_published_pin_counts` could replace Tack snapshots for email data. Finding: **no**.

- Summary emails call `tack()->getUserSnapshots(start, end)` which returns daily user metric snapshots including followers, engagement, pins, repins, impressions
- `calcs_published_pin_counts` only has: `published_pin_count`, `duplicate_pin_count`, `pin_now_count` per `account_id` per `flat_hour`
- The table is mostly deprecated — main writer (`PostScheduledPinJob`) disabled Sept 2022
- No existing first-party table replicates the full Tack snapshot dataset
- To fully eliminate Tack, would need to build a new daily metrics computation — significant scope

**Implication for solution**: Rather than promising a Tack replacement, the card should recommend (a) rebuild sending/rendering on modern stack regardless, and (b) make a design decision about which metrics to show — either keep Tack with better error handling, or simplify to metrics derivable from existing first-party data.

## Proposed Card Content

### "What"

Rebuild summary emails (daily/weekly/monthly) on the modern TypeScript email infrastructure. The current implementation is legacy PHP that depends on Tack snapshot data, which has produced inaccurate metrics for 8+ years (negative repins, missing pins, stale follower counts) and has a broken CTA link.

**Solution sketch:**

- **Move rendering/sending to TypeScript**: Follow existing patterns — add `SummaryEmail` to the `TailwindEmailTemplates` enum, create a Mailgun-hosted template, use the existing cron sharding infrastructure (96 workers across 24 hours) for scheduling
- **Fix the CTA**: Current link is generated by `SummaryComposer.php` via `buildAnalyticsLink('/publisher/queue/posts/published')`. The destination route exists — debug why the generated link produces auth/error failures, and rebuild it as a working deep link in the new template
- **Design decision on metrics**: The current email shows Tack-derived analytics (repins, impressions, followers) that are frequently wrong. Two paths:
  - **Path A** — Keep Tack data but add defensive handling (graceful fallback when snapshot not ready, suppress negative values, show "data unavailable" instead of wrong numbers)
  - **Path B** — Simplify to metrics derivable from first-party data (pins published from scheduler, SmartPins generated, queue status) and drop the unreliable Pinterest-derived analytics. This eliminates the Tack dependency entirely but changes what the email shows.
- **Add tracking**: No "summary email sent" event exists today. Add PostHog events for send, open, click, and unsubscribe to measure actual engagement
- **Honor unsubscribe preferences**: Wire into existing `emailPreferenceNameEnum` (`weekly_summary`, `daily_summary`, `monthly_summary` already defined) and ensure unsubscribe actually works (4+ users reported repeated failures)

### Evidence

[Intercom evidence CSV attached to this card]

**26 Intercom conversations** across 4 bug categories, spanning 2017-2026:

- **Broken CTA** (5 contacts, 2025-2026): "See How They're Doing" link consistently errors. One user ([boxwoodandmum](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215472860102105)) explicitly tied it to renewal decision. Another ([doolittlejewelry](https://app.intercom.com/a/inbox/jbymhv8i/inbox/conversation/215470266711729)): "EVERY SINGLE TIME... this has been the story for YEARS."
- **Inaccurate data** (15 contacts, 2017-2025): Negative repins (-828, -375, -2), missing pins, stale follower counts. Root cause: Tack snapshot timing issues + Tack data quality. Users report discrepancies lasting months to years.
- **Unsubscribe failures** (4 contacts, 2018-2021): Users unable to opt out after multiple attempts. One hostile response from user receiving 0/0 summary they couldn't stop.
- **Not received** (2 contacts, 2017): Users who wanted summaries but stopped receiving them.

**PostHog**: `weekly_summary` accounts for [69% of all email unsubscribes](https://us.posthog.com/project/161414/insights/XmWR80tb) (6,468 / 9,372 in 90 days, ~300 unique users/week). No "sent" event exists, so true unsubscribe _rate_ is unknown.

### Monetization Angle

- Retention risk: users explicitly connect email quality to renewal decisions
- Value reinforcement: summary emails are the primary touchpoint for users who don't log in daily — if the email says "0 pins, 0 repins" when they're active, it undermines perceived value
- Reducing unsubscribe volume preserves a marketing/engagement channel

### UI Representation

**What the user receives**: A periodic email showing their activity summary. Current version shows Tack-derived metrics (pins, repins, followers, impressions) with a CTA linking to in-app analytics.

**Implementation surface**:

- New Mailgun-hosted HTML template (follow pattern of existing 11 templates in `TailwindEmailTemplates` enum)
- Existing email preferences UI (`email-notifications.tsx`) already has toggles for daily/weekly/monthly summary — wire to new sending path
- CTA should deep-link to `/publisher/queue/posts/published` (route exists, currently broken in legacy link generation)

**Design decision needed**: What metrics to show — current Tack analytics vs. simplified first-party metrics. See "What" section for trade-offs.

### Reporting Needs/Measurement Plan

- Add `summary_email_sent` PostHog event (with `frequency` property: daily/weekly/monthly)
- Track open rate, CTA click rate, unsubscribe rate
- Compare unsubscribe volume before/after (baseline: ~300/week from current PostHog data)
- Success criteria: unsubscribe rate decreases, CTA click rate > 0% (currently effectively 0 due to broken link)

### Release strategy

-

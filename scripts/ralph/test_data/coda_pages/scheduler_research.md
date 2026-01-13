# Pinterest Scheduler Usability Research

**Date:** January 2026
**Researcher:** UX Research Team
**Methodology:** Contextual inquiry + usability testing

## Executive Summary

We conducted 8 usability sessions with Tailwind users to understand pain points in the Pinterest scheduling workflow. Three major themes emerged related to scheduling mechanics, timezone handling, and notification gaps.

## Key Findings

### 1. Timezone Confusion (5/8 participants)

Participants struggled to understand what timezone their scheduled pins would publish in.

**Verbatims:**
- "Is this my time or Pinterest's time? I'm so confused."
- "I scheduled for 3pm but it posted at 6pm... I think?"
- "I travel for work and my pins never go out when I expect"

**Observed Behavior:**
- Users would schedule pins, then immediately check Pinterest to verify
- Some users maintained a separate spreadsheet to track "real" vs "scheduled" times
- 3 participants had given up on scheduling specific times and just used SmartSchedule

**Impact:** Users lose trust in the scheduler and either over-rely on SmartSchedule (losing control) or manually post (defeating the purpose of Tailwind).

### 2. Failed Pin Notifications (4/8 participants)

When pins fail to publish, users often don't find out until much later.

**Verbatims:**
- "I found out my pins didn't go out when a client asked where they were"
- "Is there supposed to be an email when something fails?"
- "I check the error log every day now, just to be safe"

**Observed Behavior:**
- Users would schedule a batch of pins and assume success
- Discovery of failures was often accidental (checking Pinterest, client feedback)
- Some users developed workarounds like daily manual checks

**Impact:** Broken trust in the platform; users feel they can't "set and forget" even though that's the core value proposition.

### 3. Pin Spacing Clarity (3/8 participants)

Users didn't understand how pin spacing worked with their schedule.

**Verbatims:**
- "I set 30 minutes between pins but some went out back-to-back"
- "What's the difference between spacing and my time slots?"
- "I want my pins spread throughout the day but they all cluster"

**Observed Behavior:**
- Users would set both time slots AND pin spacing, then get confused by the interaction
- Some users over-scheduled time slots to "guarantee" spreading
- Mental model mismatch between "schedule" and "spacing"

**Impact:** Suboptimal scheduling strategies; users either bunch pins together or spread them too thin.

## Recommendations

1. **Timezone:** Display user's local timezone prominently in the scheduler UI; add confirmation showing "This will publish at [time] in [timezone]"

2. **Notifications:** Implement push/email notifications for failed pins within 1 hour of scheduled time; add a "scheduled pins health" dashboard widget

3. **Pin Spacing:** Redesign the spacing UI to show a visual timeline of when pins will actually publish; clarify the relationship between slots and spacing in onboarding

## Next Steps

- Share findings with Pinterest Scheduler team
- Prioritize based on engineering effort and impact
- Consider A/B test for timezone display changes

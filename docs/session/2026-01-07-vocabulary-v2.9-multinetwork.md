# Vocabulary v2.9 - Multi-Network Scheduler Support

**Date**: 2026-01-07
**Task**: Add Multi-Network Scheduler as 3rd scheduling system with proper URL context mapping

## Problem Identified

During vocabulary work, we realized there are **THREE** distinct scheduling systems in Tailwind, not two:

1. **Pin Scheduler (Next Publisher)** - Pinterest-only, new system
2. **Legacy Publisher (Original Publisher)** - Pinterest-only, old system
3. **Multi-Network Scheduler** - Cross-platform (Pinterest, Instagram, Facebook)

Previous vocabulary only covered the two Pinterest-specific schedulers. Multi-Network was missing entirely.

## Changes Applied

### 1. Added Multi-Network as Product Area

Added to `product_area_mapping`:

```json
"Multi-Network": [
  "crossposting_failure",
  "multinetwork_scheduling_failure",
  "multinetwork_feature_question"
]
```

### 2. Updated URL Context Mappings

**Pin Scheduler (Next Publisher)**:

- `/dashboard/v2/advanced-scheduler/pinterest`
- `/advanced-scheduler/pinterest`

**Legacy Publisher**:

- `/publisher/queue`
- `/publisher/drafts`

**Multi-Network Scheduler** (NEW):

- `/dashboard/v2/drafts`
- `/dashboard/v2/scheduler`

### 3. Added Three Multi-Network Themes

**`crossposting_failure`** (updated existing theme)

- **Product area**: Changed from `scheduling` → `multi-network`
- **Description**: Posts not automatically cross-posting between platforms (Instagram to Facebook, etc.)
- **Keywords**: "auto-post", "cross-post", "not posting to facebook", "instagram posts not on facebook"
- **Example**: "Our instagram posts are not being automatically posted on Facebook"

**`multinetwork_scheduling_failure`** (new)

- **Product area**: `multi-network`
- **Description**: Multi-Network posts not publishing at scheduled time to Pinterest, Instagram, or Facebook
- **Keywords**: "multi-network not posting", "instagram not posting", "facebook not posting", "drafts not scheduling", "quick schedule"
- **Example**: "My Instagram posts aren't publishing from Multi-Network Scheduler"

**`multinetwork_feature_question`** (new)

- **Product area**: `multi-network`
- **Description**: User needs help understanding Multi-Network Scheduler features
- **Keywords**: "how to schedule instagram", "schedule to multiple platforms", "instagram stories how to", "carousel posts", "sms reminder"
- **Example**: "Can I schedule the same post to Pinterest and Instagram?"

### 4. Updated Documentation

Updated `product_area_mapping` comment to clarify:

> "THREE SCHEDULERS - Next Publisher = Pin Scheduler (Pinterest-only, new), Legacy Publisher = Original Publisher (Pinterest-only, old), Multi-Network = cross-platform scheduler (Pinterest/Instagram/Facebook)"

## Key Insights from Product Documentation

**Multi-Network Scheduler** (from `context/product/Tailwind Product Documentation - COMPLETE UPDATED.md`):

**Also Known As**:

- External: Multi-Network Posts, Cross-Platform Scheduler
- Internal: Quick Schedule, 2.0 Scheduler, TWNext Scheduler

**Core Functionality**:

- Upload once, schedule across Pinterest, Instagram, Facebook
- Ghostwriter integration for captions
- Smart Schedule recommendations (Pinterest & Instagram only)
- Instagram: Feed posts, Stories (SMS reminder only), grid preview, hashtag finder
- Facebook: Page posts (custom time only, no Smart Schedule)
- Centralized drafts management

**Key Differences from Pin Scheduler**:

- Smart Schedule only provides **time recommendations**, not auto-slotted time slots
- Instagram Stories limited to SMS reminder (no auto-post)
- Multi-platform in one flow vs Pinterest-only focus

## Why This Matters for Theme Extraction

**Disambiguation**: When a user reports "scheduling failure", we now have THREE possibilities:

1. Pin Scheduler issue → `/advanced-scheduler/pinterest` → Next Publisher
2. Legacy Publisher issue → `/publisher/queue` → Legacy Publisher
3. Multi-Network issue → `/dashboard/v2/scheduler` → Multi-Network

**URL context is critical** because keywords alone can't distinguish between these three systems. All three use similar language ("scheduling", "posts not publishing", "drafts").

**Example scenarios**:

- User on `/dashboard/v2/scheduler` says "Instagram posts not scheduling" → Multi-Network Scheduler issue
- User on `/advanced-scheduler/pinterest` says "pins not scheduling" → Pin Scheduler (Next Publisher) issue
- User on `/publisher/queue` says "pins sent back to drafts" → Legacy Publisher issue

## Impact on Validation

**Current validation script limitation**: Tests against Shortcut story titles only (no URL context). Stories may not specify which scheduler they're using.

**For real Intercom conversations**: URL context will be available and critical for routing these three schedulers correctly.

## Files Modified

- `config/theme_vocabulary.json` (v2.8 → v2.9)
  - Added Multi-Network product area with 3 themes
  - Updated `crossposting_failure` to Multi-Network product area
  - Added 2 new themes: `multinetwork_scheduling_failure`, `multinetwork_feature_question`
  - Updated URL context mappings for all three schedulers
  - Updated terminology comment to clarify three distinct schedulers
  - Updated version to 2.9

## Next Steps

### High Priority

1. **Integrate URL context into theme extractor** - Use `source.url` from Intercom to boost correct scheduler (this is now even more critical with 3 schedulers)
2. **Update validation script** - Add URL context simulation based on expected product area
3. **Test on real Intercom data** - Validate that Multi-Network themes match real user issues

### Medium Priority

4. **Review Shortcut training data** - Look for Multi-Network stories that were mislabeled as Pin Scheduler or Legacy Publisher
5. **Expand Multi-Network keywords** - Add more Instagram/Facebook-specific terms if needed

## Overall Progress

**Scheduler Coverage**:

- ✅ Pin Scheduler (Next Publisher) - 5 themes
- ✅ Legacy Publisher - 3 themes
- ✅ Multi-Network Scheduler - 3 themes (NEW)

**Version History**:

- v2.5: 44.1% accuracy (baseline)
- v2.6: 50.6% (+6.5%) - Customer keywords
- v2.7: 53.2% (+9.1%) - Context boosting + Product Dashboard
- v2.8: 52.5% (+8.4%) - Extension UI, Legacy/Next split, SmartLoop
- **v2.9**: 52.5% (no change expected) - Multi-Network infrastructure added

Note: v2.9 doesn't change validation accuracy because Shortcut training data doesn't have URL context. Real impact will be seen on live Intercom conversations.

## Strategic Importance

This completes our scheduler coverage. We now have proper theme + URL disambiguation for all three scheduling systems. This is critical because:

1. **Scheduling is the core Tailwind feature** - Most user issues relate to scheduling
2. **Three distinct systems** - Each has different architecture, APIs, and failure modes
3. **URL context is the differentiator** - Keywords alone can't distinguish them
4. **Proper routing improves engineering efficiency** - Issues go to the right team immediately

With v2.9, we're ready to process real Intercom conversations with full scheduler coverage.

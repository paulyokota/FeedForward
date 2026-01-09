# Phase 5A: Ground Truth Data Summary

**Generated**: 2026-01-08 14:16:58

## Dataset Overview

| Metric | Value |
|--------|-------|
| Total conversations with story_id | 384 |
| Total unique Shortcut stories | 902 |
| Conversations with product_area | 195 |
| Date range | 2024-01-18 to 2025-11-18 |

## Dataset Splits

| Split | Count | Purpose |
|-------|-------|---------|
| Validation Set (80%) | 156 | Accuracy measurement |
| Analysis Set (20%) | 39 | Vocabulary gap discovery |

## Product Area Distribution

| Product Area | Count | % of Dataset |
|--------------|-------|--------------|
| Pin Scheduler | 31 | 15.9% |
| Next Publisher | 25 | 12.8% |
| Legacy Publisher | 24 | 12.3% |
| Create | 22 | 11.3% |
| Smart.bio | 15 | 7.7% |
| Analytics | 15 | 7.7% |
| Billing & Settings | 13 | 6.7% |
| Extension | 11 | 5.6% |
| Made For You | 10 | 5.1% |
| GW Labs | 8 | 4.1% |
| Product Dashboard | 6 | 3.1% |
| SmartLoop | 5 | 2.6% |
| Communities | 4 | 2.1% |
| CoPilot | 3 | 1.5% |
| Jarvis | 1 | 0.5% |
| Email | 1 | 0.5% |
| Ads | 1 | 0.5% |

## Top 20 Shortcut Labels

| Label | Count |
|-------|-------|
| Pinterest | 100 |
| Low Lift | 20 |
| Systems Review | 6 |
| GhostwriterV2 | 5 |
| BachV2-SMS | 1 |
| Needs Design | 1 |

## Data Quality Notes

- **Target Met**: ❌ No (195 < 200)
- **Product area as ground truth**: We use the `product_area` field from Shortcut stories as the primary ground truth label
- **Conversations without product_area**: Excluded from validation (no ground truth label)

## Files Generated

- `data/phase5_ground_truth.json` - Full dataset with all conversations and metadata
- `prompts/phase5_data_summary.md` - This summary

## Next Steps

Proceed to **Phase 5B**: Run theme extraction on all validation set conversations.

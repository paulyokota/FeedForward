# Phase 1: Data Summary

**Date**: 2026-01-08
**Ground Truth Source**: `Story ID v2` custom attribute from Intercom conversations

## Data Sources

1. **Primary**: `data/story_id_conversations.csv` - 756 conversation IDs exported from Intercom with Story ID v2 filter
2. **Supplementary**: `data/shortcut_stories_with_intercom_links.csv` - 31,654 Shortcut stories, 31 with embedded Intercom conversation links (32 total conversations)

## Shortcut CSV Analysis

The Shortcut CSV was analyzed to extract additional conversation-to-story mappings:

- **Stories with Intercom links**: 31
- **Total conversation IDs found**: 32
- **Stories with 2+ conversations**: 1 (Story 60549 with 2 conversations)
- **Conversations with Story ID v2**: 24 of 32 fetched
- **Result**: All 24 conversations were already in the primary dataset (overlap with story_id_conversations.csv)

## Dataset Statistics

| Metric                               | Value                    |
| ------------------------------------ | ------------------------ |
| Total conversations fetched          | 706                      |
| Unique Story IDs                     | 251                      |
| Story IDs with 2+ conversations      | 65                       |
| Total conversations in usable groups | 520                      |
| Date range                           | 2024-01-25 to 2025-11-18 |
| Fetch errors                         | 57 (7.5%)                |

## Group Size Distribution

| Conversations per Group | Count     |
| ----------------------- | --------- |
| 2 conversations         | 37 groups |
| 3 conversations         | 7 groups  |
| 4 conversations         | 4 groups  |
| 5 conversations         | 6 groups  |
| 6 conversations         | 5 groups  |
| 7 conversations         | 1 group   |
| 8 conversations         | 1 group   |
| 11 conversations        | 2 groups  |
| 35 conversations        | 1 group   |
| 277 conversations       | 1 group   |

## Training/Test Split

| Set            | Groups | Conversations |
| -------------- | ------ | ------------- |
| Training (80%) | 52     | 480           |
| Test (20%)     | 13     | 40            |

## Test Set Composition

| Story ID | Conversations |
| -------- | ------------- |
| 63005    | 2             |
| 60862    | 2             |
| 55720    | 2             |
| 60086    | 11            |
| 63275    | 2             |
| 53734    | 2             |
| 63202    | 2             |
| 52070    | 2             |
| 62569    | 2             |
| 61917    | 6             |
| 58913    | 3             |
| 63593    | 2             |
| 62845    | 2             |

## Data Quality Notes

1. **Suspicious catch-all groups** (in training set only):
   - Story ID `66666`: 277 conversations - clearly a placeholder/catch-all
   - Story ID `88`: 35 conversations - likely another placeholder
2. **Fetch errors**: 57 conversations (7.5%) could not be fetched - likely deleted or archived in Intercom
3. **Single-conversation groups**: 186 Story IDs have only 1 conversation - excluded from analysis since they don't test grouping

## Files Generated

- `data/story_id_ground_truth.json` - Full dataset with train/test split
- `data/shortcut_all_mappings.json` - Story ID → conversation ID mappings from Shortcut CSV
- `data/shortcut_conversation_results.json` - Intercom fetch results for Shortcut-linked conversations
- `prompts/data_summary.md` - This file

## Next Steps

Proceed to Phase 2: Baseline Evaluation using the test set of 13 groups (40 conversations).

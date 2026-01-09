# Multi-Source Architecture: Quick Reference

## Phase Overview

| Phase | Name                   | Goal                              | Estimated Time |
| ----- | ---------------------- | --------------------------------- | -------------- |
| 0     | Bulk Coda Import       | Import all existing research data | 2-4 hours      |
| 1     | Schema Updates         | Add data_source tracking          | 30 minutes     |
| 2     | Source Adapters        | Normalize Coda + Intercom format  | 1-2 hours      |
| 3     | Unified Pipeline       | Multi-source ingestion            | 1-2 hours      |
| 4     | Aggregation Updates    | Track source counts               | 1 hour         |
| 5     | Cross-Source Analytics | Identify theme overlap            | 1-2 hours      |
| 6     | Story Enrichment       | Evidence from both sources        | 1 hour         |

**Total Estimated Time**: 8-13 hours

---

## Key Deliverables by Phase

### Phase 0

- `src/coda_client.py` - Coda API wrapper
- `scripts/import_coda_ai_summaries.py` - AI Summary importer
- `scripts/import_coda_synthesis.py` - Table importer
- `reports/coda_import_YYYY-MM-DD.md` - Import analysis report

### Phase 1

- `src/db/migrations/003_add_data_source.sql` - Schema migration

### Phase 2

- `src/adapters/__init__.py` - Base adapter interface
- `src/adapters/coda_adapter.py` - Coda normalizer
- `src/adapters/intercom_adapter.py` - Intercom normalizer

### Phase 3

- Updated `src/two_stage_pipeline.py` with `--source` parameter

### Phase 4

- Updated `src/theme_tracker.py` with source_counts tracking

### Phase 5

- `src/analytics/cross_source.py` - Cross-source queries

### Phase 6

- Updated `src/story_formatter.py` with source-attributed evidence

---

## Data Flow

```
┌─────────────────┐         ┌─────────────────┐
│  Coda Research  │         │Intercom Support │
│   (100 pages)   │         │  (conversations)│
└────────┬────────┘         └────────┬────────┘
         │                           │
         ▼                           ▼
   CodaAdapter              IntercomAdapter
         │                           │
         └───────────┬───────────────┘
                     ▼
           Unified Pipeline
         (theme extraction)
                     │
                     ▼
        ┌────────────────────────┐
        │  PostgreSQL            │
        │  - conversations       │
        │  - themes              │
        │  - theme_aggregates    │
        │    (with source_counts)│
        └────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │ Cross-Source Analytics │
        │ - High confidence      │
        │ - Strategic            │
        │ - Tactical             │
        └────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │   Shortcut Stories     │
        │ (evidence from both    │
        │     sources)           │
        └────────────────────────┘
```

---

## Common Issues & Solutions

### Issue: Coda pages appear empty

**Solution**: Use `/pages/{id}/content` endpoint, not just page metadata

### Issue: Rate limiting from Coda API

**Solution**: Add `time.sleep(0.5)` between requests (200 req/min limit)

### Issue: Theme extraction quality low from Coda

**Solution**: Parse AI Summary sections separately (Loves, Pain Points, Feature Requests)

### Issue: JSONB source_counts not updating

**Solution**: Verify JSONB syntax: `source_counts || jsonb_build_object('coda', 1)`

### Issue: Backward compatibility broken

**Solution**: Default `data_source='intercom'` in all existing code paths

---

## Testing Checklist

- [ ] Coda client connects and lists 100 pages
- [ ] AI Summary import extracts 5-10 populated summaries
- [ ] Synthesis table import gets 50-100 rows
- [ ] Import report generated with theme counts
- [ ] Schema migration runs without errors
- [ ] Intercom pipeline still works (`--source intercom`)
- [ ] Coda pipeline works (`--source coda`)
- [ ] Theme aggregates show source_counts JSONB
- [ ] Cross-source query returns high-confidence themes
- [ ] Shortcut story includes evidence from both sources

---

## Success Metrics

**Quantitative**:

- 50-100 themes extracted from Coda
- 5-10 themes appear in BOTH sources (high confidence)
- 0 regressions in existing Intercom pipeline

**Qualitative**:

- Research quotes add context to support volume
- Product team can see which support issues were researched
- Clear priority signal: themes in both sources vs. single source

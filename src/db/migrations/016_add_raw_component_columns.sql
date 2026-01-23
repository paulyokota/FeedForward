-- Migration 016: Raw Component Preservation
-- Preserves LLM output before normalization for audit and drift detection
-- Commit: 76bd915 - fix: Preserve raw LLM output and fix normalization issues

-- 1) Add raw columns to themes table
ALTER TABLE themes ADD COLUMN IF NOT EXISTS component_raw TEXT;
ALTER TABLE themes ADD COLUMN IF NOT EXISTS product_area_raw TEXT;

-- 2) Add flag to distinguish true raw values from backfilled data
-- TRUE = backfilled from normalized values (no recovery possible)
-- FALSE = captured from actual LLM output
ALTER TABLE themes ADD COLUMN IF NOT EXISTS component_raw_inferred BOOLEAN DEFAULT FALSE;

-- 3) Comments for documentation
COMMENT ON COLUMN themes.component_raw IS 'Original LLM output before normalization';
COMMENT ON COLUMN themes.product_area_raw IS 'Original LLM output before normalization';
COMMENT ON COLUMN themes.component_raw_inferred IS 'TRUE = inferred from normalized data, FALSE = true LLM output';

-- 4) Composite index for drift detection queries
-- Supports finding multiple raw variants that map to same canonical
CREATE INDEX IF NOT EXISTS idx_themes_component_drift ON themes(component, component_raw);

-- 5) Backfill existing rows (optional, one-time)
-- Run manually after migration if you have legacy data:
--
-- UPDATE themes SET
--     component_raw = component,
--     product_area_raw = product_area,
--     component_raw_inferred = TRUE
-- WHERE component_raw IS NULL;

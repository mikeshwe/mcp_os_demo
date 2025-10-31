
-- 03_queries.sql
-- Handy queries for the LP one-pager workflow.

-- 1) LP Snapshot: approved GoldenFacts for a deal (flat list)
-- :deal_id -> UUID of the portfolio company
SELECT k.name AS kpi, kv.value, kv.unit, kv.as_of, kv.formula
FROM golden_facts gf
JOIN kpi_values kv USING (kpi_value_id)
JOIN kpis k USING (kpi_id)
WHERE gf.deal_id = '00000000-0000-0000-0000-000000000001'
  AND gf.status = 'approved'
ORDER BY k.name;

-- 2) KPI → underlying cell references (lineage)
SELECT k.name AS kpi, kv.kpi_value_id, t.name AS table_name, c.source_ref, c.label, c.period, c.value, c.unit
FROM kpi_values kv
JOIN kpis k USING (kpi_id)
JOIN kpi_value_sources s ON s.kpi_value_id = kv.kpi_value_id AND s.source_type='cell'
JOIN table_cells c ON c.cell_id = s.source_id
JOIN tables_norm t ON t.table_id = c.table_id
WHERE kv.deal_id = '00000000-0000-0000-0000-000000000001'
ORDER BY k.name, c.period DESC;

-- 3) Build a wide Snapshot for templating (pivot-like)
-- (You can also pivot in your app layer.)
SELECT
  MAX(CASE WHEN k.name = 'Revenue_LTM'    THEN kv.value END) AS revenue_ltm,
  MAX(CASE WHEN k.name = 'YoY_Growth'     THEN kv.value END) AS yoy_growth_pct,
  MAX(CASE WHEN k.name = 'Gross_Margin'   THEN kv.value END) AS gross_margin_pct,
  MAX(CASE WHEN k.name = 'EBITDA_Margin'  THEN kv.value END) AS ebitda_margin_pct
FROM golden_facts gf
JOIN kpi_values kv USING (kpi_value_id)
JOIN kpis k USING (kpi_id)
WHERE gf.deal_id = '00000000-0000-0000-0000-000000000001'
  AND gf.status='approved';

-- 4) Vector search example (semantic retrieval of text chunks)
-- Replace `:qvec` with your embedding vector for the query.
-- SELECT chunk_id, 1 - (e.vector <=> :qvec) AS score, text
-- FROM embeddings e
-- JOIN chunks c USING (chunk_id)
-- WHERE c.access_tag IN ('LP-safe','internal')
-- ORDER BY e.vector <=> :qvec
-- LIMIT 10;

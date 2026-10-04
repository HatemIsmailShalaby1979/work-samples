-- =============================================================================
-- Query 07 — index, and the query plan it changes
-- =============================================================================
-- Question: does an index on `tickets(created_at)` actually change how SQLite
--           executes a date-range report — and if so, how?
--
-- This file holds exactly two statements, in order:
--   1. the CREATE INDEX
--   2. the query under study
--
-- run_checks.py parses both, then executes the query under study twice —
-- once with the index absent and once with it present — capturing
-- `EXPLAIN QUERY PLAN` at each point. The comparison is measured, not asserted
-- from memory, and the two plans are written to expected/query_plan.txt.
--
-- Read the plan as follows:
--   `SCAN tickets`              — the whole table is read, row by row.
--   `SEARCH tickets USING INDEX` — the index is used to jump to the range.
--   `USING COVERING INDEX`      — the index alone answers the query, with no
--                                 table lookup at all.
--
-- The index is created here rather than in schema.sql on purpose: schema.sql
-- builds the tables, so that the effect of adding the index can be observed
-- separately instead of being baked into the starting state.
-- =============================================================================

CREATE INDEX idx_tickets_created_at ON tickets (created_at);

-- The query under study: one month of daily volumes.
-- The WHERE clause is a range on `created_at` and the grouping key derives from
-- the same column, which is the shape an index can serve.
SELECT
    DATE(created_at) AS day,
    COUNT(*)         AS tickets
FROM tickets
WHERE created_at >= '2026-09-01 00:00:00'
  AND created_at <  '2026-10-01 00:00:00'
GROUP BY DATE(created_at)
ORDER BY day ASC;

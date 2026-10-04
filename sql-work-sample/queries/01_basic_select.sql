-- =============================================================================
-- Query 01 — SELECT / WHERE / ORDER BY / LIMIT
-- =============================================================================
-- Question: which still-open contacts have waited longest?
--
-- Demonstrates: single-table filtering, multi-key ordering, row limiting.
--
-- Why the ORDER BY has two keys: `wait_seconds` alone is not unique, so a
-- LIMIT 10 over it could return a different set of rows between runs. Adding
-- `ticket_id` as a tiebreaker makes the cut deterministic and the expected
-- output reproducible.
--
-- Why `wait_seconds >= 60` and not just `status`: the status filter selects the
-- population, the wait filter selects the interesting tail of it. Two separate
-- predicates doing two separate jobs.
-- =============================================================================

SELECT
    ticket_id,
    created_at,
    status,
    wait_seconds,
    handle_seconds
FROM tickets
WHERE status IN ('unresolved', 'escalated')
  AND wait_seconds >= 60
ORDER BY wait_seconds DESC, ticket_id ASC
LIMIT 10;

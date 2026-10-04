-- =============================================================================
-- Query 08 — period-over-period comparison
-- =============================================================================
-- Question: did average wait time improve from August to September, and by how
--           much, per queue?
--
-- How the comparison is built
-- ---------------------------
-- `monthly` collapses tickets to one row per queue per calendar month.
--
-- `with_previous` then attaches the PREVIOUS month's average to the current
-- row using `LAG(...) OVER (PARTITION BY queue_name ORDER BY month)`. That is
-- the whole trick: period-over-period comparison without a self-join and
-- without a correlated subquery, because LAG reads the preceding row of the
-- same partition in a single pass.
--
-- The August rows necessarily carry NULL in `prev_avg_wait` — there is no
-- earlier month in the data — so their change columns are NULL too. That is
-- correct, not missing data, and the percentage is guarded against division by
-- NULL rather than by zero.
--
-- The trend is real in this dataset by construction: tools/generate_seed.py
-- applies a documented 0.85 factor to September waits. The query's job is to
-- find it and size it, not to be surprised by it.
-- =============================================================================

WITH monthly AS (
    SELECT
        q.queue_id,
        q.queue_name,
        STRFTIME('%Y-%m', t.created_at) AS month,
        COUNT(*)                        AS tickets,
        AVG(t.wait_seconds)             AS avg_wait_raw,
        AVG(t.handle_seconds)           AS avg_handle_raw
    FROM tickets AS t
    INNER JOIN queues AS q
            ON q.queue_id = t.queue_id
    GROUP BY q.queue_id, q.queue_name, STRFTIME('%Y-%m', t.created_at)
),
with_previous AS (
    SELECT
        queue_id,
        queue_name,
        month,
        tickets,
        avg_wait_raw,
        avg_handle_raw,
        LAG(avg_wait_raw) OVER (PARTITION BY queue_id ORDER BY month) AS prev_avg_wait_raw
    FROM monthly
)
SELECT
    queue_name,
    month,
    tickets,
    ROUND(avg_wait_raw, 1)   AS avg_wait_seconds,
    ROUND(avg_handle_raw, 1) AS avg_handle_seconds,
    ROUND(prev_avg_wait_raw, 1) AS prev_avg_wait_seconds,
    ROUND(avg_wait_raw - prev_avg_wait_raw, 1) AS wait_change_seconds,
    ROUND(100.0 * (avg_wait_raw - prev_avg_wait_raw) / prev_avg_wait_raw, 1) AS wait_change_pct
FROM with_previous
ORDER BY queue_name ASC, month ASC;

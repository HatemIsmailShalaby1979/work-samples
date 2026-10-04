-- =============================================================================
-- Query 06 — window function: a rolling frame
-- =============================================================================
-- Question: what does the daily contact volume look like once the day-to-day
--           noise is smoothed out?
--
-- Why a frame and not just ORDER BY
-- ---------------------------------
-- `OVER (ORDER BY day)` with no frame gives a RUNNING total from the first row
-- to the current one. That is not what is wanted here. The `ROWS BETWEEN 6
-- PRECEDING AND CURRENT ROW` clause redefines the window as a 7-row sliding
-- window — the current day plus the six before it — which is what turns a
-- spiky daily series into a readable trend.
--
-- The first six rows have fewer than seven days available, so SQLite averages
-- whatever exists rather than returning NULL. That is why the first row's
-- rolling average equals its own daily count: worth knowing before reading the
-- left edge of the output as a real trend.
--
-- `daily` collapses ~1,100 tickets to 61 rows; the window then runs over those
-- 61 rather than over the raw ticket rows.
-- =============================================================================

WITH daily AS (
    SELECT
        DATE(created_at) AS day,
        COUNT(*)         AS tickets
    FROM tickets
    GROUP BY DATE(created_at)
)
SELECT
    day,
    tickets,
    ROUND(
        AVG(tickets) OVER (
            ORDER BY day
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ), 2
    ) AS rolling_7day_avg,
    SUM(tickets) OVER (ORDER BY day) AS running_total
FROM daily
ORDER BY day ASC;

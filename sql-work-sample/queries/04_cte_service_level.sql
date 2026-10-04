-- =============================================================================
-- Query 04 — CTE: service level against target, per queue
-- =============================================================================
-- Question: which queues are missing their service-level target?
--
-- Structure: three named steps rather than one nested query, because each step
-- answers a different question and each is worth being able to read on its own.
--
--   ticket_flags  — one row per ticket, with a 1/0 flag for "answered within
--                   this queue's own target". The target lives in `queues`, so
--                   the comparison has to happen per row against a joined value.
--   queue_sl      — one row per queue: the aggregate, computed once.
--   final SELECT  — joins the aggregate back to the target and states a verdict.
--
-- Abandoned contacts are excluded at the first step. A contact nobody answered
-- was never "answered outside target" — counting it as a service-level failure
-- would conflate two different problems, which is why the exclusion is in the
-- CTE and not bolted on at the end.
-- =============================================================================

WITH ticket_flags AS (
    SELECT
        t.ticket_id,
        t.queue_id,
        CASE
            WHEN t.wait_seconds <= q.target_answer_seconds THEN 1
            ELSE 0
        END AS answered_in_target
    FROM tickets AS t
    INNER JOIN queues AS q
            ON q.queue_id = t.queue_id
    WHERE t.status <> 'abandoned'
),
queue_sl AS (
    SELECT
        queue_id,
        COUNT(*)                                 AS answered_tickets,
        SUM(answered_in_target)                  AS in_target,
        ROUND(100.0 * SUM(answered_in_target) / COUNT(*), 2) AS service_level_pct
    FROM ticket_flags
    GROUP BY queue_id
)
SELECT
    q.queue_name,
    q.channel,
    q.target_answer_seconds,
    q.target_service_level_pct                       AS target_sl_pct,
    s.answered_tickets,
    s.in_target,
    s.service_level_pct,
    CASE
        WHEN s.service_level_pct >= q.target_service_level_pct THEN 'MEETS'
        ELSE 'MISSES'
    END                                              AS verdict
FROM queue_sl AS s
INNER JOIN queues AS q
        ON q.queue_id = s.queue_id
ORDER BY s.service_level_pct ASC;

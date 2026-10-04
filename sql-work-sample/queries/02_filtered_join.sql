-- =============================================================================
-- Query 02 — filtered two-table JOIN, and its row count
-- =============================================================================
-- Question: which of Team Bravo's long technical contacts took the most time?
--
-- CARDINALITY, stated before the query is read
-- -------------------------------------------
--   tickets.agent_id  ->  agents.agent_id   is MANY-TO-ONE
--   agents.team_id    ->  teams.team_id     is MANY-TO-ONE
--
-- A many-to-one join cannot multiply rows. So a join between `tickets` and
-- `agents` returns AT MOST one row per ticket — the only way the count can
-- differ from the ticket count is if a ticket has no matching agent.
--
-- That is exactly what happens here. Abandoned contacts are never assigned to
-- an agent, so they carry `agent_id IS NULL`, and an INNER JOIN silently drops
-- them. Statement A measures that loss rather than asserting it.
--
-- Statement B is the join itself, restricted to two tables.
-- =============================================================================

-- Statement A — measure the cardinality before trusting the join.
SELECT
    (SELECT COUNT(*) FROM tickets)                            AS tickets_total,
    (SELECT COUNT(*) FROM tickets WHERE agent_id IS NULL)     AS tickets_without_agent,
    (SELECT COUNT(*) FROM tickets WHERE agent_id IS NOT NULL) AS tickets_joinable;

-- Statement B — the filtered two-table join.
-- The filter on `a.team_id = 2` is applied to the joined row set, so tickets
-- whose agent belongs to another team — and tickets with no agent at all —
-- are excluded by the same predicate.
SELECT
    a.agent_id,
    a.agent_name,
    t.ticket_id,
    t.created_at,
    t.channel,
    t.handle_seconds
FROM tickets AS t
INNER JOIN agents AS a
        ON a.agent_id = t.agent_id
WHERE a.team_id = 2
  AND t.channel = 'phone'
  AND t.handle_seconds >= 600
ORDER BY t.handle_seconds DESC, t.ticket_id ASC;

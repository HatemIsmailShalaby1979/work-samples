-- =============================================================================
-- Query 03 — GROUP BY / HAVING
-- =============================================================================
-- Question: which agents are underperforming on customer satisfaction, once
--           small samples are excluded?
--
-- WHY HAVING, AND NOT WHERE
-- -------------------------
-- The two predicates here are not the same kind of thing, and SQL evaluates
-- them at different stages:
--
--   WHERE  runs BEFORE grouping. It filters ROWS. `t.csat_score IS NOT NULL`
--          belongs here — it decides which individual survey rows enter the
--          aggregate at all. Moving it to HAVING would be a logic error: HAVING
--          cannot see individual rows, only the groups they collapsed into.
--
--   HAVING runs AFTER grouping. It filters GROUPS. `COUNT(*) >= 5` and
--          `AVG(t.csat_score) < 4.1` are properties of a group, not of any one
--          row, so they cannot be expressed in WHERE at all.
--
-- The `COUNT(*) >= 5` guard is the substantive part. Without it, an agent with
-- one bad survey ranks bottom of the table and the ranking is noise. The
-- threshold makes the output a finding rather than an artefact of sample size.
-- =============================================================================

SELECT
    a.agent_id,
    a.agent_name,
    tm.team_name,
    COUNT(*)                    AS surveys,
    ROUND(AVG(t.csat_score), 2) AS avg_csat,
    MIN(t.csat_score)           AS min_csat,
    MAX(t.csat_score)           AS max_csat
FROM tickets AS t
INNER JOIN agents AS a
        ON a.agent_id = t.agent_id
INNER JOIN teams AS tm
        ON tm.team_id = a.team_id
WHERE t.csat_score IS NOT NULL      -- row filter: keep only returned surveys
GROUP BY a.agent_id, a.agent_name, tm.team_name
HAVING COUNT(*) >= 5                -- group filter: ignore small samples
   AND AVG(t.csat_score) < 4.1      -- group filter: the actual finding
ORDER BY avg_csat ASC, a.agent_id ASC;

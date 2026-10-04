-- =============================================================================
-- Query 05 — window function: RANK within a partition
-- =============================================================================
-- Question: how does each agent rank against their own team on CSAT, and how
--           far are they from the team average?
--
-- Why a window function and not GROUP BY
-- --------------------------------------
-- GROUP BY would collapse each team to a single row and lose the agents.
-- A window function computes an aggregate ACROSS a partition while keeping
-- every detail row. So one pass returns, per agent: their own average, their
-- rank inside the team, and the team's average — the comparison and the
-- underlying rows in the same result.
--
-- `PARTITION BY` defines the window; `ORDER BY` inside `OVER` defines the rank
-- order. The `agent_id` tiebreaker keeps the ranking deterministic when two
-- agents hold the same average.
--
-- The inner CTE aggregates first, so the window operates over one row per agent
-- rather than over the 411 raw survey rows.
-- =============================================================================

WITH agent_csat AS (
    SELECT
        a.team_id,
        a.agent_id,
        a.agent_name,
        COUNT(*)                    AS surveys,
        AVG(t.csat_score)           AS avg_csat_raw
    FROM tickets AS t
    INNER JOIN agents AS a
            ON a.agent_id = t.agent_id
    WHERE t.csat_score IS NOT NULL
    GROUP BY a.team_id, a.agent_id, a.agent_name
)
SELECT
    tm.team_name,
    ac.agent_name,
    ac.surveys,
    ROUND(ac.avg_csat_raw, 2) AS avg_csat,
    RANK() OVER (
        PARTITION BY ac.team_id
        ORDER BY ac.avg_csat_raw DESC, ac.agent_id ASC
    )                                                          AS csat_rank_in_team,
    ROUND(AVG(ac.avg_csat_raw) OVER (PARTITION BY ac.team_id), 2) AS team_avg_csat,
    ROUND(ac.avg_csat_raw - AVG(ac.avg_csat_raw) OVER (PARTITION BY ac.team_id), 2) AS vs_team_avg
FROM agent_csat AS ac
INNER JOIN teams AS tm
        ON tm.team_id = ac.team_id
ORDER BY tm.team_name ASC, csat_rank_in_team ASC;

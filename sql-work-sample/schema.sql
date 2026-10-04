-- =============================================================================
-- Contact-centre operations — schema
-- =============================================================================
-- Engine : SQLite 3
-- Data   : 100% synthetic. No real customer, agent or employer data.
-- Notes  : Tables only. The index is created deliberately in
--          queries/07_index_and_query_plan.sql so that the query-plan change
--          it causes can be measured rather than assumed.
-- =============================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS interval_volumes;
DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS agents;
DROP TABLE IF EXISTS queues;
DROP TABLE IF EXISTS teams;

-- -----------------------------------------------------------------------------
-- teams — an operational team, sited at one location
-- -----------------------------------------------------------------------------
CREATE TABLE teams (
    team_id      INTEGER PRIMARY KEY,
    team_name    TEXT    NOT NULL UNIQUE,
    site         TEXT    NOT NULL,
    manager_name TEXT    NOT NULL
);

-- -----------------------------------------------------------------------------
-- queues — a service queue with its own answer-time and service-level targets
-- -----------------------------------------------------------------------------
CREATE TABLE queues (
    queue_id                 INTEGER PRIMARY KEY,
    queue_name               TEXT    NOT NULL UNIQUE,
    channel                  TEXT    NOT NULL CHECK (channel IN ('phone', 'chat', 'email')),
    target_answer_seconds    INTEGER NOT NULL CHECK (target_answer_seconds > 0),
    target_service_level_pct REAL    NOT NULL CHECK (target_service_level_pct BETWEEN 0 AND 100)
);

-- -----------------------------------------------------------------------------
-- agents — a frontline agent belonging to exactly one team
-- -----------------------------------------------------------------------------
CREATE TABLE agents (
    agent_id        INTEGER PRIMARY KEY,
    agent_name      TEXT    NOT NULL,
    team_id         INTEGER NOT NULL REFERENCES teams (team_id),
    hire_date       TEXT    NOT NULL,   -- ISO-8601 date, YYYY-MM-DD
    employment_type TEXT    NOT NULL CHECK (employment_type IN ('full_time', 'part_time')),
    active          INTEGER NOT NULL CHECK (active IN (0, 1))
);

-- -----------------------------------------------------------------------------
-- tickets — one contact, from creation to resolution
--
-- agent_id is NULLABLE on purpose: an abandoned contact is never assigned to
-- an agent. That single nullable key is what makes the join-cardinality
-- explanation in queries/02_filtered_join.sql worth writing down.
-- -----------------------------------------------------------------------------
CREATE TABLE tickets (
    ticket_id      INTEGER PRIMARY KEY,
    created_at     TEXT    NOT NULL,   -- ISO-8601 timestamp, YYYY-MM-DD HH:MM:SS
    resolved_at    TEXT,               -- NULL while the contact is open
    queue_id       INTEGER NOT NULL REFERENCES queues (queue_id),
    agent_id       INTEGER REFERENCES agents (agent_id),
    status         TEXT    NOT NULL CHECK (status IN ('resolved', 'unresolved', 'escalated', 'abandoned')),
    channel        TEXT    NOT NULL CHECK (channel IN ('phone', 'chat', 'email')),
    fcr            INTEGER CHECK (fcr IN (0, 1)),          -- first-contact resolution; NULL when not applicable
    csat_score     INTEGER CHECK (csat_score BETWEEN 1 AND 5),  -- NULL when no survey was returned
    handle_seconds INTEGER NOT NULL CHECK (handle_seconds >= 0),
    wait_seconds   INTEGER NOT NULL CHECK (wait_seconds >= 0)
);

-- -----------------------------------------------------------------------------
-- interval_volumes — weekly offered / answered / abandoned volumes per queue
-- Kept separate from `tickets` because abandonment is counted at the interval
-- level in real WFM reporting, not reconstructed from ticket rows.
-- -----------------------------------------------------------------------------
CREATE TABLE interval_volumes (
    interval_id    INTEGER PRIMARY KEY,
    interval_start TEXT    NOT NULL,   -- ISO-8601 date of the week start (Monday)
    queue_id       INTEGER NOT NULL REFERENCES queues (queue_id),
    offered        INTEGER NOT NULL CHECK (offered >= 0),
    answered       INTEGER NOT NULL CHECK (answered >= 0),
    abandoned      INTEGER NOT NULL CHECK (abandoned >= 0),
    UNIQUE (interval_start, queue_id)
);

#!/usr/bin/env python3
"""Generate a deterministic synthetic contact-centre dataset as seed.sql.

The dataset is entirely invented. No real customer, agent, employer, queue or
site data appears anywhere in it, and no employer system was consulted.

Determinism
-----------
A single fixed seed drives a private ``random.Random`` instance, so repeated runs
on the same Python build emit byte-identical SQL. ``seed.sql`` is committed as the
source of truth; this script exists so the data can be regenerated and audited,
not so it can be relied on across Python major versions.

Two properties are deliberate and are documented in README.md:

1. September waits are generated ~15% lower than August waits, so the
   period-over-period query in queries/08 has a real change to find.
2. Agent quality offsets are fixed per agent, so the HAVING query in queries/03
   returns a small, stable set rather than an empty one.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

SEED = 20261004
OUT_PATH = "seed.sql"

# --- Reference data -----------------------------------------------------------

TEAMS = [
    (1, "Alpha", "Cairo", "Mona Farouk"),
    (2, "Bravo", "Cairo", "Youssef Adel"),
    (3, "Charlie", "Alexandria", "Rania Habib"),
]

QUEUES = [
    (1, "Billing", "phone", 30, 80.0),
    (2, "Technical", "phone", 45, 75.0),
    (3, "General", "chat", 60, 80.0),
    (4, "Escalations", "email", 240, 90.0),
]

AGENT_NAMES = [
    "Amal Nabil", "Bassem Kamal", "Carla Adel", "Dina Samir",
    "Ehab Rashad", "Farida Lotfy", "Gamal Hosny", "Hana Tarek",
    "Ibrahim Zaki", "Jasmin Adel", "Karim Fathy", "Laila Mounir",
]

# Fixed per-agent quality offset. Negative values pull an agent's CSAT average
# below the HAVING threshold used in queries/03.
AGENT_OFFSET = [0.3, 0.1, -0.7, 0.0, 0.2, -0.9, 0.1, 0.4, -0.5, 0.2, -0.1, -0.6]

# Mean wait and handle seconds per queue_id.
QUEUE_WAIT = {1: 22, 2: 38, 3: 48, 4: 190}
QUEUE_HANDLE = {1: 240, 2: 420, 3: 300, 4: 900}

PERIOD_START = date(2026, 8, 1)
PERIOD_END = date(2026, 9, 30)
SEPTEMBER_WAIT_FACTOR = 0.85  # deliberate, documented improvement trend

STATUS_WEIGHTS = [("resolved", 85), ("unresolved", 6), ("escalated", 5), ("abandoned", 4)]
CSAT_DELTA_WEIGHTS = [-1, 0, 1]
CSAT_DELTA_PROBS = [0.1, 0.6, 0.3]


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def build() -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Return the INSERT statements for each table, in load order."""
    rng = random.Random(SEED)

    teams_sql = [
        "INSERT INTO teams (team_id, team_name, site, manager_name) VALUES",
    ]
    teams_sql.append(",\n".join(
        f"    ({tid}, '{name}', '{site}', '{mgr}')" for tid, name, site, mgr in TEAMS
    ) + ";")

    queues_sql = [
        "INSERT INTO queues (queue_id, queue_name, channel, target_answer_seconds, "
        "target_service_level_pct) VALUES",
    ]
    queues_sql.append(",\n".join(
        f"    ({qid}, '{name}', '{chan}', {target}, {sl})"
        for qid, name, chan, target, sl in QUEUES
    ) + ";")

    agents_sql = ["INSERT INTO agents (agent_id, agent_name, team_id, hire_date, "
                  "employment_type, active) VALUES"]
    agent_rows = []
    for index, name in enumerate(AGENT_NAMES, start=1):
        team_id = (index - 1) // 4 + 1
        hire_year = 2019 + (index % 5)
        hire_month = (index * 3) % 12 + 1
        hire_day = (index * 7) % 27 + 1
        employment = "part_time" if index % 7 == 0 else "full_time"
        active = 0 if index == 12 else 1  # one leaver, so "active" is not a constant
        agent_rows.append(
            f"    ({index}, '{name}', {team_id}, '{hire_year:04d}-{hire_month:02d}-{hire_day:02d}', "
            f"'{employment}', {active})"
        )
    agents_sql.append(",\n".join(agent_rows) + ";")

    # --- tickets --------------------------------------------------------------
    ticket_rows: list[str] = []
    ticket_id = 0
    day = PERIOD_START
    while day <= PERIOD_END:
        is_weekend = day.weekday() >= 5
        volume = rng.randint(8, 14) if is_weekend else rng.randint(18, 26)
        in_september = day.month == 9

        for _ in range(volume):
            ticket_id += 1
            queue_id = rng.choices([1, 2, 3, 4], weights=[40, 28, 22, 10])[0]
            channel = dict((q[0], q[2]) for q in QUEUES)[queue_id]

            hour = rng.randint(8, 19)
            minute = rng.randint(0, 59)
            second = rng.randint(0, 59)
            created = datetime(day.year, day.month, day.day, hour, minute, second)

            status = rng.choices(
                [s for s, _ in STATUS_WEIGHTS], weights=[w for _, w in STATUS_WEIGHTS]
            )[0]

            mean_wait = QUEUE_WAIT[queue_id]
            if in_september:
                mean_wait = mean_wait * SEPTEMBER_WAIT_FACTOR
            wait_seconds = max(1, int(rng.gauss(mean_wait, mean_wait * 0.45)))

            mean_handle = QUEUE_HANDLE[queue_id]
            handle_seconds = max(20, int(rng.gauss(mean_handle, mean_handle * 0.30)))

            fcr = None
            csat = None
            resolved_at = None

            if status == "abandoned":
                # An abandoned contact never reaches an agent. This is the row
                # class the join-cardinality explanation in queries/02 turns on.
                agent_id = None
                handle_seconds = 0
                wait_seconds = max(wait_seconds, 45)
            else:
                agent_id = rng.randint(1, len(AGENT_NAMES))
                if status == "escalated":
                    handle_seconds = int(handle_seconds * 1.6)
                resolved_at = created + timedelta(seconds=wait_seconds + handle_seconds)
                if status == "resolved":
                    fcr = 1 if rng.random() < 0.70 else 0
                    if rng.random() < 0.45:
                        base = 4.3
                        delta = rng.choices(CSAT_DELTA_WEIGHTS, weights=CSAT_DELTA_PROBS)[0]
                        csat = clamp(round(base + AGENT_OFFSET[agent_id - 1] + delta), 1, 5)
                elif status == "unresolved":
                    resolved_at = None

            created_s = created.strftime("%Y-%m-%d %H:%M:%S")
            resolved_s = f"'{resolved_at.strftime('%Y-%m-%d %H:%M:%S')}'" if resolved_at else "NULL"
            agent_s = "NULL" if agent_id is None else str(agent_id)
            fcr_s = "NULL" if fcr is None else str(fcr)
            csat_s = "NULL" if csat is None else str(csat)

            ticket_rows.append(
                f"({ticket_id}, '{created_s}', {resolved_s}, {queue_id}, {agent_s}, "
                f"'{status}', '{channel}', {fcr_s}, {csat_s}, {handle_seconds}, {wait_seconds})"
            )
        day += timedelta(days=1)

    tickets_sql = [
        "INSERT INTO tickets (ticket_id, created_at, resolved_at, queue_id, agent_id, "
        "status, channel, fcr, csat_score, handle_seconds, wait_seconds) VALUES",
    ]
    for start in range(0, len(ticket_rows), 40):
        chunk = ticket_rows[start:start + 40]
        tickets_sql.append(",\n".join(chunk) + ";")
        tickets_sql.append("INSERT INTO tickets (ticket_id, created_at, resolved_at, queue_id, "
                           "agent_id, status, channel, fcr, csat_score, handle_seconds, "
                           "wait_seconds) VALUES")
    tickets_sql.pop()  # drop the trailing INSERT prefix

    # --- interval_volumes -----------------------------------------------------
    interval_rows: list[str] = []
    interval_id = 0
    week_start = date(2026, 8, 3)  # a Monday
    for _ in range(9):
        for queue_id, _, _, _, _ in QUEUES:
            interval_id += 1
            offered = rng.randint(600, 1400)
            abandon_rate = {1: 0.05, 2: 0.07, 3: 0.04, 4: 0.02}[queue_id]
            abandoned = int(offered * abandon_rate * rng.uniform(0.7, 1.3))
            answered = offered - abandoned
            interval_rows.append(
                f"    ({interval_id}, '{week_start.isoformat()}', {queue_id}, "
                f"{offered}, {answered}, {abandoned})"
            )
        week_start += timedelta(days=7)

    intervals_sql = [
        "INSERT INTO interval_volumes (interval_id, interval_start, queue_id, offered, "
        "answered, abandoned) VALUES",
        ",\n".join(interval_rows) + ";",
    ]

    return teams_sql, queues_sql, agents_sql, tickets_sql, intervals_sql


def main() -> None:
    teams_sql, queues_sql, agents_sql, tickets_sql, intervals_sql = build()

    header = [
        "-- =============================================================================",
        "-- seed.sql — deterministic synthetic contact-centre data",
        "-- =============================================================================",
        "-- GENERATED FILE. Do not hand-edit.",
        "-- Regenerate with:  python tools/generate_seed.py",
        f"-- Seed: {SEED}    Period: {PERIOD_START} .. {PERIOD_END}",
        "--",
        "-- Entirely invented data. No real customer, agent, employer or site appears here.",
        "-- =============================================================================",
        "",
        "PRAGMA foreign_keys = ON;",
        "",
    ]

    sections = [
        ("-- --- teams --------------------------------------------------------------", teams_sql),
        ("-- --- queues -------------------------------------------------------------", queues_sql),
        ("-- --- agents -------------------------------------------------------------", agents_sql),
        ("-- --- tickets ------------------------------------------------------------", tickets_sql),
        ("-- --- interval_volumes ---------------------------------------------------", intervals_sql),
    ]

    lines = list(header)
    for banner, statements in sections:
        lines.append(banner)
        lines.extend(statements)
        lines.append("")

    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))

    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()

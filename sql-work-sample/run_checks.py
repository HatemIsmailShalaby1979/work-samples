#!/usr/bin/env python3
"""Build the database from scratch, run every query, and check the results.

Standard library only. No third-party dependency, no network, no cloud service.

What it does
------------
1. Deletes and rebuilds ``build/contact_centre.db`` from ``schema.sql`` +
   ``seed.sql``, so every run starts from a clean state.
2. Parses each file in ``queries/`` into individual statements.
3. Executes them in filename order and formats the output deterministically.
4. Compares each result against the committed file in ``expected/``.
5. For ``queries/07_index_and_query_plan.sql``, additionally measures
   ``EXPLAIN QUERY PLAN`` with the index absent and then present, and writes the
   two plans side by side.

Usage
-----
    python run_checks.py                  # check against expected/
    python run_checks.py --update-expected  # regenerate expected/ from current run

Exit code is 0 when every check passes, 1 otherwise.

The committed files in ``expected/`` are the specification. If a query changes,
``expected/`` must be regenerated deliberately and the diff reviewed — a silent
change in output is exactly what these checks exist to catch.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent
DB_PATH = ROOT / "build" / "contact_centre.db"
QUERY_DIR = ROOT / "queries"
EXPECTED_DIR = ROOT / "expected"
PLAN_FILE = EXPECTED_DIR / "query_plan.txt"
INDEX_NAME = "idx_tickets_created_at"

NULL = "NULL"


# --- SQL parsing --------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")


def strip_comments(sql: str) -> str:
    """Remove -- and /* */ comments so statement splitting is safe."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", sql))


def split_statements(sql: str) -> list[str]:
    """Split a script into non-empty statements on semicolons."""
    cleaned = strip_comments(sql)
    return [part.strip() for part in cleaned.split(";") if part.strip()]


# --- Output formatting --------------------------------------------------------

def format_rows(columns: list[str], rows: list[tuple]) -> str:
    """Format a result set as pipe-delimited text, with a row count footer."""
    lines = ["|".join(columns)]
    for row in rows:
        lines.append("|".join(NULL if value is None else str(value) for value in row))
    lines.append(f"-- rows: {len(rows)}")
    return "\n".join(lines)


def run_statement(conn: sqlite3.Connection, statement: str) -> str:
    """Execute one statement and return its formatted output."""
    cursor = conn.execute(statement)
    if cursor.description is None:  # DDL / DML, no result set
        return f"(statement executed; rows affected: {cursor.rowcount})"
    columns = [description[0] for description in cursor.description]
    return format_rows(columns, cursor.fetchall())


def explain_plan(conn: sqlite3.Connection, statement: str) -> str:
    """Return the EXPLAIN QUERY PLAN detail lines for a statement."""
    rows = conn.execute("EXPLAIN QUERY PLAN " + statement).fetchall()
    # (id, parent, notused, detail) — the detail column is the readable one.
    return "\n".join(f"  {row[3]}" for row in rows)


# --- Database build -----------------------------------------------------------

def build_database() -> sqlite3.Connection:
    """Rebuild the database from schema + seed. Always starts clean."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    for script in ("schema.sql", "seed.sql"):
        conn.executescript((ROOT / script).read_text(encoding="utf-8"))
    conn.commit()
    return conn


# --- Checks -------------------------------------------------------------------

def check_standard_query(conn: sqlite3.Connection, path: pathlib.Path,
                         update: bool) -> tuple[str, bool, str]:
    """Run every statement in a normal query file and compare to expected."""
    statements = split_statements(path.read_text(encoding="utf-8"))
    blocks = []
    for position, statement in enumerate(statements, start=1):
        label = f"-- {path.name}  [statement {position}]"
        blocks.append(label + "\n" + run_statement(conn, statement))
    actual = "\n\n".join(blocks)

    expected_path = EXPECTED_DIR / f"{path.stem}.txt"
    if update:
        expected_path.write_text(actual + "\n", encoding="utf-8")
        return path.name, True, "written"

    if not expected_path.exists():
        return path.name, False, "no expected file"

    expected = expected_path.read_text(encoding="utf-8").rstrip("\n")
    if expected == actual:
        return path.name, True, "match"
    return path.name, False, "MISMATCH"


def check_index_and_plan(conn: sqlite3.Connection, path: pathlib.Path,
                         update: bool) -> tuple[str, bool, str]:
    """Measure the query plan without the index, then with it."""
    statements = split_statements(path.read_text(encoding="utf-8"))

    index_statements = [s for s in statements if s.upper().startswith("CREATE INDEX")]
    query_statements = [s for s in statements if not s.upper().startswith("CREATE INDEX")]

    if len(index_statements) != 1 or len(query_statements) != 1:
        return path.name, False, (
            "expected exactly one CREATE INDEX and one query in this file, found "
            f"{len(index_statements)} and {len(query_statements)}"
        )

    index_statement = index_statements[0]
    query = query_statements[0]

    # 1. Plan with no index at all.
    conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    plan_before = explain_plan(conn, query)

    # 2. Create the index, then re-plan the identical query.
    conn.execute(index_statement)
    plan_after = explain_plan(conn, query)
    conn.commit()

    used_index = "USING INDEX" in plan_after.upper() or "USING COVERING INDEX" in plan_after.upper()

    report = "\n".join([
        f"-- {path.name} — query plan comparison",
        "",
        "query under study:",
        "  SELECT DATE(created_at) AS day, COUNT(*) AS tickets",
        "  FROM tickets",
        "  WHERE created_at >= '2026-09-01 00:00:00'",
        "    AND created_at <  '2026-10-01 00:00:00'",
        "  GROUP BY DATE(created_at)",
        "  ORDER BY day ASC",
        "",
        "EXPLAIN QUERY PLAN — without idx_tickets_created_at:",
        plan_before,
        "",
        "EXPLAIN QUERY PLAN — with idx_tickets_created_at:",
        plan_after,
        "",
        f"plan changed: {'YES' if plan_before != plan_after else 'NO'}",
        f"index used by the planner: {'YES' if used_index else 'NO'}",
        "",
        "row count is unchanged by the index — an index changes HOW the rows are",
        "found, never WHICH rows come back. The result set is checked below.",
        "",
        "-- result with the index present",
        run_statement(conn, query),
    ])

    expected_path = PLAN_FILE
    if update:
        expected_path.write_text(report + "\n", encoding="utf-8")
        return path.name, True, "written"

    if not expected_path.exists():
        return path.name, False, "no expected file"

    expected = expected_path.read_text(encoding="utf-8").rstrip("\n")
    if expected != report:
        return path.name, False, "MISMATCH in plan report"

    if plan_before == plan_after:
        return path.name, False, "plan did NOT change when the index was added"
    return path.name, True, f"plan changed; index used: {used_index}"


# --- Entry point --------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-expected", action="store_true",
                        help="regenerate expected/ from the current run")
    args = parser.parse_args()

    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    conn = build_database()

    print("=" * 72)
    print("SQL work sample — checks")
    print("=" * 72)
    print(f"database : {DB_PATH.relative_to(ROOT)}")
    for table in ("teams", "queues", "agents", "tickets", "interval_volumes"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<18} {count:>6} rows")
    print()

    query_files = sorted(QUERY_DIR.glob("*.sql"))
    if not query_files:
        print("no query files found", file=sys.stderr)
        return 1

    results: list[tuple[str, bool, str]] = []
    for path in query_files:
        if path.name.startswith("07_"):
            results.append(check_index_and_plan(conn, path, args.update_expected))
        else:
            results.append(check_standard_query(conn, path, args.update_expected))

    conn.close()

    width = max(len(name) for name, _, _ in results)
    failures = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"  [{status}] {name:<{width}}  {detail}")

    print()
    print(f"{len(results) - failures}/{len(results)} checks passed")
    if args.update_expected:
        print("expected/ regenerated — review the diff before committing")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

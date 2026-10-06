#!/usr/bin/env python3
"""Run the same checks CI runs, locally, and report the exact command and result.

This exists because a workflow file that has never been executed is a wish, not
a check. Every step below is run here and its real output is reported — pass or
fail — so the state of the repository can be stated from evidence rather than
assumed.

    python scripts/ci.py                 # all steps
    python scripts/ci.py --skip-docker   # everything except the image build
    python scripts/ci.py --only pytest   # one step

Exit code is 0 when every executed step passes, 1 otherwise.

The steps mirror .github/workflows/ci.yml. If one changes, both must change.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Step:
    """One check: a name, the command, and whether it is skippable."""

    name: str
    command: list[str]
    description: str
    needs_docker: bool = False


def _ruff_command() -> list[str]:
    """Prefer a ruff on PATH; fall back to the module form."""
    if shutil.which("ruff"):
        return ["ruff"]
    return [sys.executable, "-m", "ruff"]


def build_steps() -> list[Step]:
    ruff = _ruff_command()
    return [
        Step(
            name="format",
            command=[*ruff, "format", "--check", "--diff", "."],
            description="formatting — ruff format --check",
        ),
        Step(
            name="lint",
            command=[*ruff, "check", "."],
            description="linting — ruff check",
        ),
        Step(
            name="typecheck",
            command=[sys.executable, "-m", "mypy", "src", "--ignore-missing-imports"],
            description="types — mypy src",
        ),
        Step(
            name="pytest",
            command=[sys.executable, "-m", "pytest", "-q"],
            description="tests — pytest",
        ),
        Step(
            name="eval",
            command=[sys.executable, "run_eval.py"],
            description="evaluation report matches expected/",
        ),
        Step(
            name="docker-build",
            command=["docker", "build", "-t", "support-assistant-work-sample:ci", "."],
            description="image build — docker build",
            needs_docker=True,
        ),
    ]


def run_step(step: Step, verbose: bool) -> tuple[bool, str]:
    """Run one step. Returns (passed, first meaningful output line)."""
    printable = " ".join(step.command)
    print(f"\n{'=' * 78}")
    print(f"  {step.name}: {step.description}")
    print(f"  $ {printable}")
    print("=" * 78)

    try:
        completed = subprocess.run(
            step.command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as error:
        print(f"  SKIPPED — command not found: {error.filename}")
        return False, f"command not found: {error.filename}"

    output = (completed.stdout or "") + (completed.stderr or "")
    tail = output.strip().splitlines()
    if verbose:
        print(output)
    else:
        for line in tail[-12:]:
            print(f"  | {line}")

    passed = completed.returncode == 0
    print(f"  -> {'PASS' if passed else 'FAIL'} (exit {completed.returncode})")
    summary = tail[-1] if tail else ""
    return passed, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-docker", action="store_true", help="skip the image build"
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="run only the named step(s); may be repeated",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print full command output, not just the tail",
    )
    args = parser.parse_args()

    steps = build_steps()
    if args.only:
        steps = [step for step in steps if step.name in set(args.only)]
        if not steps:
            print(f"no matching steps for {args.only}", file=sys.stderr)
            return 1
    if args.skip_docker:
        steps = [step for step in steps if not step.needs_docker]

    results: list[tuple[str, bool, str]] = []
    for step in steps:
        passed, summary = run_step(step, args.verbose)
        results.append((step.name, passed, summary))

    width = max(len(name) for name, _, _ in results)
    print(f"\n{'=' * 78}")
    print("  summary")
    print("=" * 78)
    failures = 0
    for name, passed, summary in results:
        if not passed:
            failures += 1
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:<{width}}  {summary[:60]}")

    print(f"\n  {len(results) - failures}/{len(results)} steps passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Add working-directory to every job in the moved CI workflow.

The workflow was committed at rag-work-sample/.github/workflows/ci.yml, where
GitHub never read it -- GitHub only loads .github/workflows from the repository
root, which is why this repository had a complete five-job workflow and zero
runs. Moving the file up is only half the fix: every `run:` step was written to
execute from inside the sample directory, so at the root they would fail on
missing paths.

This adds `defaults.run.working-directory` per job rather than editing each
step, which keeps the diff to one line per job.
"""

from __future__ import annotations

import pathlib
import sys

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

# The directory each job's commands are written against.
JOB_DIRS = {
    "lint": "rag-work-sample",
    "typecheck": "rag-work-sample",
    "test": "rag-work-sample",
    "evaluation": "rag-work-sample",
    # The build job only shells out to docker with an explicit -f context path,
    # so it must run from the repository root. Left absent deliberately.
}


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    original = text

    if "working-directory" in text:
        print("working-directory already present; nothing to do")
        return 0

    for job, directory in JOB_DIRS.items():
        anchor = f"  {job}:\n"
        if anchor not in text:
            print(f"error: job '{job}' not found in the workflow", file=sys.stderr)
            return 1

        # `defaults` belongs under the job, immediately before `runs-on`.
        marker = f"  {job}:\n"
        idx = text.index(marker)
        runs_on = text.index("    runs-on:", idx)
        inject = (f"    defaults:\n"
                  f"      run:\n"
                  f"        working-directory: {directory}\n")
        text = text[:runs_on] + inject + text[runs_on:]

    if text == original:
        print("error: no changes made", file=sys.stderr)
        return 1

    WORKFLOW.write_text(text, encoding="utf-8", newline="\n")
    print(f"added working-directory to {len(JOB_DIRS)} jobs: "
          f"{', '.join(JOB_DIRS)}")
    print("build job intentionally left at the repository root: it uses an "
          "explicit docker -f context path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
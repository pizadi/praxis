#!/usr/bin/env python3
"""Fail when an English/Persian documentation pair drifts into one tree.

Without ``--base-ref`` this checks that every file in ``docs/`` has a matching
file in ``docs_fa/`` (and vice versa), plus the README pair. With a Git base it
also fails when one side of a pair changed in a PR but the other did not.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def paired_names() -> tuple[set[str], set[str]]:
    docs = {p.name for p in (ROOT / "docs").glob("*.md")}
    docs_fa = {p.name for p in (ROOT / "docs_fa").glob("*.md")}
    return docs, docs_fa


def changed_files(base_ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return set(result.stdout.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Git revision to compare changed pairs against")
    args = parser.parse_args()

    docs, docs_fa = paired_names()
    failures: list[str] = []
    if missing := sorted(docs - docs_fa):
        failures.append(f"missing docs_fa translations: {missing}")
    if missing := sorted(docs_fa - docs):
        failures.append(f"unexpected docs_fa files without docs/: {missing}")
    if (ROOT / "README.md").exists() != (ROOT / "README_fa.md").exists():
        failures.append("README.md and README_fa.md must exist as a pair")

    if args.base_ref:
        changes = changed_files(args.base_ref)
        for english in sorted(docs):
            english_changed = f"docs/{english}" in changes
            persian_changed = f"docs_fa/{english}" in changes
            if english_changed != persian_changed:
                failures.append(
                    f"documentation pair changed on one side only: docs/{english}"
                )
        for name in ("README.md", "README_fa.md"):
            other = "README_fa.md" if name == "README.md" else "README.md"
            if (name in changes) != (other in changes):
                failures.append(f"README pair changed on one side only: {name}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("documentation pairs are aligned")
    return 0


if __name__ == "__main__":
    sys.exit(main())

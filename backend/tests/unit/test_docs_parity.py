"""Documentation pair structure is checked together with scripts/check_doc_pairs.py."""

import pathlib
import subprocess
import sys

BACKEND_ROOT = pathlib.Path(__file__).parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def test_english_and_persian_doc_file_sets_match():
    docs = {p.name for p in (REPO_ROOT / "docs").glob("*.md")}
    docs_fa = {p.name for p in (REPO_ROOT / "docs_fa").glob("*.md")}
    assert docs == docs_fa
    assert (REPO_ROOT / "README.md").exists() == (REPO_ROOT / "README_fa.md").exists()


def test_doc_pair_checker_passes():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_doc_pairs.py")],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

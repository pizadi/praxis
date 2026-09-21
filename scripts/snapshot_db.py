#!/usr/bin/env python3
"""Snapshot a clinic database before migrations / destructive operations.

PostgreSQL (the compose stack): streams a `pg_dump --format=custom` archive
out of the running db container via `docker exec` — credentials stay inside
the container, no host pg_dump needed. SQLite: byte-copies the database file
(plus -journal/-wal sidecars) for dev databases.

Usage:
  python snapshot_db.py --label pre-1.3.0-deploy            # PG via docker
  python snapshot_db.py --sqlite-path backend/data/x.db     # SQLite copy

Snapshots land in work/db-snapshots/<UTC timestamp>-<label>.dump and are
validated (size, PGDMP magic, pg_restore --list) before the script reports
success.

Rollback (PostgreSQL), from the repo root:
  docker compose stop api
  docker exec -i new-patients-db-1 sh -c \
      'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
      < work/db-snapshots/<snapshot>.dump
  docker compose start api

Exit 0 = snapshot taken and validated. Non-zero = no snapshot was produced
(treat the database as NOT protected).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

MAGIC = b"PGDMP"
CONTAINER = "new-patients-db-1"


def snapshot_dir() -> Path:
    here = Path(__file__).resolve().parent.parent
    d = here / "work" / "db-snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def target_path(label: str, ext: str) -> Path:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return snapshot_dir() / f"{ts}-{label}{ext}"


def snapshot_postgres(container: str, out: Path) -> None:
    cmd = [
        "docker",
        "exec",
        container,
        "sh",
        "-c",
        'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom',
    ]
    with out.open("wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE)  # noqa: S603
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        sys.exit(f"pg_dump failed ({proc.returncode}):\n{proc.stderr.decode(errors='replace')}")


def validate_postgres(container: str, out: Path) -> None:
    data = out.read_bytes()
    if len(data) < 100 or not data.startswith(MAGIC):
        sys.exit(f"{out}: not a pg_dump custom archive (size {len(data)})")
    with out.open("rb") as fh:
        check = subprocess.run(  # noqa: S603
            ["docker", "exec", "-i", container, "pg_restore", "--list"],
            stdin=fh,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    if check.returncode != 0:
        sys.exit(
            f"{out}: pg_restore --list rejected the archive:\n"
            f"{check.stderr.decode(errors='replace')}"
        )


def snapshot_sqlite(db_path: Path, out: Path) -> None:
    out.write_bytes(db_path.read_bytes())
    for side in ("-journal", "-wal", "-shm"):
        side_path = db_path.with_name(db_path.name + side)
        if side_path.exists():
            shutil.copy2(side_path, out.with_suffix(out.suffix + side))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="snapshot", help="filename label, e.g. pre-1.3.0-deploy")
    parser.add_argument("--container", default=CONTAINER, help="docker container hosting postgres")
    parser.add_argument("--sqlite-path", type=Path, help="snapshot this SQLite file instead of PG")
    args = parser.parse_args()

    if args.sqlite_path:
        out = target_path(args.label, ".db")
        snapshot_sqlite(args.sqlite_path, out)
        print(f"sqlite snapshot: {args.sqlite_path} -> {out} ({out.stat().st_size} bytes)")
        return 0

    out = target_path(args.label, ".dump")
    snapshot_postgres(args.container, out)
    validate_postgres(args.container, out)
    print(f"postgres snapshot: {out} ({out.stat().st_size} bytes) — validated")
    print("rollback: see the docstring of scripts/snapshot_db.py (pg_restore --clean --if-exists)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

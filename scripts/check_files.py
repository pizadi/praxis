#!/usr/bin/env python3
"""Check that file-backed attachments in the DB exist on disk under UPLOAD_DIR.

Usage:
  python check_files.py --database-url URL --upload-dir DIR

Exit 0 = all files present. Exit 1 = some files missing (with a report).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--upload-dir", required=True, type=Path)
    args = parser.parse_args()

    engine = create_async_engine(args.database_url)
    upload_dir: Path = args.upload_dir
    print(f"upload dir: {upload_dir.resolve()}")
    if not upload_dir.is_dir():
        print("FATAL: upload dir does not exist — nothing can be downloaded")
        return 1

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, stored_filename FROM attachments"
                    " WHERE stored_filename IS NOT NULL"
                )
            )
        ).all()
    if not rows:
        print("no file-backed attachments in DB")
        return 0

    missing = [aid for aid, name in rows if not (upload_dir / name).is_file()]
    print(f"file-backed attachments: {len(rows)}")
    print(f"present on disk:        {len(rows) - len(missing)}")
    print(f"missing on disk:        {len(missing)}")
    if missing:
        print("first missing ids:", missing[:20])
        print(
            "\nThis is the cause of download 404s. The DB references files that"
            " are not in this upload dir. Typical cause: the migration was run"
            " with --upload-dir pointing at a different directory than the one"
            " mounted into the api container (docker-compose 'uploads' volume)."
        )
        return 1
    print("OK — all DB-referenced files present on disk")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

# Migration from the legacy system (SQLite → PostgreSQL)

Tooling: `scripts/migrate_sqlite.py`, `scripts/check_files.py`,
`scripts/verify_import.py`, `scripts/make_test_legacy_db.py`.

**Never point the script at the live DB.** Snapshot first:

```bash
# on the box running the old system, during quiet hours:
systemctl stop old-patients   # or however it runs
cp /path/to/db.sqlite3  snapshot/db.sqlite3
cp -r /path/to/patient_files  snapshot/patient_files
systemctl start old-patients  # old system keeps running meanwhile
```

Then, from this repo (target the Postgres mapped to host port 5434):

```bash
# dry run (no writes) — counts, data-quality report, verification:
.venv/bin/python scripts/migrate_sqlite.py \
  --source snapshot/db.sqlite3 \
  --files  snapshot/patient_files \
  --database-url postgresql+asyncpg://clinic:PASS@localhost:5434/clinic \
  --upload-dir /var/lib/clinic/uploads

# real run (idempotent; safe to re-run):
... --apply
```

## Behavior

- **1:1 mapping** — PKs and all values preserved; join tables rebuilt.
- Legacy `Appointment_Date` naive local datetimes are stored as
  `timestamptz` assuming Asia/Tehran (+03:30).
- Files are copied to UUID names; the DB keeps `original_filename`;
  missing files are imported with `missing_file=true` (reported, not lost).
  Since 1.3 attachments belong to the **patient** — the legacy
  `Appointment_id` is resolved through the appointments table; an
  unresolvable reference **halts** `--apply` (corruption signal).
- **Legacy rx free text** is converted into structured prescriptions with
  the same frozen parser as the 1.3 Alembic migration
  (`app/services/rx_migration.py`): comma/newline items, trailing integer
  → quantity, dictionary admission only for names seen ≥ 3 times,
  everything rarer verbatim in the prescription notes. The raw text also
  stays in the deprecated `appointments.rx` column. Re-runs skip
  prescriptions already derived (`source_appointment_id`).
- **Data-quality report** flags legacy rows violating the new validation
  (10-digit national ID, 4-digit year, digits-only phone). Non-blocking —
  fix them via the UI later. Duplicate national IDs **halt** `--apply`
  until resolved manually.
- Legacy English payment descriptions (`Visit`/`Spiro`/`Other`) are
  translated to ویزیت/اسپیرو/سایر (case-insensitive; unmatched kept as-is).
- Automatic verification compares per-table counts, POS/cash sums,
  per-patient appointment counts, orphan FKs, and the planned
  prescriptions/items/links counts. Exit code 0 only on PASS.
- Post-cutover: keep the old system read-only for two weeks as fallback.

After `--apply`, run the independent cross-check (does NOT share code with
the migration script — compares SQLite vs PostgreSQL directly, including
field-by-field patient comparison, money sums, tz conversion, note-text
survival, and physical file sizes):

```bash
.venv/bin/python scripts/verify_import.py   # ALL CHECKS PASSED = safe cutover
```

> **Warning:** `verify_import.py` has its target DSN **hardcoded**
> (`postgresql+psycopg2://clinic:testpass@localhost:5432/clinic` — a test
> container on port 5432). Edit the DSN at the top of the script before
> using it against the real stack (compose maps Postgres to **5434**), and
> never run it against a database you cannot afford to query.

A synthetic legacy DB for testing the migration itself:
`python3 scripts/make_test_legacy_db.py /tmp/legacy.db`

`old_database/` in the repo is a real production snapshot — treat as
sensitive; never commit anything into it.

## Attachment files: where they must land

`--upload-dir` must be the directory the running compose **api actually
mounts** — on the compose stack that is the named volume `praxis_uploads`
(`/data/uploads` inside the container). Files copied to a host path the
container cannot see are invisible to the app AND to the backup job: the
tarball ships with `uploads_files: 0` and a suspiciously small size (the
Sep-14 import wrote to `data/uploads` on the host — backups were 2 MB
instead of 360 MB until the files were copied into the volume).

Two repair paths:

```bash
# after the host-side import, copy the files into the volume:
docker cp data/uploads/. praxis-api-1:/data/uploads/

# or re-run the idempotent file relocation (fills rows marked
# missing_file=TRUE whose files exist; already-relocated rows are skipped):
.venv/bin/python scripts/migrate_sqlite.py --source old_database/db.sqlite3 \
  --files old_database/patient_files --database-url "$DATABASE_URL" \
  --upload-dir data/uploads --apply
```

Notes:

- Each attachment row owns its own stored copy — identical legacy content
  is stored multiple times (the live-row unique index
  `uq_attachments_stored_filename_live` forbids sharing a
  `stored_filename`).
- Rows whose legacy file is genuinely absent on disk stay
  `missing_file=TRUE` (the UI flags them) — 7 files were lost in the
  legacy snapshot itself.
- The post-apply verify compares money totals against the LEGACY snapshot:
  on a live system where users kept working after the import, a FAIL there
  is a false alarm (post-import rows), not corruption.

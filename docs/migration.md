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
- **Data-quality report** flags legacy rows violating the new validation
  (10-digit national ID, 4-digit year, digits-only phone). Non-blocking —
  fix them via the UI later. Duplicate national IDs **halt** `--apply`
  until resolved manually.
- Legacy English payment descriptions (`Visit`/`Spiro`/`Other`) are
  translated to ویزیت/اسپیرو/سایر (case-insensitive; unmatched kept as-is).
- Automatic verification compares per-table counts, POS/cash sums,
  per-patient appointment counts, orphan FKs. Exit code 0 only on PASS.
- Post-cutover: keep the old system read-only for two weeks as fallback.

After `--apply`, run the independent cross-check (does NOT share code with
the migration script — compares SQLite vs PostgreSQL directly, including
field-by-field patient comparison, money sums, tz conversion, note-text
survival, and physical file sizes):

```bash
.venv/bin/python scripts/verify_import.py   # ALL CHECKS PASSED = safe cutover
```

A synthetic legacy DB for testing the migration itself:
`python3 scripts/make_test_legacy_db.py /tmp/legacy.db`

`old_database/` in the repo is a real production snapshot — treat as
sensitive; never commit anything into it.

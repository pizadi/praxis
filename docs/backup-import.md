# Backup export / import & uploads purge

## Export (tarball)

- `POST /admin/backup` starts a background job (daemon thread; 409
  `backup_running` if one is already running); `GET /admin/backup` polls;
  `GET /admin/backup/download` streams the tar.gz; `DELETE` discards.
  Perm: `backup.manage`; audited.
- The api container has no `pg_dump` — the DB is dumped via psycopg2
  `COPY ... TO STDOUT` per table (FK order, REPEATABLE READ snapshot).
  The DSN is converted from `postgresql+asyncpg://` to plain
  `postgresql://` (raw psycopg2 can't parse dialect schemes).
- Tables are staged in `SpooledTemporaryFile`s and uploads are streamed —
  the archive is never fully in memory.
- SQLite (dev) databases are archived as the raw file.

## Tarball format

```
manifest.json            {"schema_version": 3, "app_version": "1.3.0",
                          "created_at": ..., "app_timezone": ...,
                          "tables": {table: rowcount},
                          "table_columns": {table: [columns...]}}
db/<table>.copy          PostgreSQL COPY data (one per table)      ← PG
db/clinic.sqlite3        raw SQLite database                      ← SQLite dev
uploads/<name>           the uploaded patient files
```

## Import (restore)

- `POST /admin/backup/import` — multipart tarball (perm `backup.manage`,
  audited). `GET /admin/backup/import` polls; the job runs in a background
  thread sharing one lock with backup (409 `backup_running` if busy).
- The tarball is pre-validated before anything happens: member allowlist
  (`manifest.json`, `db/…`, `uploads/…`), zip-slip guards, size caps —
  invalid → 422 `invalid_backup`.

### Version rules

- `schema_version` **newer than supported** (currently 3) → 422
  `unsupported_schema`.
- producer `app_version` **older** → imports cleanly: only tables present
  in the dump are replaced; columns are mapped through the manifest's
  `table_columns` (columns added after the dump are filled from their DDL
  default, else a type-aware fallback `''`/`0`; dump columns unknown to the
  live schema are dropped). Every skew is reported in the import summary.
  **Pre-1.3 backups (schema_version ≤ 2)**: attachments arrive keyed by
  `appointment_id` — the importer remaps them to `patient_id` through the
  dumped appointments table (FK integrity of one dump makes the mapping
  total; a dangling reference rolls back loudly). Because `TRUNCATE …
  CASCADE` on patients also wipes prescriptions (they did not exist in the
  old format), they are **re-derived from the restored `rx` text** inside
  the same transaction (same frozen parser as the 1.3 migration;
  `_rederived_from_rx` in the summary reports the counts).
- `app_version` **newer** → 409 `newer_version` with the manifest summary —
  the UI asks whether to import anyway (`force=true`).
- **Rollback**: the DB import is one transaction — any unresolvable error
  (FK violation, NOT NULL without a fallback, …) rolls everything back and
  the running system is untouched.

### Mechanics

- PostgreSQL: one REPEATABLE READ transaction — `TRUNCATE` the dump's
  tables (CASCADE), `COPY` each with the manifest column list, re-sync
  serial sequences from `max(id)`, commit.
- SQLite (dev/tests): `ATTACH` the archived database read-only and
  `INSERT … SELECT` table-by-table in one transaction (no file swapping —
  safe against the live connection pool).
- uploads/: extracted into `UPLOAD_DIR/.import-<ts>/` staging, then moved
  into place after the DB commit (merge — pre-existing files not in the
  tarball stay until the automatic purge reclaims them).

## Uploads purge (automatic)

- Files in `UPLOAD_DIR` referenced by **no** attachment row (live or
  soft-deleted) and matching the storage-name pattern (UUID hex +
  extension) are unlinked automatically: once at API startup, then every
  6 hours (lifespan task).
- A **24h grace period** (file mtime) protects in-flight uploads (the file
  is written before the row commits) and the post-import merge window.
- Hidden directories (`.import-*` staging) are skipped; foreign files that
  don't match the storage-name pattern are never touched.
- Each removing pass is audited as the `system` user (entity
  `uploads_purge`).

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

## Artifact persistence (survives restarts)

- The artifact lives under `BACKUP_DIR` — default `<UPLOAD_DIR>/.backups`,
  a **hidden dir on the uploads volume**, so it survives `docker compose
  down && up` with no compose changes. The purge never descends into
  hidden dirs, and the archiver skips dot-dirs (the tarball can never
  include itself).
- Exactly **one artifact** exists: the job writes `<random>.part` in the
  same dir and atomically `os.replace`s it onto the fixed final name
  (`clinic-backup.tar.gz` / `.tar.gz.enc`); a stale artifact of the other
  kind (encryption toggled between runs) is removed.
- At startup (after migrations/bootstrap) a background thread
  **re-discovers** the artifact: dead `.part` files are swept, the
  checksum is recomputed (streamed), and the status flips to `ready`
  with `finished_at` from the file mtime. A restart therefore never
  silently loses the last backup.
- `DELETE` discards the persisted artifact from disk.

## Download (native browser flow)

- A browser navigation cannot send the `Authorization` header, so
  `POST /admin/backup/download-token` issues a **short-lived HMAC token**
  (5 min, signed with `SECRET_KEY`); the UI then navigates to
  `GET /admin/backup/download?token=…` and the browser's **download
  manager** streams the artifact to disk (visible progress even on slow
  links). The header path (Bearer + `backup.manage`) keeps working —
  `?token=` is only additive; invalid/expired tokens are 401.

## Tarball format

```
manifest.json            {"schema_version": 4, "app_version": "1.3.0",
                          "created_at": ..., "app_timezone": ...,
                          "tables": {table: rowcount},
                          "table_columns": {table: [columns...]},
                          "member_sha256": {member: hex, ...}}
db/<table>.copy          PostgreSQL COPY data (one per table)      ← PG
db/clinic.sqlite3        raw SQLite database                      ← SQLite dev
uploads/<name>           the uploaded patient files
```

- Since schema_version 4 the manifest carries a **SHA-256 per member**
  (everything except manifest.json itself — a file cannot contain its own
  hash). The importer verifies every member **before** the destructive DB
  transaction; a mismatch fails the import loudly.
- A plaintext (`.tar.gz`) artifact is a gzip stream; an **encrypted**
  artifact starts with the `PRAXISBK` magic and downloads as `.tar.gz.enc`
  (see below).

## Artifact checksum

- `GET /admin/backup` returns `sha256` — the hash of the FINAL artifact
  (the encrypted bytes when encryption is on, else the tarball); the same
  value rides on the download as the `X-Checksum-Sha256` header. Verify
  what landed on disk with `sha256sum`.
- The import accepts an optional `expected_sha256` form field — a mismatch
  refuses the restore with 422 `checksum_mismatch` before anything runs.
  The UI computes the hash client-side (`crypto.subtle`) and always sends
  it.

## Encryption (optional)

- Set `BACKUP_ENCRYPTION_KEY` (a long random passphrase) to encrypt
  tarballs: **AES-256-GCM** with a per-archive random salt/nonce and a
  scrypt-derived key. Wire format:
  `PRAXISBK | 0x01 | salt(16) | nonce(12) | ciphertext | tag(16)`; the
  magic doubles as GCM additional authenticated data. Streaming both ways
  (1 MiB chunks) — the archive is never fully in memory.
- The plaintext tarball is deleted after encryption — only the encrypted
  artifact stays on disk.
- **Losing the key means losing the backups** — it both encrypts new ones
  and unlocks importing encrypted ones. Store it in a password manager.
- Importing an encrypted artifact without a configured key (or with the
  wrong one) refuses with 422 `invalid_backup` and a clear message.

## Stale-backup warning

- Every successful backup records a durable completion row in the audit
  trail (`action='backup'`, username `system`, with size/sha/encrypted
  details) — it survives restarts, unlike the in-memory job status.
- `GET /admin/backup` returns `last_backup_at`, `backup_stale` and
  `backup_stale_days` (from `BACKUP_STALE_DAYS`, default **7**; `0`
  disables the warning → `backup_stale` is null).
- Admins (`backup.manage`) see a dismissible warning banner on every page
  while no successful backup is newer than the threshold — including
  "never backed up" on a fresh install.

## Import (restore)

- `POST /admin/backup/import` — multipart tarball (perm `backup.manage`,
  audited). `GET /admin/backup/import` polls; the job runs in a background
  thread sharing one lock with backup (409 `backup_running` if busy).
- **No size cap**: the tarball is exempt from `MAX_UPLOAD_BYTES` (that limit
  guards patient attachments only) — nginx accepts an unlimited body for
  this exact route (`client_max_body_size 0`) with request buffering off,
  so the upload streams straight through to the api, which spools it to
  `BACKUP_DIR` on the persistent volume in 1 MiB chunks. The UI shows
  hashing + upload progress and hashes the file incrementally (never
  whole-file in memory).
- The tarball is pre-validated before anything happens: member allowlist
  (`manifest.json`, `db/…`, `uploads/…`), zip-slip guards, size caps —
  invalid → 422 `invalid_backup`.

### Version rules

- `schema_version` **newer than supported** (currently 4) → 422
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

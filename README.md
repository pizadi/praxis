# Praxis — پراکسیس | Clinic Management System

FastAPI + React + PostgreSQL rewrite of a legacy Django/SQLite patient &
appointment system. Persian (RTL) UI with Jalali calendar. Multi-user with
role-based access control.

## Stack

| Layer     | Tech                                                              |
| --------- | ----------------------------------------------------------------- |
| API       | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, JWT + argon2 |
| DB        | PostgreSQL 16 (SQLite for tests/dev)                              |
| Frontend  | Vite + React + TS, antd (RTL), TanStack Query, jalaliday          |
| Deploys   | docker-compose (3 services: web/api/db), nginx reverse proxy       |
| Migration | `scripts/migrate_sqlite.py` (legacy SQLite → Postgres, verifiable) |

## Quick start (dev)

```bash
# 1. Backend
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
DATABASE_URL=sqlite+aiosqlite:///data/clinic-dev.db ../.venv/bin/python -m alembic -c alembic.ini upgrade head
DATABASE_URL=sqlite+aiosqlite:///data/clinic-dev.db ../.venv/bin/uvicorn app.main:app --reload

# 2. Frontend (separate terminal; proxies /api → :8000)
cd frontend
npm install
npm run dev     # http://localhost:5173

# 3. Login with the bootstrap admin (create users via UI)
#    admin / (BOOTSTRAP_ADMIN_PASSWORD, default admin123 — change it!)
```

## Quick start (docker / Raspberry Pi)

```bash
cp .env.example .env      # edit secrets!
docker compose up -d --build
# site: http://<pi-ip>/   API docs: http://<pi-ip>/api/v1/docs is NOT exposed;
# use http://127.0.0.1:8000/docs on the host (or add a location in nginx.conf)
```

On the Pi: mount `pgdata` and `uploads` volumes on an SSD, not the SD card.

## Roles & permissions

Access control is **permission-based**. Each role row (in `roles`) holds a
permission set (JSON array of keys from the catalog in
`backend/app/core/permissions.py`); every endpoint checks
`require_perm(...)` instead of a fixed hierarchy.

- Three **system roles** are seeded at startup — `admin` (all permissions),
  `doctor`, `receptionist` — reproducing the legacy hierarchy exactly.
- The **admin role is locked** (cannot be edited or deleted) so the instance
  can never lock itself out of role management; doctor/receptionist are
  editable but undeletable.
- Admins create custom roles at `/roles` (grouped permission checkboxes),
  and assign them to users at `/users`. A role in use refuses deletion.
- Permission changes apply immediately (permissions are read from the DB per
  request, not baked into tokens).
- Medical fields (CM/HX/PX/RX) are blanked server-side unless the user holds
  `medical_notes.view` — not just hidden in the UI.

| Ability                        | receptionist | doctor | admin |
| ------------------------------ | :----------: | :----: | :---: |
| Patients CRUD, search          |      ✅      |   ✅   |   ✅   |
| Appointments create/list       |      ✅      |   ✅   |   ✅   |
| Medical notes (CM/HX/PX/RX)    |      ❌      |   ✅   |   ✅   |
| Edit appointments / files      |      ❌      |   ✅   |   ✅   |
| Transactions                   |      ✅      |   ✅   |   ✅   |
| Questionnaires: fill / read    |      ✅      |   ✅   |   ✅   |
| Stats                          |      ❌      |   ✅   |   ✅   |
| Tags / diagnoses               |     read     |   ✅   |   ✅   |
| Delete patients, manage users  |      ❌      |   ❌   |   ✅   |
| Custom roles / permissions     |      ❌      |   ❌   |   ✅   |
| Trash: view / restore          |      ❌      |   ✅   |   ✅   |
| Trash: permanent purge         |      ❌      |   ❌   |   ✅   |
| Audit trail                     |      ❌      |   ❌   |   ✅   |

## Questionnaires

Admin-defined questionnaire **templates** (`/questionnaires`) whose format
is a validated JSON document: number questions (range/integer), multiple-
choice questions with optional **graded** options (scores), and string
questions (single/multi-line). Templates can be built graphically or
uploaded as a JSON file — every write path (builder, upload, API) validates
identically server-side, and a downloadable example JSON is provided.

Filled **responses** belong to a **patient** (not an appointment): from the
patient page's پرسش‌نامه‌ها segment — list/add/edit/delete, multiple
responses per template allowed. Answers are stored as raw nullable JSON and
validated against the template at write time (unknown keys and
type/range/choice violations are rejected; empty is always allowed —
`required` is a form-level constraint only). The fill form validates
explicitly with per-field Persian messages (range/integer/choice/length) —
both client-side and, authoritatively, server-side with inline per-field
errors from the 422 envelope.

There is deliberately **no snapshot**: rendering merges stored answers with
the *current* template — questions removed from the template are ignored,
new questions render as null, and values that no longer validate render as
missing with a warning banner and a confirm-dialog button that clears the
invalid fields (server-revalidated PATCH).

**Scoring**: a template may define a `score_formula` — a small arithmetic
expression over question keys (a number question contributes its answer, a
choice question the chosen option's score), with `+ - * /`, parentheses and
`min`/`max`/`abs` functions, e.g. `0.5 * pain + max(mobility, 2)`. The
formula is parsed and validated (syntax + referenced keys must be numeric
questions) on every template write path — same parser mirrored client-side
in the builder for live feedback — and evaluated per response. Evaluation
never invents a score: if any referenced answer is missing/invalid, a chosen
option has no score, or the formula divides by zero, the total renders as
"—". Without a formula, the total falls back to the sum of the chosen
options' scores.

**Responses report**: `/questionnaire-responses` (گزارش پاسخ‌ها,
`questionnaires.read`) lists every response of a selected template in a
horizontally-scrollable table — patient national ID, Jalali date, one column
per question, and the total score when the template defines scoring — with
a client-generated CSV export (UTF-8 BOM, all pages).

## Patient page (appointments / files / questionnaires)

The patient detail page is a three-segment workspace:

- **نوبت‌ها** — appointment list + full detail panel (medical notes
  CM/HX/PX/RX, files with upload, payments).
- **همه فایل‌ها** — every attachment of the patient in one list; selecting a
  row opens the detail pane: title, شرح, upload date, size, editable notes,
  an authorized download button, and an **in-page preview** for images
  (with a zoom toolbar) and PDFs (browser viewer). A file can be **attached
  to a note-only document or replaced** later from the same pane (the
  superseded file stays on disk until a trash purge). Preview/download
  fetch bytes as authorized blobs — attachments never render from bare URLs.
- **پرسش‌نامه‌ها** — the per-patient questionnaire workspace (above).

**Unsaved changes are guarded**: editing the medical notes or a
questionnaire form and then switching the segment (or jumping to another
appointment) opens a three-way confirmation — ذخیره و ادامه (save, then the
switch completes), دورریختن تغییرات (reset, then switch), بازگشت (stay).
Dialogs across the app close only via their buttons — clicking the backdrop
never dismisses a modal.

## Versions

The API version lives in `backend/app/__init__.py::__version__` and is
reported by `GET /api/v1/health`; the UI version is `frontend/package.json`'s
`version`, shown next to the header title. Both are bumped together
(minor = feature, patch = fix).

## Soft deletes & trash

All deletions are **soft** (`deleted_at` timestamp). A deleted patient hides
its whole subtree (appointments/files/payments/questionnaires) through join
filtering; the trash panel (`/trash`, doctor+admin) lists directly-deleted
rows with Jalali timestamps, restores them (subtree rules enforced — a child
refuses restore while its parent is deleted, with a clear 409), and offers
admin-only permanent purge, the only action that unlinks physical files.
Unique values (national ID, tag/diagnosis/user/role/template names) are
enforced only among live rows via partial unique indexes, so a deleted value
can be reused; restoring then conflicts only if a live duplicate exists.

## Patient search

The omnibox (`q`) matches first/last name, national ID, **and phone number**
(SQL-side `ILIKE` on all four). Advanced filters: exact national ID
substring, phone substring, and multi-select tags/diagnoses (patients must
have ALL selected).

## Audit trail

Every mutating action (create / update / delete / restore / purge) is recorded
in `audit_log` with: acting user, timestamp (timestamptz), action, entity
type + id, a human summary (e.g. "name surname (national-id)", old → new for
renames, "1,500,000 — visit" for payments), a JSON `details` payload with
field-level diffs for updates, and the client IP. Login attempts live in the
separate `login_audit` table. Admins view the trail at `/audit` with
action/entity filters; the API is `GET /admin/audit` (paginated).

## Jalali inputs

All date inputs (schedule day, stats range, new-appointment datetime) use
react-multi-date-picker with the Persian calendar; internal state and the
API contract remain Gregorian ISO. The new-appointment dialog defaults to
**now**.

## Migration from the legacy system (SQLite → PostgreSQL)

**Never point the script at the live DB.** Snapshot first:

```bash
# on the Pi, during quiet hours:
systemctl stop old-patients   # or however it runs
cp /path/to/db.sqlite3  snapshot/db.sqlite3
cp -r /path/to/patient_files  snapshot/patient_files
systemctl start old-patients  # old system keeps running meanwhile
```

Then, from this repo (target the Postgres mapped to host port 5434):

```bash
# dry run (no writes) — shows counts, data-quality report, verification:
.venv/bin/python scripts/migrate_sqlite.py \
  --source snapshot/db.sqlite3 \
  --files  snapshot/patient_files \
  --database-url postgresql+asyncpg://clinic:PASS@localhost:5434/clinic \
  --upload-dir /var/lib/clinic/uploads

# real run (idempotent; safe to re-run):
... --apply
```

Behavior:

- **1:1 mapping** — PKs and all values preserved; join tables rebuilt.
- Legacy `Appointment_Date` naive local datetimes are stored as
  `timestamptz` assuming Asia/Tehran (+03:30).
- Files are copied to UUID names; DB keeps `original_filename`;
  missing files are imported with `missing_file=true` (reported, not lost).
- **Data-quality report** flags legacy rows violating the new validation
  (10-digit national ID, 4-digit year, digits-only phone). Non-blocking —
  you fix them via the UI later. Duplicate national IDs **halt** `--apply`
  until resolved manually.
- Automatic verification compares per-table counts, POS/cash sums,
  per-patient appointment counts, orphan FKs. Exit code 0 only on PASS.
- Post-cutover: keep old system read-only for two weeks as fallback.

After `--apply`, run the independent cross-check (does NOT share code with
the migration script — compares SQLite vs PostgreSQL directly, including
field-by-field patient comparison, money sums, tz conversion, note-text
survival, and physical file sizes):

```bash
.venv/bin/python scripts/verify_import.py   # ALL CHECKS PASSED = safe cutover
```

**Verified against the real production snapshot** (`old_database/`):
9,903 patients · 17,190 appointments · 24,575 transactions (POS 10,047,985,000
+ cash 445,285,000 = 10,493,270,000 — exact match) · 18,492 attachments
(4,934 files copied byte-identical, 13,551 note-only rows, 7 referenced
files absent from disk, 14 orphan files on disk) · 4,434 M2M links.
Known dirty rows flagged (fix at your pace): 4 phone numbers containing
non-digits (`+98…` prefix, `÷` typo, a slash-separated pair, one with a
trailing word). Re-running `--apply` is safe (idempotent, re-verified).

A synthetic legacy DB for testing the migration itself:
`python3 scripts/make_test_legacy_db.py /tmp/legacy.db`

## Tests / lint / typecheck

```bash
cd backend
../.venv/bin/python -m pytest tests -q      # 52 tests
../.venv/bin/ruff check app tests ../scripts
../.venv/bin/mypy app

cd frontend
npm run lint      # after npm install
npm run build     # tsc -b && vite build
```

## Backups (on the Pi)

```bash
# crontab: nightly pg_dump with 14-day retention + uploaded files
0 2 * * *  docker exec clinic-db-1 pg_dump -U clinic clinic | gzip > /ssd/backups/db-$(date +\%F).sql.gz && find /ssd/backups -name 'db-*.sql.gz' -mtime +14 -delete
30 2 * * * rsync -a /ssd/clinic-data/uploads/ /ssd/backups/uploads/
```

Do a **restore drill** monthly: `gunzip -c db-DATE.sql.gz | docker exec -i clinic-db-1 psql -U clinic clinic`.

## Project layout

```
backend/app
  api/v1/        routers (auth, users, roles, patients, appointments,
                 attachments, transactions, taxonomies, questionnaires,
                 stats, trash, audit, backup, meta)
  api/deps.py    auth deps, permission guards, file-storage safety
  core/          config, security (JWT/argon2), errors, tokens,
                 permissions (catalog + system role sets)
  db/session.py  engine + APP_TZ
  models/        domain.py (1:1 legacy schema + questionnaires),
                 system.py (users/roles/auth/audit)
  schemas/       Pydantic v2 request/response models
   services/      audit trail, questionnaire format/answer validation,
                  score-formula parser/evaluator
backend/alembic  migrations (baseline: b7eee1c1aa98)
backend/tests    pytest suite (isolated SQLite, per-test drop/create)
frontend/src     pages, api client with refresh-token rotation, Jalali utils
scripts/         migrate_sqlite.py, make_test_legacy_db.py
deploy/nginx     production nginx config
```

## Security notes

- Access tokens 30 min; refresh tokens rotate on use (single-use, DB-tracked).
- File downloads resolve paths strictly inside `UPLOAD_DIR`
  (`Path.resolve()` + containment check — fixes the legacy traversal bug).
- Uploads get UUID storage names; extension sanitized; size capped.
- Deleting patients/appointments also unlinks physical files (legacy leaked).
- Uniform JSON error envelope with machine-readable codes; Persian messages
  rendered client-side.
- Production startup refuses default `SECRET_KEY`/admin password
  (`CLINIC_ENV=production`).

## Phase-2 backlog (after verified import, each via Alembic migration)

- `payment_method` enum replacing the `POS` boolean
- appointment `status` (scheduled/completed/no_show/cancelled) + conflict checks
- soft deletes + full audit log for medical records
- money type + currency labeling (Toman/Rial)
- SMS reminders (job queue), printable prescriptions/invoices (PDF)
- pg_trgm fuzzy search, image thumbnails

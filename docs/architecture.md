# Architecture

Praxis (پراکسیس) is a FastAPI + React + PostgreSQL clinic management system,
rewritten from a legacy Django/SQLite application.

## Stack

| Layer | Tech |
| --- | --- |
| API | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, JWT + argon2 |
| DB | PostgreSQL 16 (SQLite for tests/dev) |
| Frontend | Vite + React + TS, antd (RTL), TanStack Query, jalaliday |
| Deploy | docker-compose (web/api/db), nginx reverse proxy |

## Layout

```
backend/app
  api/v1/        routers: auth, users, roles, patients, appointments,
                 attachments, transactions, taxonomies, questionnaires,
                 stats, trash, audit, backup, meta
  api/deps.py    auth deps, permission guards, file-storage safety
  core/          config, security (JWT/argon2), errors, tokens,
                 permissions (catalog + system role sets)
  db/session.py  engine, SessionLocal, APP_TZ (Asia/Tehran)
  models/        domain.py (patients/appointments/... + questionnaires),
                 system.py (users/roles/auth/audit)
  schemas/       Pydantic v2 request/response models
  services/      audit trail, questionnaire format validation, score
                 formulas, backup import, uploads purge
  alembic/       migrations (additive-only; auto-applied at container boot)
frontend/src
  pages/         one page per route (Persian/RTL UI)
  components/    shared panels (AppointmentPanel, FileDetailPane, ...)
  api/           axios client (token refresh), types mirroring backend
  lib/           pure helpers: jalali dates, questionnaire logic, downloads
scripts/         legacy SQLite→Postgres migration + verification tooling
deploy/          production nginx config
docs/, docs_fa/  feature documentation (English / Persian)
```

## Key invariants

- **Permissions, not roles**: every endpoint checks `require_perm(...)` from
  `app/api/deps.py`. Roles are data (JSON permission sets on the `roles`
  table); the admin role is locked to prevent lockout.
- **Soft deletes everywhere**: deletions stamp `deleted_at`; uniqueness is
  enforced with partial unique indexes on live rows. See
  [trash-soft-delete.md](trash-soft-delete.md).
- **Audit trail**: every mutating endpoint calls `services/audit.py::
  log_action` before returning. See [audit.md](audit.md).
- **No snapshot for questionnaires**: responses are rendered merged with the
  *current* template. See [questionnaires.md](questionnaires.md).
- **Time**: internal state and the API contract are Gregorian ISO/UTC; only
  display/input is Jalali. Day-boundary logic uses `APP_TZ` (Asia/Tehran).
- **Errors**: uniform envelope `{"error": {"code", "message", "details"}}`
  via `app/core/errors.py` — 409 `ConflictError`, 422 `BusinessRuleError`,
  404 `NotFoundError`.

## Versioning

- `backend/app/__init__.py::__version__` — single source for the API,
  exposed by `GET /api/v1/health` and baked into backup manifests.
- `frontend/package.json` `version` — single source for the UI, injected as
  `__APP_VERSION__` via vite `define`, shown next to the header title.
- Both are bumped together: minor = feature, patch = fix. Pre-release
  commits during development use `X.Y.Z.devN`.

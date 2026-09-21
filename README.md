# Praxis — پراکسیس | Clinic Management System

FastAPI + React + PostgreSQL clinic management system (rewritten from a
legacy Django/SQLite app). Persian (RTL) UI with Jalali calendar,
permission-based access control.

* [مستندات فارسی](README_fa.md)

## Stack

| Layer | Tech |
| --- | --- |
| API | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, JWT + argon2 |
| DB | PostgreSQL 16 (SQLite for tests/dev) |
| Frontend | Vite + React + TS, antd (RTL), TanStack Query, jalaliday |
| Deploy | docker-compose (web/api/db), nginx reverse proxy |

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

# 3. Login with the bootstrap admin (see .env / .env.example)
```

## Quick start (docker)

```bash
cp .env.example .env      # edit secrets!
docker compose up -d --build
```

See [docs/deployment.md](docs/deployment.md) for operations details.

## Features

| Area | Docs |
| --- | --- |
| Patients, appointments (visit stages, same-day visit tabs), medical notes | [docs/patients-appointments.md](docs/patients-appointments.md) |
| File attachments: preview, zoom, attach/replace | [docs/files.md](docs/files.md) |
| Payments (POS/cash) + day-wide views | [docs/payments.md](docs/payments.md) |
| Stats & reports | [docs/reports.md](docs/reports.md) |
| Questionnaires: builder, scoring formulas, responses report + CSV | [docs/questionnaires.md](docs/questionnaires.md) |
| Permission-based access control (custom roles) | [docs/permissions.md](docs/permissions.md) |
| Soft deletes + trash (restore/purge) | [docs/trash-soft-delete.md](docs/trash-soft-delete.md) |
| Audit trail | [docs/audit.md](docs/audit.md) |
| Backup tarballs: export, checksums, optional AES-256-GCM encryption, versioned import with rollback, stale-backup warning | [docs/backup-import.md](docs/backup-import.md) |
| Architecture & versioning | [docs/architecture.md](docs/architecture.md) |
| Development (tests/lint/typecheck/e2e) | [docs/development.md](docs/development.md) |
| Legacy migration (SQLite → PostgreSQL) | [docs/migration.md](docs/migration.md) |

## Tests

```bash
# backend (ruff → mypy → pytest; also verified on real PostgreSQL)
cd backend && DATABASE_URL="sqlite+aiosqlite:///data/clinic-dev.db" ../.venv/bin/python -m pytest tests -q
../.venv/bin/ruff check backend/app backend/tests scripts
(cd backend && ../.venv/bin/mypy app)

# frontend: eslint, vitest (units + questionnaire parity), tsc build
cd frontend
npm run lint
npm test              # vitest — includes the TS side of testdata/questionnaire_parity.json
npm run build

# end-to-end (spins a scratch backend on :18001 + vite preview on :18010)
npm run test:e2e
```

The questionnaire validators (Python + TypeScript) are kept in sync by a
shared conformance corpus — `testdata/questionnaire_parity.json` — executed
by both test suites.

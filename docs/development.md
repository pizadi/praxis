# Development

## Commands

Python venv is at the **repo root** (`.venv`), not in `backend/`.

```bash
# backend tests (from backend/ — pyproject.toml lives there)
cd backend && DATABASE_URL="sqlite+aiosqlite:///data/clinic-dev.db" ../.venv/bin/python -m pytest tests -q
# single test
../.venv/bin/python -m pytest tests/api/test_patients.py::test_patient_crud -q

# lint + typecheck
.venv/bin/ruff check backend/app backend/tests scripts
(cd backend && ../.venv/bin/mypy app)

# frontend (from frontend/)
npm run lint        # eslint, zero warnings allowed
npm run build       # tsc -b && vite build
npm test            # vitest: unit + parity (jsdom)
npm run test:e2e    # playwright: spins a scratch backend (18001) + preview (18010)

# questionnaire validators (server validation + shared evaluation corpus)
../.venv/bin/python -m pytest backend/tests/parity -q   # python side
npx vitest run src/parity                               # TS evaluation side

# documentation pair guard
python scripts/check_doc_pairs.py --base-ref origin/dev

# deploy to the running compose stack
docker compose up -d --build api web
```

Verify order: ruff → mypy → pytest → npm lint/test/build → e2e.

## Test suite layout

```
backend/tests/
  conftest.py   # env setup (BEFORE app imports) + client fixture + auth fixtures
                # (admin_token / doctor / recep) + backup/import poll helpers
  factories.py  # API builders: mk_patient/mk_appointment/mk_file/mk_template/
                # mk_response/mk_prescription/mk_transaction/... — the single
                # source for creating domain objects (asserts on CREATE responses)
  unit/         # pure functions, no HTTP: scoring parser/eval, rx_migration
                # (frozen golden rules), questionnaire format matrix, backup
                # crypto, day_bounds (APP_TZ), audit ip/diffs, architecture
                # and documentation guards
  api/          # per-resource integration tests over the httpx ASGI client:
                # auth/users, roles, permissions_matrix (endpoint × role sweep),
                # patients, appointments+stages, payments, attachments,
                # questionnaires, prescriptions, trash, audit, backup, meta/stats
  parity/       # questionnaire-validator parity — the python half
frontend/
  src/**/*.test.ts(x)  # vitest: lib units + components + evaluation parity
  e2e/                 # playwright specs against a SCRATCH stack:
                       #   uvicorn on 18001 (fresh tmp SQLite + bootstrap
                       #   admin/admin123) + vite preview on 18010 proxying /api
testdata/questionnaire_parity.json  # shared evaluation/answer corpus
testdata/rx_migration_v1.json       # golden freeze corpus
```

## Testing quirks

- `backend/tests/conftest.py` sets `DATABASE_URL`/`UPLOAD_DIR`/`SECRET_KEY`
  at module import time, **before any `app.*` import** — pydantic-settings
  caches at first import.
- Tests build tables via `Base.metadata.create_all`, **not** Alembic;
  migration correctness is verified against a real PostgreSQL separately
  (see docs/deployment.md for the test-container pattern).
- The `client` fixture drops/creates all tables per test and calls
  `bootstrap_admin()` manually.
- `pytest-asyncio` runs in `asyncio_mode = "auto"`.
- `login()` returns `(access_token, refresh_cookie_value)` — `recep, _ =
  await login(...)`, **not** `recep[0]`. Browser refresh cookies are
  `HttpOnly`; API tests read the raw cookie from the httpx jar.
- Assert persisted fields on the **create response** (not just after a
  PATCH) — a multipart-upload bug once survived the whole suite that way.
- Tests must derive «today» from `APP_TZ` (see payments.md).
- SQLAlchemy `Enum` columns persist the member **NAME** — any migration or
  script reading legacy enum columns must match case-insensitively and fail
  loudly on unexpected values instead of silently defaulting.
- The parity corpus (`testdata/questionnaire_parity.json`) is law: the server
  validator changes only together with it and the runners. The TS side runs
  evaluation/answer cases; formula syntax validation is server-authoritative.
  Boundary facts live there (length 1000, depth 100).
- Playwright E2E runs against its own scratch backend — never the live
  containers (real patient data). `vite preview` binds localhost (IPv6) —
  use `http://localhost:18010`, not 127.0.0.1; the chromium executable is
  the system one (`/usr/bin/chromium --no-sandbox`) since browsers cannot
  be downloaded here.
- E2E auth tests must NOT lock out `admin` (the 5-failure lockout is
  per-username and persists in the scratch DB for the whole run) — use a
  dedicated throwaway user.

## Conventions (short list)

- Persian/RTL UI; Jalali display only — API/state stay Gregorian ISO/UTC.
- Modals carry `maskClosable={false}`; prefer `destroyOnHidden`.
- antd Selects need `showSearch` + `optionFilterProp="label"`.
- Errors: uniform envelope with machine-readable codes; Persian messages
  rendered client-side.
- ruff line-length 100; `B008` ignored; mypy must stay clean.
- Versioning: bump `backend/app/__init__.py::__version__` and
  `frontend/package.json` together.

# Development

## Commands

Python venv is at the **repo root** (`.venv`), not in `backend/`.

```bash
# backend tests (from backend/ — pyproject.toml lives there)
cd backend && DATABASE_URL="sqlite+aiosqlite:///data/clinic-dev.db" ../.venv/bin/python -m pytest tests -q
# single test
../.venv/bin/python -m pytest tests/test_patients.py::test_patient_crud -q

# lint + typecheck
.venv/bin/ruff check backend/app backend/tests scripts
(cd backend && ../.venv/bin/mypy app)

# frontend (from frontend/)
npm run lint        # eslint, zero warnings allowed
npm run build       # tsc -b && vite build

# deploy to the running compose stack
docker compose up -d --build api web
```

Verify order: ruff → mypy → pytest → (if frontend touched) tsc/eslint/build.

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
- `login()` returns `(access_token, refresh_token)` — `recep, _ = await
  login(...)`, **not** `recep[0]`.
- Assert persisted fields on the **create response** (not just after a
  PATCH) — a multipart-upload bug once survived the whole suite that way.
- Tests must derive «today» from `APP_TZ` (see payments.md).
- SQLAlchemy `Enum` columns persist the member **NAME** — any migration or
  script reading legacy enum columns must match case-insensitively and fail
  loudly on unexpected values instead of silently defaulting.

## Conventions (short list)

- Persian/RTL UI; Jalali display only — API/state stay Gregorian ISO/UTC.
- Modals carry `maskClosable={false}`; prefer `destroyOnHidden`.
- antd Selects need `showSearch` + `optionFilterProp="label"`.
- Errors: uniform envelope with machine-readable codes; Persian messages
  rendered client-side.
- ruff line-length 100; `B008` ignored; mypy must stay clean.
- Versioning: bump `backend/app/__init__.py::__version__` and
  `frontend/package.json` together.

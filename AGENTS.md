# AGENTS.md

FastAPI + React + PostgreSQL clinic management system (rewritten from a legacy Django app; the legacy `models.py`/`views.py` at repo root and `old_database/` are reference material only — never modify or import them from app code). Persian (RTL) UI, Jalali calendar display, role-based access.

## Commands

Python venv is at the **repo root** (`.venv`), not in `backend/` — from `backend/` use `../.venv/bin/...`.

```bash
# backend tests (run from backend/ — pyproject.toml lives there)
cd backend && DATABASE_URL="sqlite+aiosqlite:///data/clinic-dev.db" ../.venv/bin/python -m pytest tests -q
# single test
../.venv/bin/python -m pytest tests/test_patients.py::test_patient_crud -q

# lint + typecheck (ruff/mypy config in backend/pyproject.toml; run ruff from repo root)
.venv/bin/ruff check backend/app backend/tests scripts
(cd backend && ../.venv/bin/mypy app)

# frontend (run from frontend/)
npm run lint        # eslint, zero warnings allowed
npm run build       # tsc -b && vite build

# deploy to the running compose stack (api container auto-runs `alembic upgrade head` on boot)
docker compose up -d --build api web
```

Verify order: ruff → mypy → pytest → (if frontend touched) tsc/eslint/build.

## Testing quirks

- `backend/tests/conftest.py` sets `DATABASE_URL`/`UPLOAD_DIR`/`SECRET_KEY` env vars **at module import time, before any `app.*` import** — pydantic-settings caches at first import, so env vars must be set before `app.main` is imported anywhere.
- Tests default to SQLite (via aiosqlite) but must also pass on PostgreSQL. For a real-PG run: `docker run -d --name pg-t --network host -e POSTGRES_USER=t -e POSTGRES_PASSWORD=t -e POSTGRES_DB=t postgres:16-alpine`, then `alembic -c alembic.ini upgrade head` and pytest with `DATABASE_URL=postgresql+asyncpg://t:t@localhost:5432/t`.
- Tests build tables via `Base.metadata.create_all`, **not** Alembic; migration correctness must be verified against a real Postgres separately.
- The `client` fixture drops/creates all tables per test and calls `bootstrap_admin()` manually (httpx ASGITransport does not run lifespan).
- `pytest-asyncio` is in `asyncio_mode = "auto"` — async test functions need no markers.
- `login()` in conftest returns `(access_token, refresh_token)` — `recep, _ = await login(...)` then `auth(recep)`, **not** `recep[0]` (that's the first character of the token → 401).
- When testing a create endpoint, assert persisted fields on the **create response** — the multipart upload bug survived the whole suite because only post-PATCH values were checked.
- Repo-root `.env` (gitignored, real values) sets `BOOTSTRAP_ADMIN_*` — pydantic reads `env_file=".env"` **relative to CWD**, so behavior differs between running from repo root vs `backend/`. In tests this is masked by conftest env vars; be careful with manual scripts.

## Environment / network gotchas

- PyPI/npm registries are unreliable here; mirrors are configured: PyPI via `https://package-mirror.liara.ir/repository/pypi/simple`, npm via `frontend/.npmrc` (Liara; if it 504s, retry with `--registry=https://mirror-npm.runflare.com`). `.npmrc`'s `allow-remote=all` is required — mirror metadata points at absolute Artifactory tarball URLs that npm 12 blocks otherwise.
- Docker Hub pulls: `docker-mirror.liara.ir` if direct pulls stall.
- **Docker bridge networking is broken in this dev sandbox** (veth `operation not supported`): use `--network host` for test containers, and `DOCKER_BUILDKIT=0 docker build --network=host` for image builds. The user's own compose stack runs fine elsewhere/on their kernel — don't "fix" the compose bridge network because a local test failed.
- The live compose stack (real patient data) runs on this machine: `new-patients-{db,api,web}-1`. The compose Postgres is mapped to host port **5434** (container name `db:5432`); a leftover test PG container on 5432 can masquerade as the real DB — check `docker ps` first. Credentials live in `.env` (never print/commit them). Feature changes are **not live until the images are rebuilt** (`docker compose up -d --build api web`) — a "missing" feature on the live UI is usually a stale container, not a code bug.
- **The live api container binds host port 8000** (and web port 80) — a local uvicorn on 8000 fails with "address already in use" that looks like a code bug. Run scratch dev backends on e.g. 8001 and point any static-server proxy there. Never run test mutations against the live stack (real patient data) — verify via its read-only endpoints (`/health`, image contents) only.
- `data/` is root-owned (from a volume mount); use `work/` for scratch files.
- For E2E/UI debugging: system chromium exists (`/usr/bin/chromium`, launch with `--no-sandbox` via playwright-core from `frontend/node_modules`; `NODE_PATH=frontend/node_modules node script.cjs`). Vite dev server proxies `/api` to `:8000`; the compose nginx serves the same paths, so a local uvicorn + a tiny static server for `dist/` faithfully reproduces prod routing. Detach long-running dev servers with `setsid nohup ... < /dev/null & disown` — a plain background process dies with the shell's timeout.
- `page.waitForSelector('text=سامانه مطب')` matches the **login page's own title** — wait for a post-login marker (e.g. the dashboard heading) or you'll race the async login and misread the app state.

## Architecture invariants

- **Soft deletes everywhere**: domain tables + `users` have `deleted_at`; uniqueness is via **partial unique indexes** (`uq_*_live`, `WHERE deleted_at IS NULL`) so deleted values are reusable. Read paths must filter `deleted_at IS NULL` across the whole parent chain (a file is visible only if itself + appointment + patient are alive) — the trash API (`app/api/v1/trash.py`) implements list/restore (doctor+) and purge (admin-only, the only path that unlinks physical files). Never hard-delete in regular endpoints; never unlink files on soft delete.
- **Audit trail**: every mutating endpoint calls `services/audit.py::log_action` (never raises) before returning; admin-only listing `GET /admin/audit`. New mutations must be audited.
- **Roles**: receptionist < doctor < admin (`require_at_least`/`require_role` in `app/api/deps.py`). Appointment medical fields (`cm/hx/px/rx`) are blanked in the serializer for receptionists — server-side, not just UI. File (attachment) upload/edit/note-only create and appointment delete are doctor+; patients delete is admin-only.
- **Attachments**: two kinds of rows — real files (`stored_filename` set) and **note-only** rows (`stored_filename IS NULL`, `original_filename IS NULL`, `missing_file=False`; created via `POST /appointments/{id}/files/note`, doctor+). `missing_file=True` means "a file was expected but is absent" (migration), NOT note-only. Download must handle both. The partial unique index `uq_attachments_stored_filename_live` tolerates multiple NULLs (SQLite + PG), so note-only rows never collide. `scripts/check_files.py` skips `stored_filename IS NULL`.
- **Transactions/payments**: cash-vs-card is the `pos` bool (کارت‌خوان/نقدی). Day-wide payments view: `GET /payments?date=` (payments.py; APP_TZ day boundaries on the **appointment's** `scheduled_at`, defaults to today-in-Tehran, receptionist+; `Transaction` has no created_at, so the appointment date is the payment timestamp). Per-type aggregates for the same day: `GET /payments/summary?date=` (`PaymentTypeStat`: count/total/POS/cash split).
- **Backup** (`app/api/v1/backup.py`, admin-only, audited): on-demand job — `POST /admin/backup` starts a daemon thread (module-level status dict + lock; 409 `backup_running` if concurrent), `GET` polls status/size, `GET /download` streams the tar.gz (manifest.json + DB dump + `uploads/`), `DELETE` discards. The api container has **no pg_dump** — the DB is dumped via psycopg2 `COPY ... TO STDOUT` per table (FK order, REPEATABLE READ snapshot); `_psycopg2_url()` must strip dialect schemes (`postgresql+asyncpg://` → plain `postgresql://` — raw psycopg2 cannot parse `+psycopg2`/`+asyncpg` DSNs). Table dumps use `SpooledTemporaryFile` and uploads are streamed — never buffer the archive in memory.
- **Alembic**: `alembic/env.py` converts the async URL (asyncpg→psycopg2), so `psycopg2-binary` is a required dep. Migrations are additive and must be safe to auto-apply on a live DB at container boot.
- **Pagination**: `Page[T]` + `paginate()` (single-column selects) / `paginate_rows()` (multi-column selects — `db.scalars` silently drops extra columns).

## Conventions

- API errors use the uniform envelope `{"error": {"code", "message", "details"}}` via `app/core/errors.py` (`ConflictError` 409, `BusinessRuleError`/validation 422, `NotFoundError` 404). Raise these instead of bare `HTTPException` where a code matters.
- **FastAPI multipart**: fields alongside an `UploadFile` must be declared with `Form("...")` — a bare `param: str = ""` becomes a *query param* and the form field is silently dropped (this exact bug shipped once: upload description/notes never persisted).
- UI is Persian/RTL with Jalali dates: internal state and API contract stay **Gregorian ISO/UTC**; only display/input is Jalali. Pickers: `frontend/src/components/JalaliDates.tsx` (react-multi-date-picker); display helpers: `src/lib/jalali.ts` (incl. `toFaDigits`/`toEnDigits` — normalize Persian-digit *input* with `toEnDigits` before sending; the DB stores ASCII digits). Backend day-boundary logic uses `APP_TZ` (Asia/Tehran) from `app/db/session.py`.
- antd Select with `options=[{value: id, label: name}]` needs `showSearch` + `optionFilterProp="label"` — the default filter matches against `value` (the numeric id), so searchable selects silently show "no results" without it. Modal forms whose values must not survive a reopen should reset on open (form instance lives outside the modal); prefer `destroyOnHidden` (antd ≥5.25, `destroyOnClose` is deprecated).
- Dark mode: `useTheme()` from `frontend/src/components/ThemeContext.tsx` (persisted `clinic-theme` localStorage, `html.dark` class, switches antd `theme.darkAlgorithm`). Derive custom colors from `theme.useToken()` tokens (e.g. `colorBgContainer`) — never hardcode `#fff`/`#eee` in components. Jalali picker inputs are themed via CSS overrides in `index.css` (their inline style can't be overridden by class).
- ruff line-length 100; `B008` ignored (FastAPI `Depends()` defaults). mypy must stay clean — annotate `dict[str, Any]` for dict-literal params, and don't unpack into `_` inside endpoints that already have the `_` User dependency (mypy: "variable has type User").
- File uploads from the UI go through the axios client (`api.post` with `FormData`; antd `Upload` only selects the file via `beforeUpload: () => false`) — never antd's auto-XHR upload path, which bypasses the token-refresh interceptor.
- Legacy import tooling: `scripts/migrate_sqlite.py` (dry-run default, `--apply` idempotent, content-hash dedup for files; legacy English payment descriptions `Visit`/`Spiro`/`Other` are translated to ویزیت/اسپیرو/سایر via `normalize_txn_description` — case-insensitive after strip, unmatched values kept as-is), `scripts/check_files.py` (DB↔disk consistency), `scripts/verify_import.py` (independent cross-check; its DB DSN is hardcoded to a test container). `old_database/` is a real production snapshot — treat as sensitive. Synthetic legacy DB for testing the migration: `scripts/make_test_legacy_db.py`.

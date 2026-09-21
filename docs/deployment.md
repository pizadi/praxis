# Deployment & operations

## Docker compose

```bash
cp .env.example .env    # edit secrets!
docker compose up -d --build
```

- Three services: `web` (nginx serving the built UI + reverse proxy),
  `api` (FastAPI), `db` (PostgreSQL 16). The api container auto-runs
  `alembic upgrade head` at boot — migrations must be safe to auto-apply.
- **Rebuild to ship**: `docker compose up -d --build api web` — code changes
  are NOT live until the images are rebuilt (a "missing" feature on the
  live UI is usually a stale container, not a code bug).
- The compose Postgres maps to host port **5434** (container-internal
  `db:5432`); a stray test container on 5432 can masquerade as the real DB —
  check `docker ps` first.
- The api binds host port 8000, web port 80.

## Secrets

- `.env` (gitignored) holds `BOOTSTRAP_ADMIN_*`, `SECRET_KEY`, DB
  credentials. pydantic reads `env_file=".env"` **relative to CWD** —
  running the backend from the repo root vs `backend/` differs; in tests
  conftest's env vars mask this.
- Production startup refuses default `SECRET_KEY`/admin password
  (`CLINIC_ENV=production`).

## External cron (on the box)

```bash
# nightly pg_dump with 14-day retention + uploaded files
0 2 * * *  docker exec new-patients-db-1 pg_dump -U clinic clinic | gzip > /ssd/backups/db-$(date +\%F).sql.gz && find /ssd/backups -name 'db-*.sql.gz' -mtime +14 -delete
30 2 * * * rsync -a /ssd/clinic-data/uploads/ /ssd/backups/uploads/
```

Do a restore drill monthly. The in-app tarball backup/import (see
[backup-import.md](backup-import.md)) is the admin UI path for the same
need.

## Dev sandbox quirks (this repo's development environment)

- Docker bridge networking may be broken (`operation not supported` on
  veth): use `--network host` for test containers and
  `DOCKER_BUILDKIT=0 docker build --network=host` for builds. The user's
  own compose stack runs fine elsewhere — don't "fix" compose networking
  because a local test failed.
- Registries are flaky; PyPI/npm mirrors are configured (see
  `frontend/.npmrc`). If npm 504s, retry with
  `--registry=https://mirror-npm.runflare.com`.
- `data/` may be root-owned from a volume mount — use `work/` for scratch
  files.
- For UI debugging: system chromium + playwright-core from
  `frontend/node_modules` (`NODE_PATH=frontend/node_modules node script.cjs`,
  launch with `--no-sandbox`). Detach long-running dev servers with
  `setsid nohup … < /dev/null & disown`.

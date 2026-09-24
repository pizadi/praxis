"""Test fixtures.

IMPORTANT: environment is configured at module import time, BEFORE any
`app.*` import happens elsewhere. Pydantic-settings caches values at first
import, so ordering matters.

Layout:
- tests/factories.py          — API builders (mk_patient, mk_appointment, …)
- tests/unit/                 — pure-function tests (no HTTP, no DB)
- tests/api/                  — per-resource API tests (httpx ASGI client)
- tests/parity/               — questionnaire-validator parity (shared corpus
                                with frontend/src/parity)
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="clinic-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["SECRET_KEY"] = "test-secret-key-0000000000000000"
os.environ["CLINIC_ENV"] = "test"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app, bootstrap_admin  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await bootstrap_admin()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# --- auth helpers ----------------------------------------------------------------


async def login(
    client: AsyncClient, username: str = "admin", password: str = "admin123"
) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    refresh = r.cookies.get("praxis_refresh")
    assert refresh, "login did not set the HttpOnly refresh cookie"
    return data["access_token"], refresh


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_user(
    client: AsyncClient,
    admin_token: str,
    username: str,
    role: str = "receptionist",
    password: str = "passw0rd123",
) -> None:
    roles = (await client.get("/api/v1/roles", headers=auth(admin_token))).json()
    role_id = next(r["id"] for r in roles["items"] if r["name"] == role)
    r = await client.post(
        "/api/v1/users",
        json={"username": username, "password": password, "role_id": role_id},
        headers=auth(admin_token),
    )
    assert r.status_code == 201, r.text


# --- ready-made role fixtures (token strings) --------------------------------------


@pytest.fixture
async def admin_token(client) -> str:
    return (await login(client))[0]


@pytest.fixture
async def doctor(client, admin_token) -> str:
    await make_user(client, admin_token, "drhouse", role="doctor")
    return (await login(client, "drhouse", "passw0rd123"))[0]


@pytest.fixture
async def recep(client, admin_token) -> str:
    await make_user(client, admin_token, "recep1", role="receptionist")
    return (await login(client, "recep1", "passw0rd123"))[0]


# --- job polling (backup/import run in daemon threads; the tests poll) -------------


async def wait_backup_status(client: AsyncClient, token: str, status: str) -> dict:
    for _ in range(100):
        r = await client.get("/api/v1/admin/backup", headers=auth(token))
        st = r.json()
        if st["status"] == status:
            return st
    raise AssertionError(f"backup never reached {status!r}: {st}")


async def wait_import_done(client: AsyncClient, token: str) -> dict:
    for _ in range(100):
        r = await client.get("/api/v1/admin/backup/import", headers=auth(token))
        if r.status_code != 200:
            raise AssertionError(f"import status endpoint: {r.status_code} {r.text}")
        st = r.json()
        if st["status"] != "importing":
            return st
    raise AssertionError("import did not finish")

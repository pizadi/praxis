"""Test fixtures.

IMPORTANT: environment is configured at module import time, BEFORE any
`app.*` import happens elsewhere. Pydantic-settings caches values at first
import, so ordering matters.
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


# --- Helpers -------------------------------------------------------------------


async def login(
    client: AsyncClient, username: str = "admin", password: str = "admin123"
) -> tuple[str, str]:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return data["access_token"], data["refresh_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_user(
    client: AsyncClient,
    admin_token: str,
    username: str,
    role: str = "receptionist",
    password: str = "passw0rd123",
) -> None:
    r = await client.post(
        "/api/v1/users",
        json={"username": username, "password": password, "role": role},
        headers=auth(admin_token),
    )
    assert r.status_code == 201, r.text

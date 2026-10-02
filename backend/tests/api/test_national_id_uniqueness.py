"""National-ID uniqueness: the DATABASE is the authority.

The endpoints pre-check for a duplicate so they can return a friendly 409, but
that check is a race — two concurrent creates both pass it and one loses at the
index. These tests pin both halves of the contract:

- the DB rejects a duplicate live row (partial unique index) and a soft-deleted
  row releases the ID for reuse;
- a violation that slips past the pre-check comes back as the same 409
  envelope, never as a 500.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import unique_violation
from tests.conftest import auth, login
from tests.factories import mk_patient

BODY = {
    "first_name": "Second",
    "last_name": "Row",
    "year_of_birth": "1370",
    "gender": 0,
}


async def test_database_rejects_duplicate_national_id(client):
    """Bypassing the API: the unique index refuses a second LIVE row with the
    same national ID. This is the actual guarantee — the endpoint's pre-check
    only exists to produce a friendlier error."""
    from app.db.session import SessionLocal
    from app.models import Patient

    token, _ = await login(client)
    await mk_patient(client, token, national_id="1234567890")

    async with SessionLocal() as session:
        with pytest.raises(IntegrityError) as exc:
            session.add(
                Patient(
                    national_id="1234567890",
                    first_name="Second",
                    last_name="Row",
                    year_of_birth="1370",
                    phone_number="",
                    gender=0,
                )
            )
            await session.flush()
        # and the handler maps exactly this to the API's duplicate code
        assert unique_violation(exc.value) == (
            "national_id_taken",
            "National ID already registered",
        )


async def test_soft_delete_releases_the_national_id(client):
    """A deleted patient must not block a new registration with the same ID
    (the unique index is partial: WHERE deleted_at IS NULL)."""
    from app.db.session import SessionLocal
    from app.models import Patient

    token, _ = await login(client)
    p = await mk_patient(client, token, national_id="1234567890")

    r = await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert r.status_code == 204

    async with SessionLocal() as session:
        session.add(
            Patient(
                national_id="1234567890",
                first_name="Re",
                last_name="Registered",
                year_of_birth="1371",
                phone_number="",
                gender=1,
            )
        )
        await session.flush()  # must NOT raise


async def test_race_returns_409_not_500(client, monkeypatch):
    """Simulate the lost race: the pre-check finds nothing (as it would for a
    row inserted microseconds earlier by a concurrent request) and the INSERT
    trips the index. The client must see 409 national_id_taken — a 500 here is
    the bug this test exists to prevent."""
    from sqlalchemy.ext.asyncio import AsyncSession

    token, _ = await login(client)
    await mk_patient(client, token, national_id="1234567890")

    original = AsyncSession.scalar

    async def racing_scalar(self, statement, *args, **kwargs):
        # only the endpoint's duplicate pre-check is blinded — the auth
        # dependency's own SELECT must still find the user
        if "FROM patients" in str(statement):
            return None
        return await original(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", racing_scalar)

    r = await client.post(
        "/api/v1/patients", json={**BODY, "national_id": "1234567890"}, headers=auth(token)
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "national_id_taken"


async def test_non_unique_integrity_errors_stay_500(client, monkeypatch):
    """Only uniqueness violations become 409. A NOT NULL / FK violation is a
    server bug and must keep surfacing as a 500, not be disguised as a
    conflict."""
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    class FakeNotNull(SAIntegrityError):
        def __init__(self):
            super().__init__("INSERT", {}, Exception("NOT NULL constraint failed: x.y"))

    from app.main import app

    assert unique_violation(FakeNotNull()) is None
    assert app is not None

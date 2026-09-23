"""Permissions matrix: every endpoint is gated by require_perm — any-of
catalog permissions, role data (NOT hierarchy). This sweep walks representative
endpoints × roles and pins the access decision, so a permission renamed or a
role set silently changed fails here.

UI checks (hasPerm) only hide buttons — the server is authoritative.
"""

import pytest

from tests.conftest import auth, login, make_user
from tests.factories import (
    mk_appointment,
    mk_file,
    mk_patient,
    mk_prescription,
    mk_response,
    mk_template,
    mk_transaction,
)

PATIENT_BODY = {
    "national_id": "1234567890",
    "first_name": "T",
    "last_name": "T",
    "year_of_birth": "1990",
    "gender": 0,
}


@pytest.fixture
async def seeded(client, admin_token):
    """A live patient + appointment + transaction + file + template/response
    + prescription + a soft-deleted patient (trash content)."""
    pid = (await mk_patient(client, admin_token))["id"]
    appt = await mk_appointment(client, admin_token, pid)
    await mk_transaction(client, admin_token, appt["id"])
    await mk_file(client, admin_token, pid)
    tpl = await mk_template(client, admin_token)
    await mk_response(client, admin_token, pid, tpl["id"])
    await mk_prescription(client, admin_token, pid)
    dead = await mk_patient(client, admin_token, national_id="2222222222")
    await client.delete(f"/api/v1/patients/{dead['id']}", headers=auth(admin_token))
    return {"pid": pid, "appt_id": appt["id"], "tpl_id": tpl["id"]}


async def _hit(client, token, method, path, json=None):
    kwargs: dict = {"headers": auth(token)}
    if json is not None and method in ("post", "patch", "put"):
        kwargs["json"] = json
    return await getattr(client, method)(path, **kwargs)


async def test_receptionist_allowed_endpoints(client, recep, seeded):
    """front desk: patients r/w, appointments r/create, stage change, files
    read, transactions, questionnaires read/fill, payments view."""
    allowed = [
        ("get", "/api/v1/patients", None),
        ("post", "/api/v1/patients", PATIENT_BODY),
        ("get", f"/api/v1/patients/{seeded['pid']}", None),
        ("get", "/api/v1/appointments", None),
        ("post", f"/api/v1/patients/{seeded['pid']}/appointments",
         {"scheduled_at": "2099-01-01T09:00:00+03:30"}),
        ("patch", f"/api/v1/appointments/{seeded['appt_id']}/stage",
         {"direction": "advance"}),
        ("get", f"/api/v1/patients/{seeded['pid']}/files", None),
        ("get", f"/api/v1/appointments/{seeded['appt_id']}/transactions", None),
        ("post", f"/api/v1/appointments/{seeded['appt_id']}/transactions",
         {"description": "ویزیت", "amount": 1000, "pos": True}),
        ("get", f"/api/v1/patients/{seeded['pid']}/questionnaires", None),
        ("post", f"/api/v1/patients/{seeded['pid']}/questionnaires",
         {"template_id": seeded["tpl_id"], "answers": {"pain_level": 3}}),
        ("get", "/api/v1/payments", None),
    ]
    for method, path, body in allowed:
        r = await _hit(client, recep, method, path, body)
        assert r.status_code < 500, (method, path, r.text)
        assert r.status_code not in (401, 403), (method, path, r.text)


async def test_receptionist_denied_endpoints(client, recep, seeded):
    """no medical notes edit, no prescription anything, no delete/stage-edit,
    no trash/audit/users/roles/stats/taxonomies/backup."""
    denied = [
        ("patch", f"/api/v1/appointments/{seeded['appt_id']}", {"notes": "x"}),
        ("delete", f"/api/v1/appointments/{seeded['appt_id']}", None),
        ("post", f"/api/v1/patients/{seeded['pid']}/prescriptions", {"items": [{"name": "x"}]}),
        ("get", f"/api/v1/patients/{seeded['pid']}/prescriptions", None),
        ("get", "/api/v1/prescription-items", None),
        ("post", "/api/v1/prescription-items", {"name": "x"}),
        ("get", "/api/v1/admin/trash/patients", None),
        ("get", "/api/v1/admin/audit", None),
        ("get", "/api/v1/users", None),
        ("get", "/api/v1/roles", None),
        ("get", "/api/v1/roles/permissions", None),
        ("get", "/api/v1/stats/summary", None),
        ("get", "/api/v1/admin/backup", None),
    ]
    for method, path, body in denied:
        r = await _hit(client, recep, method, path, body)
        assert r.status_code == 403, (method, path, r.text)


async def test_doctor_cannot_administer(client, doctor, admin_token, seeded):
    """doctor: medical everything, but NOT user/role/backup/purge admin."""
    # doctor CAN read prescriptions + edit appointments
    r = await _hit(client, doctor, "get", f"/api/v1/patients/{seeded['pid']}/prescriptions")
    assert r.status_code == 200
    # doctor CANNOT manage users/roles/backups or purge trash
    dead = await mk_patient(client, admin_token, national_id="3333333333")
    await client.delete(f"/api/v1/patients/{dead['id']}", headers=auth(admin_token))
    denied = [
        ("get", "/api/v1/users", None),
        ("get", "/api/v1/roles", None),
        ("get", "/api/v1/admin/backup", None),
        ("delete", f"/api/v1/admin/trash/patients/{dead['id']}", None),
    ]
    for method, path, body in denied:
        r = await _hit(client, doctor, method, path, body)
        assert r.status_code == 403, (method, path, r.text)


async def test_anonymous_is_401_everywhere(client, seeded):
    """No token → 401 (not 403) on every endpoint, regardless of permission."""
    for method, path in (
        ("get", "/api/v1/patients"),
        ("get", f"/api/v1/patients/{seeded['pid']}"),
        ("get", "/api/v1/appointments"),
        ("get", "/api/v1/admin/audit"),
        ("get", "/api/v1/admin/backup"),
        ("post", "/api/v1/patients"),
    ):
        kwargs = {"json": {}} if method == "post" else {}
        r = await getattr(client, method)(path, **kwargs)
        assert r.status_code == 401, (method, path)


async def test_role_grant_takes_effect_immediately(client, admin_token, seeded):
    """Permission is loaded per request from role data — a role edit applies
    to already-logged-in users (no re-login, no token cache)."""
    # a role with NO permissions first
    r = await client.post(
        "/api/v1/roles", json={"name": "norole", "permissions": []}, headers=auth(admin_token)
    )
    assert r.status_code == 201, r.text
    await make_user(client, admin_token, "reader1", role="norole")
    reader, _ = await login(client, "reader1", "passw0rd123")
    body = {**PATIENT_BODY, "national_id": "9999999991"}
    r = await _hit(client, reader, "post", "/api/v1/patients", body)
    assert r.status_code == 403
    # grant via a new role
    roles = (await client.get("/api/v1/roles", headers=auth(admin_token))).json()
    recep_role = next(r_ for r_ in roles["items"] if r_["name"] == "receptionist")
    users = (await client.get("/api/v1/users?limit=100", headers=auth(admin_token))).json()
    uid = next(u["id"] for u in users["items"] if u["username"] == "reader1")
    r = await client.patch(
        f"/api/v1/users/{uid}", json={"role_id": recep_role["id"]}, headers=auth(admin_token)
    )
    assert r.status_code == 200
    new_body = {**PATIENT_BODY, "national_id": "9999999992"}
    r = await _hit(client, reader, "post", "/api/v1/patients", new_body)
    assert r.status_code == 201

"""Audit trail + patient-level aggregate endpoint tests."""

import io

from tests.conftest import auth, login


async def _mk_patient(client, token, **overrides) -> dict:
    body = {
        "national_id": "1234567890",
        "first_name": "Test",
        "last_name": "Testi",
        "year_of_birth": "1990",
        "gender": 0,
    }
    body.update(overrides)
    r = await client.post("/api/v1/patients", json=body, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()


async def _mk_appt(client, token, patient_id, at="2026-09-10T10:30:00+03:30") -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/appointments",
        json={"scheduled_at": at},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _audit_entries(client, token, **params) -> list[dict]:
    r = await client.get(
        "/api/v1/admin/audit", params=params, headers=auth(token)
    )
    assert r.status_code == 200, r.text
    return r.json()["items"]


async def test_audit_records_crud_actions(client):
    token, _ = await login(client)

    p = await _mk_patient(client, token)
    entries = await _audit_entries(client, token, entity_type="patient")
    assert any(
        e["action"] == "create" and e["entity_id"] == p["id"] for e in entries
    ), entries
    create_entry = next(
        e for e in entries if e["action"] == "create" and e["entity_id"] == p["id"]
    )
    assert create_entry["username"] == "admin"
    assert create_entry["summary"].endswith("(1234567890)")
    assert create_entry["ip_address"] != ""  # captured from the request

    # update
    await client.patch(
        f"/api/v1/patients/{p['id']}",
        json={"phone_number": "09121110000"},
        headers=auth(token),
    )
    entries = await _audit_entries(client, token, entity_type="patient")
    upd = next(e for e in entries if e["action"] == "update" and e["entity_id"] == p["id"])
    assert '"phone_number"' in (upd["details"] or "")

    # delete → restore → purge all audited
    await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))
    await client.post(
        f"/api/v1/admin/trash/patients/{p['id']}/restore", headers=auth(token)
    )
    await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))
    await client.delete(f"/api/v1/admin/trash/patients/{p['id']}", headers=auth(token))
    entries = await _audit_entries(client, token, entity_type="patient")
    actions = [e["action"] for e in entries if e["entity_id"] == p["id"]]
    assert actions.count("delete") == 2
    assert "restore" in actions
    assert "purge" in actions


async def test_audit_appointment_and_payment(client):
    token, _ = await login(client)
    p = await _mk_patient(client, token)
    appt = await _mk_appt(client, token, p["id"])
    await client.post(
        f"/api/v1/appointments/{appt['id']}/transactions",
        json={"description": "visit", "amount": 250000, "pos": True},
        headers=auth(token),
    )
    await client.post(
        f"/api/v1/patients/{p['id']}/files",
        data={"description": "lab"},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=auth(token),
    )
    await client.delete(f"/api/v1/appointments/{appt['id']}", headers=auth(token))

    for etype in ("appointment", "transaction", "file"):
        entries = await _audit_entries(client, token, entity_type=etype)
        assert entries, f"no audit entries for {etype}"
        assert entries[0]["action"] in ("delete", "create")


async def test_audit_admin_only(client):
    admin, _ = await login(client)
    from tests.conftest import make_user

    await make_user(client, admin, "recep1", role="receptionist")
    recep, _ = await login(client, "recep1", "passw0rd123")

    r = await client.get("/api/v1/admin/audit", headers=auth(recep))
    assert r.status_code == 403
    r = await client.get("/api/v1/admin/audit", headers=auth(admin))
    assert r.status_code == 200


async def test_patient_level_files_and_payments(client):
    token, _ = await login(client)
    p = await _mk_patient(client, token)
    a1 = await _mk_appt(client, token, p["id"], at="2026-09-10T09:00:00+03:30")
    a2 = await _mk_appt(client, token, p["id"], at="2026-09-11T09:00:00+03:30")

    for appt in (a1, a2):
        await client.post(
            f"/api/v1/appointments/{appt['id']}/transactions",
            json={"description": "visit", "amount": 100000, "pos": True},
            headers=auth(token),
        )
    r = await client.post(
        f"/api/v1/patients/{p['id']}/files",
        data={"description": "report"},
        files={"file": ("f.txt", io.BytesIO(b"data"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201

    # all files of the patient
    r = await client.get(
        f"/api/v1/patients/{p['id']}/files", headers=auth(token)
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["patient_id"] == p["id"]

    # all-payments across both, newest appointment first
    r = await client.get(
        f"/api/v1/patients/{p['id']}/all-transactions", headers=auth(token)
    )
    body = r.json()
    assert body["total"] == 2
    assert body["items"][0]["appointment_id"] == a2["id"]
    assert "appointment_scheduled_at" in body["items"][0]

    # soft-delete one appointment → its payments vanish from the aggregate,
    # but patient-level files are untouched
    await client.delete(f"/api/v1/appointments/{a2['id']}", headers=auth(token))
    files = await client.get(f"/api/v1/patients/{p['id']}/files", headers=auth(token))
    assert len(files.json()) == 1
    r = await client.get(
        f"/api/v1/patients/{p['id']}/all-transactions", headers=auth(token)
    )
    assert r.json()["total"] == 1

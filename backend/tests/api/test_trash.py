"""Soft delete, trash panel, subtree restore rules, patient search."""

import io

from tests.conftest import auth, login, make_user
from tests.factories import mk_appointment, mk_patient


async def _mk_patient(client, token, **overrides) -> dict:
    return await mk_patient(client, token, **overrides)


async def _mk_appt(client, token, patient_id, at="2026-09-10T10:30:00+03:30") -> dict:
    return await mk_appointment(client, token, patient_id, at=at, cm="chief", rx="plan")


# --- soft delete basics -------------------------------------------------------


async def test_soft_delete_patient_hides_everywhere(client):
    token, _ = await login(client)
    p = await _mk_patient(client, token)
    appt = await _mk_appt(client, token, p["id"])

    # admin soft-deletes the patient
    r = await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert r.status_code == 204

    # patient 404s, is not in search results
    r = await client.get(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert r.status_code == 404
    r = await client.get("/api/v1/patients", params={"q": "Testi"}, headers=auth(token))
    assert r.json()["total"] == 0

    # appointments hidden (own list + direct get)
    r = await client.get("/api/v1/appointments", headers=auth(token))
    assert r.json()["total"] == 0
    r = await client.get(f"/api/v1/appointments/{appt['id']}", headers=auth(token))
    assert r.status_code == 404

    # trash panel sees it (doctor+)
    r = await client.get("/api/v1/admin/trash/patients", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["title"] == "Test Testi"

    # restore brings everything back
    r = await client.post(
        f"/api/v1/admin/trash/patients/{p['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 200
    r = await client.get(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert r.status_code == 200
    r = await client.get(f"/api/v1/appointments/{appt['id']}", headers=auth(token))
    assert r.status_code == 200


async def test_soft_delete_appointment_subtree(client):
    token, _ = await login(client)
    p = await _mk_patient(client, token)
    appt = await _mk_appt(client, token, p["id"])
    # add a file (patient-level since 1.3) and a transaction
    r = await client.post(
        f"/api/v1/patients/{p['id']}/files",
        data={"description": "report"},
        files={"file": ("r.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=auth(token),
    )
    assert r.status_code == 201
    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/transactions",
        json={"description": "visit", "amount": 500},
        headers=auth(token),
    )
    assert r.status_code == 201

    # delete the appointment (doctor can)
    r = await client.delete(f"/api/v1/appointments/{appt['id']}", headers=auth(token))
    assert r.status_code == 204

    # files are PATIENT-level now — they stay visible after appointment deletion
    r = await client.get(f"/api/v1/patients/{p['id']}/files", headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()) == 1
    # stats exclude the deleted appointment
    r = await client.get(
        "/api/v1/stats/summary",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        headers=auth(token),
    )
    assert r.json()["num_appointments"] == 0
    assert r.json()["num_transactions"] == 0

    # trash: appointment listed, files/txns NOT listed (subtree rule)
    r = await client.get("/api/v1/admin/trash/appointments", headers=auth(token))
    assert r.json()["total"] == 1
    r = await client.get("/api/v1/admin/trash/attachments", headers=auth(token))
    assert r.json()["total"] == 0
    r = await client.get("/api/v1/admin/trash/transactions", headers=auth(token))
    assert r.json()["total"] == 0

    # restore appointment → transactions visible again (files never hid)
    r = await client.post(
        f"/api/v1/admin/trash/appointments/{appt['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 200
    r = await client.get(
        f"/api/v1/appointments/{appt['id']}/transactions", headers=auth(token)
    )
    assert r.json()["total"] == 1


async def test_restore_child_refused_while_parent_deleted(client):
    token, _ = await login(client)
    p = await _mk_patient(client, token)
    appt = await _mk_appt(client, token, p["id"])

    await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))
    # try to restore the (hidden) appointment while its patient is deleted → 409
    r = await client.post(
        f"/api/v1/admin/trash/appointments/{appt['id']}/restore", headers=auth(token)
    )
    # not in trash directly → 404 (subtree rule: it's the patient's deletion)
    assert r.status_code == 404

    # now also delete the appointment itself directly, then restore → 409
    # (set it deleted via direct delete first requires it visible: use trash API path)
    # restore the patient, delete the appointment, then delete patient again
    await client.post(f"/api/v1/admin/trash/patients/{p['id']}/restore", headers=auth(token))
    await client.delete(f"/api/v1/appointments/{appt['id']}", headers=auth(token))
    await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))
    r = await client.post(
        f"/api/v1/admin/trash/appointments/{appt['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "parent_still_deleted"

    # restore the patient, then the appointment works
    await client.post(f"/api/v1/admin/trash/patients/{p['id']}/restore", headers=auth(token))
    r = await client.post(
        f"/api/v1/admin/trash/appointments/{appt['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 200


async def test_national_id_reusable_after_soft_delete(client):
    token, _ = await login(client)
    p = await _mk_patient(client, token, national_id="1111111111")
    await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))

    # same national_id can be registered again while the original is deleted
    r = await _mk_patient(client, token, national_id="1111111111", first_name="Second")
    assert r["id"] != p["id"]

    # restoring the original now conflicts
    rr = await client.post(
        f"/api/v1/admin/trash/patients/{p['id']}/restore", headers=auth(token)
    )
    assert rr.status_code == 409
    assert rr.json()["error"]["code"] == "unique_conflict"


async def test_soft_delete_tag_keeps_m2m_and_restores(client):
    token, _ = await login(client)
    r = await client.post("/api/v1/tags", json={"name": "VIP"}, headers=auth(token))
    vip = r.json()
    p = await _mk_patient(client, token, tag_ids=[vip["id"]])

    await client.delete(f"/api/v1/tags/{vip['id']}", headers=auth(token))
    # hidden from list
    r = await client.get("/api/v1/tags", headers=auth(token))
    assert r.json()["total"] == 0
    # name reusable while deleted
    r = await client.post("/api/v1/tags", json={"name": "VIP"}, headers=auth(token))
    assert r.status_code == 201

    # restore original → conflict (live VIP exists)
    r = await client.post(
        f"/api/v1/admin/trash/tags/{vip['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 409

    # delete the new one; restore original; patient's link intact
    r = await client.get("/api/v1/tags", headers=auth(token))
    new_id = r.json()["items"][0]["id"]
    await client.delete(f"/api/v1/tags/{new_id}", headers=auth(token))
    r = await client.post(
        f"/api/v1/admin/trash/tags/{vip['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 200
    r = await client.get(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert [t["id"] for t in r.json()["tags"]] == [vip["id"]]


async def test_user_soft_delete_blocks_login_and_restores(client):
    admin, _ = await login(client)
    await make_user(client, admin, "recep1", role="receptionist")

    users = (await client.get("/api/v1/users", headers=auth(admin))).json()
    uid = next(u["id"] for u in users["items"] if u["username"] == "recep1")
    r = await client.delete(f"/api/v1/users/{uid}", headers=auth(admin))
    assert r.status_code == 204

    # cannot log in while deleted
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep1", "password": "passw0rd123"}
    )
    assert r.status_code == 401
    # hidden from user list
    r = await client.get("/api/v1/users", headers=auth(admin))
    assert all(u["username"] != "recep1" for u in r.json()["items"])
    # in trash
    r = await client.get("/api/v1/admin/trash/users", headers=auth(admin))
    assert r.json()["total"] == 1

    # restore → login works again
    r = await client.post(
        f"/api/v1/admin/trash/users/{uid}/restore", headers=auth(admin)
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep1", "password": "passw0rd123"}
    )
    assert r.status_code == 200


async def test_trash_permissions(client):
    admin, _ = await login(client)
    await make_user(client, admin, "recep1", role="receptionist")
    await make_user(client, admin, "drhouse", role="doctor")
    recep, _ = await login(client, "recep1", "passw0rd123")
    doctor, _ = await login(client, "drhouse", "passw0rd123")

    p = await _mk_patient(client, admin)
    await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(admin))

    # receptionist: no access to trash
    r = await client.get("/api/v1/admin/trash/patients", headers=auth(recep))
    assert r.status_code == 403
    # doctor: can list
    r = await client.get("/api/v1/admin/trash/patients", headers=auth(doctor))
    assert r.status_code == 200
    # doctor: can restore
    r = await client.post(
        f"/api/v1/admin/trash/patients/{p['id']}/restore", headers=auth(doctor)
    )
    assert r.status_code == 200

    # purge is admin-only
    p2 = await _mk_patient(client, admin, national_id="2222222222")
    await client.delete(f"/api/v1/patients/{p2['id']}", headers=auth(admin))
    r = await client.delete(
        f"/api/v1/admin/trash/patients/{p2['id']}", headers=auth(doctor)
    )
    assert r.status_code == 403
    r = await client.delete(
        f"/api/v1/admin/trash/patients/{p2['id']}", headers=auth(admin)
    )
    assert r.status_code == 204
    # permanently gone: not in trash, not restorable
    r = await client.get("/api/v1/admin/trash/patients", headers=auth(admin))
    assert r.json()["total"] == 0
    r = await client.post(
        f"/api/v1/admin/trash/patients/{p2['id']}/restore", headers=auth(admin)
    )
    assert r.status_code == 404


# --- search --------------------------------------------------------------------


async def test_search_by_phone_and_omnibox(client):
    token, _ = await login(client)
    await _mk_patient(client, token, national_id="1111111111", phone_number="09121110001")
    await _mk_patient(
        client, token, national_id="2222222222", phone_number="09122220002", last_name="Other"
    )

    # explicit phone filter
    r = await client.get(
        "/api/v1/patients", params={"phone": "091211"}, headers=auth(token)
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["national_id"] == "1111111111"

    # omnibox q now matches phone too
    r = await client.get("/api/v1/patients", params={"q": "22220002"}, headers=auth(token))
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["national_id"] == "2222222222"


async def test_patient_file_listing_independent_of_appointments(client):
    """Since 1.3 files belong to the patient: the appointment brief carries
    no attachment_count anymore, and the patient files list is independent
    of appointment lifecycle."""
    token, _ = await login(client)
    p = await _mk_patient(client, token)
    a1 = await _mk_appt(client, token, p["id"], at="2026-09-10T09:00:00+03:30")
    a2 = await _mk_appt(client, token, p["id"], at="2026-09-11T09:00:00+03:30")
    r = await client.post(
        f"/api/v1/patients/{p['id']}/files",
        data={"description": "one"},
        files={"file": ("f.txt", io.BytesIO(b"data"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201
    att = r.json()
    assert att["patient_id"] == p["id"]
    assert "appointment_id" not in att

    r = await client.get(
        "/api/v1/appointments",
        params={"patient_id": p["id"]},
        headers=auth(token),
    )
    items = {i["id"]: i for i in r.json()["items"]}
    assert "attachment_count" not in items[a1["id"]]
    assert "attachment_count" not in items[a2["id"]]

    # soft-deleting the file hides it from the patient list without
    # deleting the row (restorable via trash)
    await client.delete(f"/api/v1/files/{att['id']}", headers=auth(token))
    r = await client.get(f"/api/v1/patients/{p['id']}/files", headers=auth(token))
    assert r.json() == []
    r = await client.get("/api/v1/admin/trash/attachments", headers=auth(token))
    assert r.json()["total"] == 1

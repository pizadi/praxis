"""Appointments API: CRUD, visit stages, role gating; date filtering."""

import io

from tests.conftest import auth, login, make_user
from tests.factories import mk_appointment, mk_patient


async def test_appointment_flow(client):
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
    appt = await mk_appointment(client, token, pid, cm="chief", rx="plan")

    assert appt["patient_first_name"] == "Test"
    assert appt["cm"] == "chief"

    # date-range listing in APP_TIMEZONE
    r = await client.get(
        "/api/v1/appointments",
        params={"date_from": "2026-09-10", "date_to": "2026-09-10"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # range outside
    r = await client.get(
        "/api/v1/appointments",
        params={"date_from": "2026-01-01", "date_to": "2026-01-02"},
        headers=auth(token),
    )
    assert r.json()["total"] == 0

    # reversed range → 422 with clear message (legacy silent reset fixed)
    r = await client.get(
        "/api/v1/appointments",
        params={"date_from": "2026-09-11", "date_to": "2026-09-10"},
        headers=auth(token),
    )
    assert r.status_code == 422

    # update notes (doctor+)
    r = await client.patch(
        f"/api/v1/appointments/{appt['id']}",
        json={"rx": "updated plan"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["rx"] == "updated plan"

    # patient filter
    r = await client.get(
        "/api/v1/appointments", params={"patient_id": pid}, headers=auth(token)
    )
    assert r.json()["total"] == 1


async def test_transactions(client):
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
    appt = await mk_appointment(client, token, pid)

    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/transactions",
        json={"description": "visit", "amount": 500000, "pos": True},
        headers=auth(token),
    )
    assert r.status_code == 201
    t1 = r.json()
    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/transactions",
        json={"description": "lab", "amount": 200000, "pos": False},
        headers=auth(token),
    )
    t2 = r.json()

    r = await client.get(
        f"/api/v1/appointments/{appt['id']}/transactions", headers=auth(token)
    )
    assert r.json()["total"] == 2

    # negative amount rejected
    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/transactions",
        json={"description": "bad", "amount": -1},
        headers=auth(token),
    )
    assert r.status_code == 422

    # update & delete
    r = await client.patch(
        f"/api/v1/appointments/transactions/{t1['id']}",
        json={"amount": 600000},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["amount"] == 600000
    r = await client.delete(
        f"/api/v1/appointments/transactions/{t2['id']}", headers=auth(token)
    )
    assert r.status_code == 204
    r = await client.get(
        f"/api/v1/appointments/{appt['id']}/transactions", headers=auth(token)
    )
    assert r.json()["total"] == 1


async def test_receptionist_role_gating(client):
    admin_token, _ = await login(client)
    await make_user(client, admin_token, "recep1", role="receptionist")
    await make_user(client, admin_token, "drhouse", role="doctor")
    recep, _ = await login(client, "recep1", "passw0rd123")
    doctor, _ = await login(client, "drhouse", "passw0rd123")

    pid = (await mk_patient(client, admin_token))["id"]
    appt = await mk_appointment(client, admin_token, pid)

    # receptionist sees appointment but medical fields (cm/hx/px/rx) blanked
    r = await client.get(f"/api/v1/appointments/{appt['id']}", headers=auth(recep))
    assert r.status_code == 200
    body = r.json()
    assert body["cm"] == ""
    assert body["rx"] == ""
    assert body["hx"] == ""
    assert body["px"] == ""

    # receptionist cannot edit appointment (doctor+)
    r = await client.patch(
        f"/api/v1/appointments/{appt['id']}",
        json={"notes": "hack"},
        headers=auth(recep),
    )
    assert r.status_code == 403

    # receptionist cannot upload files
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("x.txt", io.BytesIO(b"nope"), "text/plain")},
        headers=auth(recep),
    )
    assert r.status_code == 403

    # receptionist cannot read prescriptions (medical data)
    r = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(recep))
    assert r.status_code == 403

    # doctor can edit notes
    r = await client.patch(
        f"/api/v1/appointments/{appt['id']}",
        json={"notes": "doc note"},
        headers=auth(doctor),
    )
    assert r.status_code == 200
    # receptionist can see the (non-medical) notes field but never cm/hx/px/rx
    r = await client.get(f"/api/v1/appointments/{appt['id']}", headers=auth(recep))
    assert r.json()["notes"] == "doc note"
    assert r.json()["cm"] == ""

    # receptionist CAN manage transactions
    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/transactions",
        json={"description": "visit", "amount": 100},
        headers=auth(recep),
    )
    assert r.status_code == 201

    # but not stats (doctor+)
    r = await client.get(
        "/api/v1/stats/summary",
        params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        headers=auth(recep),
    )
    assert r.status_code == 403


async def test_appointment_stage_pipeline(client):
    """1.4 visit stages: default reserved, ±1 advance/regress, hard bounds,
    audit trail."""
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
    appt = await mk_appointment(client, token, pid, at="2099-01-01T09:00:00+03:30")
    assert appt["stage"] == 0  # new appointments start reserved

    url = f"/api/v1/appointments/{appt['id']}/stage"
    for expected in (1, 2, 3):
        r = await client.patch(url, json={"direction": "advance"}, headers=auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == expected

    # past the last stage → conflict
    r = await client.patch(url, json={"direction": "advance"}, headers=auth(token))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "stage_limit"

    # regress steps back down, one at a time
    for expected in (2, 1, 0):
        r = await client.patch(url, json={"direction": "regress"}, headers=auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == expected

    # below the first stage → conflict
    r = await client.patch(url, json={"direction": "regress"}, headers=auth(token))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "stage_limit"

    # invalid direction → validation error
    r = await client.patch(url, json={"direction": "skip"}, headers=auth(token))
    assert r.status_code == 422

    # stage is on the list briefs too
    r = await client.get(
        "/api/v1/appointments", params={"patient_id": pid}, headers=auth(token)
    )
    assert r.json()["items"][0]["stage"] == 0

    # audit: both directions recorded with old/new names
    r = await client.get(
        "/api/v1/admin/audit", params={"entity_type": "appointment"}, headers=auth(token)
    )
    stage_entries = [
        e for e in r.json()["items"] if isinstance(e.get("details"), str)
        and "stage" in e["details"]
    ]
    assert len(stage_entries) == 6


async def test_appointment_stage_permissions(client):
    """appointments.stage: receptionist (front-desk check-in) and doctor may
    change stages; appointment editing stays doctor+."""
    admin, _ = await login(client)
    await make_user(client, admin, "recep1", role="receptionist")
    recep, _ = await login(client, "recep1", "passw0rd123")

    pid = (await mk_patient(client, admin))["id"]
    appt = await mk_appointment(client, admin, pid)

    # receptionist cannot EDIT the appointment…
    r = await client.patch(
        f"/api/v1/appointments/{appt['id']}",
        json={"notes": "x"},
        headers=auth(recep),
    )
    assert r.status_code == 403

    # …but CAN check it in
    r = await client.patch(
        f"/api/v1/appointments/{appt['id']}/stage",
        json={"direction": "advance"},
        headers=auth(recep),
    )
    assert r.status_code == 200
    assert r.json()["stage"] == 1


async def test_files_date_filter(client):
    """date= restricts patient files to one APP_TIMEZONE day (visit tab)."""
    import datetime as dt

    from app.db.session import APP_TZ

    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("today.txt", io.BytesIO(b"x"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201
    att = r.json()

    # the APP_TZ "today" (NOT UTC — they disagree 20:30–24:00 UTC)…
    today = dt.datetime.now(APP_TZ).date().isoformat()
    r = await client.get(
        f"/api/v1/patients/{pid}/files", params={"date": today}, headers=auth(token)
    )
    assert [a["id"] for a in r.json()] == [att["id"]]

    # …vs an empty day
    r = await client.get(
        f"/api/v1/patients/{pid}/files",
        params={"date": "2001-01-01"},
        headers=auth(token),
    )
    assert r.json() == []



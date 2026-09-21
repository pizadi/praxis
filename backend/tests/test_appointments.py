"""Appointments, transactions, attachments: CRUD, role gating, file safety."""

import io
import json

from tests.conftest import auth, login, make_user


async def _mk_patient(client, token, nid="1234567890") -> int:
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": nid,
            "first_name": "Test",
            "last_name": "Testi",
            "year_of_birth": "1990",
            "gender": 0,
        },
        headers=auth(token),
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _mk_appt(client, token, patient_id, at="2026-09-10T10:30:00+03:30") -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/appointments",
        json={"scheduled_at": at, "cm": "chief", "hx": "history", "rx": "plan"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_appointment_flow(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    appt = await _mk_appt(client, token, pid)

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
    pid = await _mk_patient(client, token)
    appt = await _mk_appt(client, token, pid)

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


async def test_attachments_upload_download_edit(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    await _mk_appt(client, token, pid)

    # multipart upload — description/notes arrive as FORM fields (antd Upload "data"),
    # not query params; they must be persisted on create, not silently dropped.
    # Files belong to the PATIENT (since 1.3), not the appointment.
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        data={"description": "lab report", "notes": "pre-op"},
        files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 test bytes"), "application/pdf")},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["patient_id"] == pid
    assert att["original_filename"] == "report.pdf"
    assert att["size_bytes"] == 19
    assert att["missing_file"] is False
    assert att["description"] == "lab report"
    assert att["notes"] == "pre-op"

    # Edit description/notes — legacy system silently dropped these edits
    r = await client.patch(
        f"/api/v1/files/{att['id']}",
        json={"description": "lab report v2", "notes": "updated"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["description"] == "lab report v2"
    assert r.json()["notes"] == "updated"

    # list carries notes (shown in the UI as a collapsible box)
    r = await client.get(f"/api/v1/patients/{pid}/files", headers=auth(token))
    assert r.json()[0]["description"] == "lab report v2"
    assert r.json()[0]["notes"] == "updated"

    # download with correct content type
    r = await client.get(f"/api/v1/files/{att['id']}/download", headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content == b"%PDF-1.4 test bytes"

    # delete removes row + physical file

    r = await client.delete(f"/api/v1/files/{att['id']}", headers=auth(token))
    assert r.status_code == 204
    r = await client.get(f"/api/v1/files/{att['id']}/download", headers=auth(token))
    assert r.status_code == 404


async def test_note_only_file(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    await _mk_appt(client, token, pid)

    # create name+note without a physical file
    r = await client.post(
        f"/api/v1/patients/{pid}/files/note",
        json={"description": "شرح در جلسه", "notes": "بیمار گزارش را نفرستاد"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["description"] == "شرح در جلسه"
    assert att["notes"] == "بیمار گزارش را نفرستاد"
    assert att["original_filename"] is None
    assert att["missing_file"] is False

    # listed among the patient's files
    r = await client.get(f"/api/v1/patients/{pid}/files", headers=auth(token))
    assert r.status_code == 200
    assert r.json()[0]["id"] == att["id"]
    assert r.json()[0]["original_filename"] is None

    # download → 404 (note-only), not a crash
    r = await client.get(f"/api/v1/files/{att['id']}/download", headers=auth(token))
    assert r.status_code == 404

    # soft delete → trash restore round-trip works with no physical file
    r = await client.delete(f"/api/v1/files/{att['id']}", headers=auth(token))
    assert r.status_code == 204
    r = await client.get("/api/v1/admin/trash/attachments", headers=auth(token))
    assert r.json()["total"] == 1
    r = await client.post(
        f"/api/v1/admin/trash/attachments/{att['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 200
    r = await client.get(f"/api/v1/patients/{pid}/files", headers=auth(token))
    assert r.json()[0]["id"] == att["id"]

    # receptionist cannot create (doctor+)
    await make_user(client, token, "recep1", role="receptionist")
    recep, _ = await login(client, "recep1", "passw0rd123")
    r = await client.post(
        f"/api/v1/patients/{pid}/files/note",
        json={"description": "x"},
        headers=auth(recep),
    )
    assert r.status_code == 403


async def test_attachment_content_attach_and_replace(client):
    """Attach a physical file to a note-only row, and replace an existing
    file's content — description/notes survive, downloads reflect the change."""
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    await _mk_appt(client, token, pid)

    # note-only row → attach a file
    r = await client.post(
        f"/api/v1/patients/{pid}/files/note",
        json={"description": "شرح جلسه", "notes": "یادداشت"},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["original_filename"] is None

    r = await client.post(
        f"/api/v1/files/{att['id']}/content",
        files={"file": ("scan.png", io.BytesIO(b"\x89PNG fake image"), "image/png")},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["original_filename"] == "scan.png"
    assert body["mime_type"] == "image/png"
    assert body["size_bytes"] == len(b"\x89PNG fake image")
    assert body["missing_file"] is False
    assert body["description"] == "شرح جلسه"  # preserved
    assert body["notes"] == "یادداشت"  # preserved

    # download now works
    r = await client.get(f"/api/v1/files/{att['id']}/download", headers=auth(token))
    assert r.status_code == 200
    assert r.content == b"\x89PNG fake image"

    # replace → content and metadata change, notes survive
    r = await client.post(
        f"/api/v1/files/{att['id']}/content",
        files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 v2"), "application/pdf")},
        headers=auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["original_filename"] == "report.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["missing_file"] is False

    r = await client.get(f"/api/v1/files/{att['id']}/download", headers=auth(token))
    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 v2"
    assert r.headers["content-type"].startswith("application/pdf")

    # unknown attachment → 404
    r = await client.post(
        "/api/v1/files/999999/content",
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 404

    # receptionist (no files.write) → 403
    await make_user(client, token, "recep2", role="receptionist")
    recep, _ = await login(client, "recep2", "passw0rd123")
    r = await client.post(
        f"/api/v1/files/{att['id']}/content",
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
        headers=auth(recep),
    )
    assert r.status_code == 403

    # audit trail records the replace (details is a JSON string)
    r = await client.get("/api/v1/admin/audit?entity_type=file", headers=auth(token))
    entries = r.json()["items"]

    def details_of(e: dict) -> dict:
        raw = e.get("details")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except ValueError:
                return {}
        return raw or {}

    assert any(
        e["action"] == "update" and details_of(e).get("replaced") is False
        for e in entries
    )
    assert any(
        e["action"] == "update" and details_of(e).get("replaced") is True
        for e in entries
    )


async def test_upload_size_cap_enforced_midstream(client, monkeypatch):
    """The cap must reject while streaming (no full-body buffering) and must
    not leave partial files in UPLOAD_DIR."""
    from app.api.deps import upload_dir
    from app.core.config import settings as cfg

    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    await _mk_appt(client, token, pid)

    before = {p.name for p in upload_dir().iterdir()}
    monkeypatch.setattr(cfg, "max_upload_bytes", 1024)  # 1 KB cap
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("big.bin", io.BytesIO(b"x" * 4096), "application/octet-stream")},
        headers=auth(token),
    )
    assert r.status_code == 413, r.text
    assert {p.name for p in upload_dir().iterdir()} == before  # no partial file

    # within the (patched) cap everything still works
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("ok.bin", io.BytesIO(b"x" * 512), "application/octet-stream")},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["size_bytes"] == 512


async def test_upload_empty_rejected(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    await _mk_appt(client, token, pid)
    from app.api.deps import upload_dir

    before = {p.name for p in upload_dir().iterdir()}
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 422
    assert {p.name for p in upload_dir().iterdir()} == before


async def test_receptionist_role_gating(client):
    admin_token, _ = await login(client)
    await make_user(client, admin_token, "recep1", role="receptionist")
    await make_user(client, admin_token, "drhouse", role="doctor")
    recep, _ = await login(client, "recep1", "passw0rd123")
    doctor, _ = await login(client, "drhouse", "passw0rd123")

    pid = await _mk_patient(client, admin_token)
    appt = await _mk_appt(client, admin_token, pid)

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
    pid = await _mk_patient(client, token)
    appt = await _mk_appt(client, token, pid, at="2099-01-01T09:00:00+03:30")
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

    pid = await _mk_patient(client, admin)
    appt = await _mk_appt(client, admin, pid)

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
    pid = await _mk_patient(client, token)
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


async def test_stats_summary(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    await _mk_appt(client, token, pid, at="2026-09-10T09:00:00+03:30")
    appt2 = await _mk_appt(client, token, pid, at="2026-09-11T09:00:00+03:30")

    for appt, amount, pos in ((appt2, 500000, True), (appt2, 100000, False)):
        r = await client.post(
            f"/api/v1/appointments/{appt['id']}/transactions",
            json={"description": "visit", "amount": amount, "pos": pos},
            headers=auth(token),
        )
        assert r.status_code == 201

    r = await client.get(
        "/api/v1/stats/summary",
        params={"date_from": "2026-09-10", "date_to": "2026-09-11"},
        headers=auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["num_appointments"] == 2
    assert body["total_amount"] == 600000
    assert body["pos_amount"] == 500000
    assert body["cash_amount"] == 100000
    assert body["num_transactions"] == 2

    # CSV export
    r = await client.get(
        "/api/v1/stats/summary.csv",
        params={"date_from": "2026-09-10", "date_to": "2026-09-11"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "visit,1,500000" in r.text or "visit" in r.text

    # reversed dates → 422
    r = await client.get(
        "/api/v1/stats/summary",
        params={"date_from": "2026-09-11", "date_to": "2026-09-10"},
        headers=auth(token),
    )
    assert r.status_code == 422

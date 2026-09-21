"""Attachments: multipart upload, note-only rows, content attach/replace,
download, streaming size cap. Files belong to the PATIENT (since 1.3)."""

import io
import json

from tests.conftest import auth, login, make_user
from tests.factories import mk_appointment, mk_patient


def _pid(client, token):
    return mk_patient(client, token)


async def test_attachments_upload_download_edit(client):
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
    await mk_appointment(client, token, pid)

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
    pid = (await mk_patient(client, token))["id"]
    await mk_appointment(client, token, pid)

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
    pid = (await mk_patient(client, token))["id"]
    await mk_appointment(client, token, pid)

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
    pid = (await mk_patient(client, token))["id"]
    await mk_appointment(client, token, pid)

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
    pid = (await mk_patient(client, token))["id"]
    await mk_appointment(client, token, pid)
    from app.api.deps import upload_dir

    before = {p.name for p in upload_dir().iterdir()}
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 422
    assert {p.name for p in upload_dir().iterdir()} == before



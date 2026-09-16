"""Admin backup: tarball DB + uploads, job lifecycle, permissions."""

import io
import tarfile

from tests.conftest import auth, login, make_user


async def test_backup_full_flow(client):
    token, _ = await login(client)

    # seed: one patient + appointment + uploaded file + a note-only row
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": "1234567890",
            "first_name": "Parham",
            "last_name": "Testi",
            "year_of_birth": "1990",
            "gender": 0,
        },
        headers=auth(token),
    )
    pid = r.json()["id"]
    r = await client.post(
        f"/api/v1/patients/{pid}/appointments",
        json={"scheduled_at": "2026-09-10T10:30:00+03:30"},
        headers=auth(token),
    )
    appt_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/appointments/{appt_id}/files",
        data={"description": "lab"},
        files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201
    r = await client.post(
        f"/api/v1/appointments/{appt_id}/files/note",
        json={"description": "note-only"},
        headers=auth(token),
    )
    assert r.status_code == 201

    # initial status: idle
    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "idle"

    # start the job
    r = await client.post("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 202, r.text

    # poll until ready (the thread is fast on a test DB)
    status = "running"
    for _ in range(100):
        r = await client.get("/api/v1/admin/backup", headers=auth(token))
        status = r.json()["status"]
        if status != "running":
            break
    assert status == "ready", r.text
    assert r.json()["size_bytes"] > 0

    # download and inspect the tarball
    r = await client.get("/api/v1/admin/backup/download", headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/gzip")
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        names = tar.getnames()
        assert any(n == "manifest.json" for n in names)
        assert any(n == "db/clinic.sqlite3" for n in names)  # sqlite dev branch
        assert any(n.startswith("uploads/") for n in names)
        manifest = tar.extractfile("manifest.json")
        assert manifest is not None
        content = manifest.read().decode()
        assert "patients" in content

    # discard
    r = await client.delete("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 204
    r = await client.get("/api/v1/admin/backup/download", headers=auth(token))
    assert r.status_code == 409

    # audit trail recorded both actions
    r = await client.get(
        "/api/v1/admin/audit", params={"entity_type": "backup"}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 2


async def test_backup_receptionist_forbidden(client):
    admin, _ = await login(client)
    await make_user(client, admin, "recep1", role="receptionist")
    recep, _ = await login(client, "recep1", "passw0rd123")
    r = await client.get("/api/v1/admin/backup", headers=auth(recep))
    assert r.status_code == 403
    r = await client.post("/api/v1/admin/backup", headers=auth(recep))
    assert r.status_code == 403

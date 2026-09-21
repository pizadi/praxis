"""Admin backup: tarball DB + uploads, job lifecycle, permissions."""

import io
import json
import os
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


async def _wait_import_done(client, token: str) -> dict:
    for _ in range(100):
        r = await client.get("/api/v1/admin/backup/import", headers=auth(token))
        if r.status_code != 200:
            raise AssertionError(f"import status endpoint: {r.status_code} {r.text}")
        st = r.json()["status"]
        if st != "importing":
            return r.json()
    raise AssertionError("import did not finish")


async def test_import_round_trip(client):
    """Export → destroy the data → import → data restored (sqlite path)."""
    token, _ = await login(client)

    r = await client.post(
        "/api/v1/patients",
        json={"national_id": "1234567890", "first_name": "الف", "last_name": "ب",
              "year_of_birth": "1370", "gender": 0},
        headers=auth(token),
    )
    pid = r.json()["id"]
    r = await client.post(f"/api/v1/patients/{pid}/appointments",
                          json={"scheduled_at": "2026-09-10T10:30:00+03:30"},
                          headers=auth(token))
    appt = r.json()
    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/files",
        data={"description": "lab"},
        files={"file": ("x.txt", io.BytesIO(b"hello-backup"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201

    # export
    r = await client.post("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 202
    for _ in range(100):
        st = (await client.get("/api/v1/admin/backup", headers=auth(token))).json()["status"]
        if st == "ready":
            break
    tarball = (await client.get("/api/v1/admin/backup/download", headers=auth(token))).content
    await client.delete("/api/v1/admin/backup", headers=auth(token))

    # destroy: delete patient (subtree) → export's data is gone from live views
    r = await client.delete(f"/api/v1/patients/{pid}", headers=auth(token))
    assert r.status_code == 204
    r = await client.get(f"/api/v1/patients/{pid}", headers=auth(token))
    assert r.status_code == 404

    # import → everything back
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("backup.tar.gz", io.BytesIO(tarball), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done
    assert done["summary"]["tables"]["patients"] == 1

    r = await client.get(f"/api/v1/patients/{pid}", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["first_name"] == "الف"
    r = await client.get(f"/api/v1/appointments/{appt['id']}/files", headers=auth(token))
    assert r.status_code == 200
    assert r.json()[0]["description"] == "lab"
    # the restored attachment's file is on disk again (merge semantics)
    r = await client.get(f"/api/v1/appointments/files/{r.json()[0]['id']}/download",
                         headers=auth(token))
    assert r.status_code == 200 and r.content == b"hello-backup"


async def test_import_version_gates(client):
    token, _ = await login(client)

    # schema_version newer than supported → refuse (422)
    manifest = json.dumps({"schema_version": 99, "app_version": "9.0.0", "tables": {}})
    bad = io.BytesIO()
    with tarfile.open(fileobj=bad, mode="w:gz") as tar:
        data = manifest.encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", bad.getvalue(), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 422

    # producer app_version newer than the system → 409 unless forced
    manifest = json.dumps({
        "schema_version": 2, "app_version": "99.0.0",
        "tables": {}, "table_columns": {},
    })
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = manifest.encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", buf.getvalue(), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "newer_version"
    assert r.json()["error"]["details"]["tarball_app_version"] == "99.0.0"

    # forced → accepted (nothing to import; the empty manifest is harmless)
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", buf.getvalue(), "application/gzip")},
        data={"force": "true"},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done


async def test_import_rejects_garbage(client):
    token, _ = await login(client)
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", io.BytesIO(b"not a tarball"), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 422  # invalid_backup

    # zip-slip member → refused
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"x"
        info = tarfile.TarInfo(name="../evil.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", buf.getvalue(), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 422  # invalid_backup (unsafe member path)


async def test_import_partial_backup(client):
    """A backup carrying only some tables imports; tables absent from the
    dump keep their data. Regression: the PG path crashed with KeyError on
    the first missing db/<table>.copy member (getmember-vs-extractfile)."""
    import os
    import sqlite3
    import tempfile

    from app.db.session import engine

    token, _ = await login(client)
    is_pg = engine.dialect.name == "postgresql"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if is_pg:
            manifest = json.dumps({
                "schema_version": 2,
                "app_version": "1.2.0",
                "table_columns": {
                    "patients": [
                        "id", "first_name", "last_name",
                        "national_id", "year_of_birth", "gender",
                    ]
                },
            })
            data = manifest.encode()
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            row = b"1\tPartial\tBackup\t9999999999\t1380\t0\n"
            info = tarfile.TarInfo(name="db/patients.copy")
            info.size = len(row)
            tar.addfile(info, io.BytesIO(row))
        else:
            # SQLite path: a mini database holding only the patients table
            fd, mini = tempfile.mkstemp(suffix=".sqlite3")
            os.close(fd)
            con = sqlite3.connect(mini)
            con.execute(
                "CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name TEXT, "
                "last_name TEXT, national_id TEXT, year_of_birth TEXT, gender INTEGER)"
            )
            con.execute(
                "INSERT INTO patients VALUES (1, 'Partial', 'Backup', '9999999999', '1380', 0)"
            )
            con.commit()
            con.close()
            manifest = json.dumps({
                "schema_version": 2, "app_version": "1.2.0", "tables": {"patients": 1},
            })
            data = manifest.encode()
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            with open(mini, "rb") as f:
                db_bytes = f.read()
            os.unlink(mini)
            info = tarfile.TarInfo(name="db/clinic.sqlite3")
            info.size = len(db_bytes)
            tar.addfile(info, io.BytesIO(db_bytes))

    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("p.tar.gz", buf.getvalue(), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done

    r = await client.get("/api/v1/patients", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["first_name"] == "Partial"


async def test_import_hostile_table_names(client):
    """Table names from the imported SQLite file must stay contained (quoted
    identifiers are escaped), even when they try to break out."""
    import os
    import sqlite3
    import tempfile

    token, _ = await login(client)

    fd, mini = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    con = sqlite3.connect(mini)
    con.execute("CREATE TABLE patients (id INTEGER PRIMARY KEY, first_name TEXT)")
    con.execute("INSERT INTO patients VALUES (1, 'Hostile')")
    con.execute('CREATE TABLE "p"" union all select 1--" (id INTEGER)')
    con.execute('CREATE TABLE "users; DROP TABLE users--" (id INTEGER)')
    con.commit()
    con.close()

    manifest = json.dumps({
        "schema_version": 2, "app_version": "1.2.0", "tables": {"patients": 1},
    })
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = manifest.encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        with open(mini, "rb") as f:
            db_bytes = f.read()
        os.unlink(mini)
        info = tarfile.TarInfo(name="db/clinic.sqlite3")
        info.size = len(db_bytes)
        tar.addfile(info, io.BytesIO(db_bytes))

    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("h.tar.gz", buf.getvalue(), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done

    # users table untouched, hostile data imported as ordinary rows
    r = await client.get("/api/v1/users", headers=auth(token))
    assert r.status_code == 200
    r = await client.get("/api/v1/patients", headers=auth(token))
    assert r.json()["items"][0]["first_name"] == "Hostile"


async def test_import_older_schema_version(client):
    """A tarball from an earlier app version (fewer columns) imports via the
    manifest column lists; missing live columns are reported as skew."""
    import sqlite3
    import tempfile

    token, _ = await login(client)

    # build an "old version" database: patients without the newer columns
    fd, old_db = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    old = sqlite3.connect(old_db)
    old.execute(
        "CREATE TABLE patients (id INTEGER PRIMARY KEY, national_id TEXT, "
        "first_name TEXT, last_name TEXT)"
    )
    old.execute("INSERT INTO patients VALUES (1, '0011223344', 'قدیمی', 'نسخه')")
    old.commit()
    old.close()

    manifest = json.dumps({
        "schema_version": 2,
        "app_version": "1.0.0",
        "tables": {"patients": 1},
        "table_columns": {
            "patients": ["id", "national_id", "first_name", "last_name"],
        },
    })
    with open(old_db, "rb") as f:
        old_db_bytes = f.read()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in (
            ("db/clinic.sqlite3", old_db_bytes),
            ("manifest.json", manifest.encode()),
        ):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    os.unlink(old_db)

    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("old.tar.gz", buf.getvalue(), "application/gzip")},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done
    assert done["summary"]["tables"]["patients"] == 1
    skew = done["summary"]["skew"]["patients"]
    assert "phone_number" in skew["defaulted"]  # newer live column, filled by default

    # the imported row is really there (old values, empty new columns)
    r = await client.get("/api/v1/patients", params={"q": "0011223344"}, headers=auth(token))
    assert r.status_code == 200
    assert r.json()["total"] == 1
    item = r.json()["items"][0]
    assert item["first_name"] == "قدیمی"
    assert item["phone_number"] == ""


async def test_uploads_purge_removes_orphans_only(client):
    """The automatic sweeper removes unreferenced storage-named files older
    than the grace period; referenced / soft-deleted / foreign / young files
    stay; the pass is audited as the system user."""
    import os
    import time as time_mod

    from app.services.uploads_purge import purge_once

    token, _ = await login(client)
    r = await client.post(
        "/api/v1/patients",
        json={"national_id": "1234567890", "first_name": "الف", "last_name": "ب",
              "year_of_birth": "1370", "gender": 0},
        headers=auth(token),
    )
    pid = r.json()["id"]
    r = await client.post(f"/api/v1/patients/{pid}/appointments",
                          json={"scheduled_at": "2026-09-10T10:30:00+03:30"},
                          headers=auth(token))
    appt = r.json()
    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/files",
        files={"file": ("keep.txt", io.BytesIO(b"referenced"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201
    stored_ref = r.json()["stored_filename"]
    upload_dir = os.environ["UPLOAD_DIR"]

    # soft-deleted attachment's file is still owned → kept
    r = await client.post(
        f"/api/v1/appointments/{appt['id']}/files",
        files={"file": ("del.txt", io.BytesIO(b"deleted-owner"), "text/plain")},
        headers=auth(token),
    )
    stored_del = r.json()["stored_filename"]
    await client.delete(f"/api/v1/appointments/files/{r.json()['id']}", headers=auth(token))

    # orphans: old uuid-named files (purgeable) + a foreign file (kept)
    old_orphan = os.path.join(upload_dir, "a" * 32 + ".bin")
    young_orphan = os.path.join(upload_dir, "b" * 32 + ".bin")
    foreign = os.path.join(upload_dir, "readme-somebody-put-here.txt")
    for p in (old_orphan, young_orphan, foreign):
        with open(p, "wb") as f:
            f.write(b"orphan")
    old_ts = time_mod.time() - 25 * 3600  # older than the 24h grace period
    os.utime(old_orphan, (old_ts, old_ts))

    from app.db.session import SessionLocal
    async with SessionLocal() as session:
        s = await purge_once(session)
    assert s["removed"] == 1
    assert not os.path.exists(old_orphan)
    assert os.path.exists(young_orphan)  # within the grace period
    assert os.path.exists(foreign)  # not a storage name — never touched
    assert os.path.exists(os.path.join(upload_dir, stored_ref))
    assert os.path.exists(os.path.join(upload_dir, stored_del))

    # audited as system
    r = await client.get("/api/v1/admin/audit", params={"entity_type": "uploads_purge"},
                         headers=auth(token))
    assert r.status_code == 200
    entries = r.json()["items"]
    assert entries and entries[0]["username"] == "system"

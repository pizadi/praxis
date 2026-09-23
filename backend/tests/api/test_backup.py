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
    r.json()["id"]  # appointment row (no longer used for files since 1.3)
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        data={"description": "lab"},
        files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201
    r = await client.post(
        f"/api/v1/patients/{pid}/files/note",
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
    assert r.json()["sha256"]  # artifact checksum present
    assert r.json()["encrypted"] is False

    # download and inspect the tarball
    r = await client.get("/api/v1/admin/backup/download", headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/gzip")
    assert r.headers["x-checksum-sha256"] == (await client.get(
        "/api/v1/admin/backup", headers=auth(token)
    )).json()["sha256"]
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        names = tar.getnames()
        assert any(n == "manifest.json" for n in names)
        assert any(n == "db/clinic.sqlite3" for n in names)  # sqlite dev branch
        assert any(n.startswith("uploads/") for n in names)
        manifest = tar.extractfile("manifest.json")
        assert manifest is not None
        content = manifest.read().decode()
        assert "patients" in content
        # schema_version 4: member-level checksums
        m = json.loads(content)
        assert m["schema_version"] == 4
        assert "db/clinic.sqlite3" in m["member_sha256"]
        assert any(k.startswith("uploads/") for k in m["member_sha256"])

    # discard
    r = await client.delete("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 204
    r = await client.get("/api/v1/admin/backup/download", headers=auth(token))
    assert r.status_code == 409

    # audit trail recorded all three: start (create), completion (backup),
    # discard (delete)
    r = await client.get(
        "/api/v1/admin/audit", params={"entity_type": "backup"}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 3
    actions = {e["action"]: e for e in r.json()["items"]}
    assert "create" in actions and "delete" in actions
    # the completion row is written by the job thread as the system user
    completion = actions.get("backup")
    assert completion is not None
    assert completion["username"] == "system"


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
    r.json()  # appointment row (kept for realism)
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
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
    r = await client.get(f"/api/v1/patients/{pid}/files", headers=auth(token))
    assert r.status_code == 200
    assert r.json()[0]["description"] == "lab"
    # the restored attachment's file is on disk again (merge semantics)
    r = await client.get(f"/api/v1/files/{r.json()[0]['id']}/download",
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


async def test_import_ignores_attachment_upload_cap(client, monkeypatch):
    """Backup imports are exempt from MAX_UPLOAD_BYTES (the attachment cap):
    tarballs are admin-initiated and streamed to disk — nginx is the only
    layer that ever capped them (fixed in nginx.conf)."""
    from app.core.config import settings as cfg

    monkeypatch.setattr(cfg, "max_upload_bytes", 1024)  # 1 KB — absurdly low
    token, _ = await login(client)

    manifest = json.dumps({
        "schema_version": 2, "app_version": "1.0.0",
        "tables": {}, "table_columns": {},
    })
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = manifest.encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        pad = os.urandom(4096)  # incompressible — the stream exceeds the cap
        info = tarfile.TarInfo(name="uploads/pad.bin")
        info.size = len(pad)
        tar.addfile(info, io.BytesIO(pad))
    assert len(buf.getvalue()) > 1024  # sanity: the upload exceeds the cap

    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", buf.getvalue(), "application/gzip")},
        data={"force": "true"},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done

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
    """A pre-1.3 backup carrying only some tables imports; attachments'
    legacy appointment_id is remapped to the patient, the legacy rx text is
    re-derived into prescriptions, and tables absent from the dump keep
    their data. Regression: the PG path crashed with KeyError on the first
    missing db/<table>.copy member (getmember-vs-extractfile)."""
    import os
    import sqlite3
    import tempfile

    from app.db.session import engine

    token, _ = await login(client)

    is_pg = engine.dialect.name == "postgresql"

    pat_cols = ["id", "first_name", "last_name", "national_id", "year_of_birth", "gender"]
    appt_cols = ["id", "patient_id", "scheduled_at", "notes", "cm", "hx", "px", "rx"]
    # PRE-1.3 attachment shape: appointment_id (patient_id did not exist)
    att_cols = ["id", "appointment_id", "description", "notes", "stored_filename",
                "original_filename", "mime_type", "size_bytes", "missing_file"]

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:

        def add_bytes(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        if is_pg:
            manifest = json.dumps({
                "schema_version": 2,
                "app_version": "1.2.0",
                "table_columns": {
                    "patients": pat_cols,
                    "appointments": appt_cols,
                    "attachments": att_cols,
                },
            })
            add_bytes("manifest.json", manifest.encode())
            add_bytes(
                "db/patients.copy", b"1\tPartial\tBackup\t9999999999\t1380\t0\n"
            )
            add_bytes(
                "db/appointments.copy",
                b"201\t1\t2025-06-01 06:30:00+00\t\t\t\t\tasthma 2, rhinitis\n",
            )
            add_bytes(
                "db/attachments.copy",
                # note-only row (original_filename NULL) + missing-file row
                b"301\t201\tlab\t\t\\N\tx.pdf\t\\N\t\\N\ttrue\n"
                b"302\t201\tnote\tn\t\\N\t\\N\t\\N\t\\N\tfalse\n",
            )
        else:
            # SQLite path: a mini database with the PRE-1.3 schema
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
            con.execute(
                "CREATE TABLE appointments (id INTEGER PRIMARY KEY, patient_id INTEGER,"
                " scheduled_at TEXT, notes TEXT, cm TEXT, hx TEXT, px TEXT, rx TEXT)"
            )
            con.execute(
                "INSERT INTO appointments VALUES (201, 1, '2025-06-01 06:30:00',"
                " '', '', '', '', 'asthma 2, rhinitis')"
            )
            con.execute(
                "CREATE TABLE attachments (id INTEGER PRIMARY KEY, appointment_id INTEGER,"
                " description TEXT, notes TEXT, stored_filename TEXT, original_filename TEXT,"
                " mime_type TEXT, size_bytes INTEGER, missing_file INTEGER)"
            )
            con.execute(
                "INSERT INTO attachments VALUES (301, 201, 'lab', '', NULL, 'x.pdf', NULL, NULL, 1)"
            )
            con.execute(
                "INSERT INTO attachments VALUES (302, 201, 'note', 'n', NULL, NULL, NULL, NULL, 0)"
            )
            con.commit()
            con.close()
            manifest = json.dumps({
                "schema_version": 2, "app_version": "1.2.0",
                "tables": {"patients": 1, "appointments": 1, "attachments": 2},
            })
            add_bytes("manifest.json", manifest.encode())
            with open(mini, "rb") as f:
                db_bytes = f.read()
            os.unlink(mini)
            add_bytes("db/clinic.sqlite3", db_bytes)

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

    # attachments were remapped to the PATIENT (legacy appointment_id resolved)
    r = await client.get("/api/v1/patients/1/files", headers=auth(token))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2
    assert all(f["patient_id"] == 1 for f in r.json())

    # the legacy rx text was re-derived into a prescription (overflow notes —
    # a single-row corpus admits no dictionary items)
    r = await client.get("/api/v1/patients/1/prescriptions", headers=auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    rx = r.json()["items"][0]
    assert rx["source_appointment_id"] == 201
    # each parsed item preserved verbatim (overflow format: one per line)
    assert "asthma 2" in rx["notes"] and "rhinitis" in rx["notes"]
    assert rx["items"] == []


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
    r.json()  # appointment row (kept for realism)
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("keep.txt", io.BytesIO(b"referenced"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201
    stored_ref = r.json()["stored_filename"]
    upload_dir = os.environ["UPLOAD_DIR"]

    # soft-deleted attachment's file is still owned → kept
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("del.txt", io.BytesIO(b"deleted-owner"), "text/plain")},
        headers=auth(token),
    )
    stored_del = r.json()["stored_filename"]
    await client.delete(f"/api/v1/files/{r.json()['id']}", headers=auth(token))

    # orphans: old uuid-named files (purgeable) + a foreign file (kept)
    old_orphan = os.path.join(upload_dir, "a" * 32 + ".bin")
    young_orphan = os.path.join(upload_dir, "b" * 32 + ".bin")
    foreign = os.path.join(upload_dir, "readme-somebody-put-here.txt")
    for p in (old_orphan, young_orphan, foreign):
        with open(p, "wb") as f:
            f.write(b"orphan")
    old_ts = time_mod.time() - 25 * 3600  # older than the 24h grace period
    os.utime(old_orphan, (old_ts, old_ts))

    # the backup artifact lives in a HIDDEN dir on this volume — the purge
    # never descends into it (even an old, unreferenced-looking name)
    backup_art = os.path.join(upload_dir, ".backups", "clinic-backup.tar.gz")
    os.makedirs(os.path.dirname(backup_art), exist_ok=True)
    with open(backup_art, "wb") as f:
        f.write(b"tarball")
    os.utime(backup_art, (old_ts, old_ts))

    from app.db.session import SessionLocal
    async with SessionLocal() as session:
        s = await purge_once(session)
    assert s["removed"] == 1
    assert not os.path.exists(old_orphan)
    assert os.path.exists(young_orphan)  # within the grace period
    assert os.path.exists(foreign)  # not a storage name — never touched
    assert os.path.exists(backup_art)  # hidden dir — never swept
    assert os.path.exists(os.path.join(upload_dir, stored_ref))
    assert os.path.exists(os.path.join(upload_dir, stored_del))

    # audited as system
    r = await client.get("/api/v1/admin/audit", params={"entity_type": "uploads_purge"},
                         headers=auth(token))
    assert r.status_code == 200
    entries = r.json()["items"]
    assert entries and entries[0]["username"] == "system"


async def test_backup_staleness_warning(client, monkeypatch):
    """last_backup_at/staleness: never-backed-up → stale; a completed backup
    clears it; BACKUP_STALE_DAYS=0 disables (null)."""
    from app.core.config import settings as cfg

    token, _ = await login(client)

    # fresh test DB: no backup ever recorded → stale
    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.json()["backup_stale"] is True
    assert r.json()["last_backup_at"] is None
    assert r.json()["backup_stale_days"] == cfg.backup_stale_days

    # disabled → null (UI hides the banner)
    monkeypatch.setattr(cfg, "backup_stale_days", 0)
    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.json()["backup_stale"] is None
    monkeypatch.setattr(cfg, "backup_stale_days", 7)

    # run a backup → the completion record clears the staleness
    r = await client.post("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 202
    for _ in range(100):
        r = await client.get("/api/v1/admin/backup", headers=auth(token))
        if r.json()["status"] == "ready":
            break
    assert r.json()["backup_stale"] is False
    assert r.json()["last_backup_at"] is not None
    await client.delete("/api/v1/admin/backup", headers=auth(token))


async def test_backup_encryption_round_trip(client, monkeypatch):
    """With BACKUP_ENCRYPTION_KEY set: the artifact is AES-256-GCM encrypted
    (plaintext never left on disk), checksummed, and imports back after
    decryption — verifying the data + the checksum."""
    import hashlib

    from app.core.config import settings as cfg
    from app.services.backup_crypto import decrypt_file

    monkeypatch.setattr(cfg, "backup_encryption_key", "test-key-123")
    token, _ = await login(client)
    r = await client.post(
        "/api/v1/patients",
        json={"national_id": "1234567890", "first_name": "الف", "last_name": "ب",
              "year_of_birth": "1370", "gender": 0},
        headers=auth(token),
    )
    pid = r.json()["id"]
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("enc.txt", io.BytesIO(b"encrypted-content"), "text/plain")},
        headers=auth(token),
    )
    assert r.status_code == 201

    # build the encrypted artifact
    r = await client.post("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 202
    for _ in range(100):
        st = (await client.get("/api/v1/admin/backup", headers=auth(token))).json()
        if st["status"] == "ready":
            break
    assert st["encrypted"] is True
    sha = st["sha256"]
    assert sha

    r = await client.get("/api/v1/admin/backup/download", headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-checksum-sha256"] == sha
    assert r.headers["content-disposition"].endswith('.tar.gz.enc"')
    blob = r.content
    assert blob[:9] == b"PRAXISBK\x01"
    # the transferred bytes are exactly what the status checksummed
    assert hashlib.sha256(blob).hexdigest() == sha
    await client.delete("/api/v1/admin/backup", headers=auth(token))

    # decrypt out-of-band → a valid v4 tarball with member hashes
    with __import__("tempfile").TemporaryDirectory() as d:
        enc_path = os.path.join(d, "b.tar.gz.enc")
        plain_path = os.path.join(d, "b.tar.gz")
        with open(enc_path, "wb") as f:
            f.write(blob)
        decrypt_file(enc_path, plain_path, "test-key-123")
        with tarfile.open(plain_path, "r:gz") as tar:
            manifest = json.loads(tar.extractfile("manifest.json").read().decode())
            assert manifest["schema_version"] == 4
            assert "db/clinic.sqlite3" in manifest["member_sha256"]

    # destroy the data, then import the encrypted tarball WITH checksum check
    r = await client.delete(f"/api/v1/patients/{pid}", headers=auth(token))
    assert r.status_code == 204
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz.enc", io.BytesIO(blob), "application/octet-stream")},
        data={"expected_sha256": sha},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done
    r = await client.get(f"/api/v1/patients/{pid}", headers=auth(token))
    assert r.status_code == 200
    r = await client.get(f"/api/v1/patients/{pid}/files", headers=auth(token))
    assert r.status_code == 200
    fid = r.json()[0]["id"]
    r = await client.get(f"/api/v1/files/{fid}/download", headers=auth(token))
    assert r.status_code == 200 and r.content == b"encrypted-content"


async def test_import_checksum_mismatch(client, monkeypatch):
    from app.core.config import settings as cfg

    monkeypatch.setattr(cfg, "backup_encryption_key", "")
    token, _ = await login(client)
    r = await client.post("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 202
    for _ in range(100):
        st = (await client.get("/api/v1/admin/backup", headers=auth(token))).json()
        if st["status"] == "ready":
            break
    tarball = (await client.get("/api/v1/admin/backup/download", headers=auth(token))).content
    await client.delete("/api/v1/admin/backup", headers=auth(token))

    # wrong checksum → refuse BEFORE any import work
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", io.BytesIO(tarball), "application/gzip")},
        data={"expected_sha256": "0" * 64},
        headers=auth(token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "checksum_mismatch"

    # correct checksum → accepted
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", io.BytesIO(tarball), "application/gzip")},
        data={"expected_sha256": st["sha256"]},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done


async def test_import_encrypted_backup_requires_key(client, monkeypatch):
    """Encrypted artifact without a configured key (or with the wrong key)
    refuses loudly; unconfigured state never tries to decrypt plaintexts."""
    from app.core.config import settings as cfg

    token, _ = await login(client)
    monkeypatch.setattr(cfg, "backup_encryption_key", "right-key")
    r = await client.post("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 202
    for _ in range(100):
        st = (await client.get("/api/v1/admin/backup", headers=auth(token))).json()
        if st["status"] == "ready":
            break
    blob = (await client.get("/api/v1/admin/backup/download", headers=auth(token))).content
    await client.delete("/api/v1/admin/backup", headers=auth(token))

    # no key configured → refuse
    monkeypatch.setattr(cfg, "backup_encryption_key", "")
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz.enc", io.BytesIO(blob), "application/octet-stream")},
        headers=auth(token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_backup"
    assert "BACKUP_ENCRYPTION_KEY" in r.json()["error"]["message"]

    # wrong key → refuse
    monkeypatch.setattr(cfg, "backup_encryption_key", "wrong-key")
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz.enc", io.BytesIO(blob), "application/octet-stream")},
        headers=auth(token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_backup"

    # right key → accepted
    monkeypatch.setattr(cfg, "backup_encryption_key", "right-key")
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz.enc", io.BytesIO(blob), "application/octet-stream")},
        headers=auth(token),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token)
    assert done["status"] == "done", done


def test_verify_member_hashes_rejects_tampering(tmp_path):
    """schema_version ≥ 4 member checksums: a corrupted or missing member
    fails the pre-import verification loudly (before any DB work)."""
    import hashlib as hl

    from app.services.backup_import import _verify_member_hashes

    p = tmp_path / "b.tar.gz"
    member = b"1\tTamper\tProof\n"
    good = hl.sha256(member).hexdigest()
    with tarfile.open(p, "w:gz") as tar:
        manifest = json.dumps({
            "schema_version": 4, "tables": {},
            "member_sha256": {"db/clinic.sqlite3": good},
        }).encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))
        info = tarfile.TarInfo(name="db/clinic.sqlite3")
        info.size = len(member)
        tar.addfile(info, io.BytesIO(member))

    _verify_member_hashes(str(p), {"db/clinic.sqlite3": good})  # intact → passes

    # corrupt the member (rebuild the tarball with different content)
    with tarfile.open(p, "w:gz") as tar:
        manifest = json.dumps({
            "schema_version": 4, "tables": {},
            "member_sha256": {"db/clinic.sqlite3": good},
        }).encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))
        bad = member + b"extra row\n"
        info = tarfile.TarInfo(name="db/clinic.sqlite3")
        info.size = len(bad)
        tar.addfile(info, io.BytesIO(bad))
    try:
        _verify_member_hashes(str(p), {"db/clinic.sqlite3": good})
        raise AssertionError("tampered member not detected")
    except ValueError as e:
        assert "checksum mismatch" in str(e)

    # missing member
    try:
        _verify_member_hashes(str(p), {"db/nowhere.copy": good})
        raise AssertionError("missing member not detected")
    except ValueError as e:
        assert "missing hashed members" in str(e)


async def test_import_uploads_only_backup(client):
    """A partial dump with NO db members (uploads-only) imports the files
    without touching the DB. Regression: the PG path built an empty
    'TRUNCATE  CASCADE' statement and crashed."""
    manifest = json.dumps({
        "schema_version": 3, "app_version": "1.0.0", "tables": {},
    })
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest.encode()))
        data = b"uploads-only member"
        info = tarfile.TarInfo(name="uploads/orphan.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("u.tar.gz", buf.getvalue(), "application/gzip")},
        headers=auth(token_holder := (await login(client))[0]),
    )
    assert r.status_code == 202, r.text
    done = await _wait_import_done(client, token_holder)
    assert done["status"] == "done", done
    assert done["summary"]["uploads_moved"] == 1
    assert done["summary"]["tables"] == {}


# --- artifact persistence + native download token (1.3.1) -----------------


def _reset_backup_state() -> None:
    """Simulate a fresh volume: wipe the in-memory job state AND the persisted
    artifact dir (both survive across tests otherwise — module globals + the
    shared tmp UPLOAD_DIR)."""
    import shutil

    from app.api.v1 import backup as mod
    from app.core.config import settings as cfg

    with mod._status_lock:
        mod._file_path = None
        mod._status.update(
            status="idle",
            started_at=None,
            finished_at=None,
            error=None,
            sha256=None,
            encrypted=False,
        )
    d = cfg.backup_dir_resolved
    if d.is_dir():
        shutil.rmtree(d)


def _simulate_restart() -> None:
    """Wipe ONLY the in-memory state — what a container recreation loses. The
    persisted artifact dir stays."""
    from app.api.v1 import backup as mod

    with mod._status_lock:
        mod._file_path = None
        mod._status.update(
            status="idle",
            started_at=None,
            finished_at=None,
            error=None,
            sha256=None,
            encrypted=False,
        )


async def _wait_backup_ready(client, token: str) -> dict:
    r = await client.post("/api/v1/admin/backup", headers=auth(token))
    assert r.status_code == 202, r.text
    for _ in range(100):
        r = await client.get("/api/v1/admin/backup", headers=auth(token))
        if r.json()["status"] != "running":
            break
    assert r.json()["status"] == "ready", r.text
    return r.json()


async def test_backup_download_token_flow(client):
    """Native browser downloads cannot send an Authorization header — a
    short-lived signed token in the query string authorizes GET /download
    (the header path stays as the fallback)."""
    import hashlib
    import hmac
    import time

    from app.core.config import settings as cfg

    _reset_backup_state()
    admin, _ = await login(client)
    await make_user(client, admin, "recep2", role="receptionist")
    recep, _ = await login(client, "recep2", "passw0rd123")

    # issuing a token requires backup.manage
    r = await client.post("/api/v1/admin/backup/download-token", headers=auth(recep))
    assert r.status_code == 403
    r = await client.post("/api/v1/admin/backup/download-token", headers=auth(admin))
    assert r.status_code == 200
    dl_token = r.json()["token"]

    # valid token, but no ready backup → 409
    r = await client.get(f"/api/v1/admin/backup/download?token={dl_token}")
    assert r.status_code == 409

    st = await _wait_backup_ready(client, admin)

    # the token downloads WITHOUT any auth header; checksum header intact
    r = await client.get(f"/api/v1/admin/backup/download?token={dl_token}")
    assert r.status_code == 200
    assert r.headers["x-checksum-sha256"] == st["sha256"]

    # garbage → 401; expired (correct signature, past expiry) → 401
    r = await client.get("/api/v1/admin/backup/download?token=junk.not-a-mac")
    assert r.status_code == 401
    exp = int(time.time()) - 10
    mac = hmac.new(
        cfg.secret_key.encode(), f"backup-download:{exp}".encode(), hashlib.sha256
    ).hexdigest()
    r = await client.get(f"/api/v1/admin/backup/download?token={exp}.{mac}")
    assert r.status_code == 401

    await client.delete("/api/v1/admin/backup", headers=auth(admin))


async def test_backup_artifact_persists_across_restart(client):
    """The tarball lives in BACKUP_DIR (persistent volume) — after a restart
    the startup rediscovery finds it again: status ready, same checksum,
    downloadable with the checksum header."""
    from app.api.v1 import backup as mod
    from app.core.config import settings as cfg

    _reset_backup_state()
    token, _ = await login(client)
    st = await _wait_backup_ready(client, token)
    sha_before = st["sha256"]

    # the artifact is on the persistent path, exactly one file (no .part debris)
    art_dir = cfg.backup_dir_resolved
    assert art_dir.is_dir()
    assert [p.name for p in art_dir.iterdir()] == ["clinic-backup.tar.gz"]

    # container recreation: in-memory state gone, file remains
    _simulate_restart()
    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.json()["status"] == "idle"

    mod.rediscover_backup_artifact()

    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.json()["status"] == "ready"
    assert r.json()["sha256"] == sha_before
    assert r.json()["encrypted"] is False
    assert r.json()["size_bytes"] > 0
    # downloadable again, checksum header matches
    r = await client.get("/api/v1/admin/backup/download", headers=auth(token))
    assert r.status_code == 200
    assert r.headers["x-checksum-sha256"] == sha_before
    await client.delete("/api/v1/admin/backup", headers=auth(token))


async def test_backup_artifact_replaced_not_accumulated(client):
    """Each backup REPLACES the single artifact — the old per-run mkstemp
    leak (a full tarball left behind per run) stays fixed."""
    from app.core.config import settings as cfg

    _reset_backup_state()
    token, _ = await login(client)
    await _wait_backup_ready(client, token)
    await _wait_backup_ready(client, token)
    art_dir = cfg.backup_dir_resolved
    assert [p.name for p in art_dir.iterdir()] == ["clinic-backup.tar.gz"]
    await client.delete("/api/v1/admin/backup", headers=auth(token))


async def test_backup_part_file_never_discovered(client):
    """A killed run's .part file is debris: rediscovery ignores it and sweeps it."""
    import os

    from app.api.v1 import backup as mod
    from app.core.config import settings as cfg

    _reset_backup_state()
    token, _ = await login(client)
    art_dir = cfg.backup_dir_resolved
    art_dir.mkdir(parents=True, exist_ok=True)
    part = art_dir / "clinic-backup-abcd.tar.gz.part"
    with open(part, "wb") as f:
        f.write(b"half-written")
    mod.rediscover_backup_artifact()
    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.json()["status"] == "idle"
    assert not os.path.exists(part)  # swept as debris

    # a real artifact alongside it IS found after a restart
    st = await _wait_backup_ready(client, token)
    _simulate_restart()
    mod.rediscover_backup_artifact()
    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.json()["status"] == "ready"
    assert r.json()["sha256"] == st["sha256"]
    await client.delete("/api/v1/admin/backup", headers=auth(token))


async def test_backup_encrypted_artifact_rediscovered(client, monkeypatch):
    """Encrypted artifact: rediscovery flips encrypted=True (magic sniff) and
    the download keeps the .enc name / octet-stream type."""
    from app.api.v1 import backup as mod
    from app.core.config import settings as cfg

    _reset_backup_state()
    monkeypatch.setattr(cfg, "backup_encryption_key", "rediscover-key")
    token, _ = await login(client)
    st = await _wait_backup_ready(client, token)
    assert st["encrypted"] is True

    _simulate_restart()
    mod.rediscover_backup_artifact()

    r = await client.get("/api/v1/admin/backup", headers=auth(token))
    assert r.json()["status"] == "ready"
    assert r.json()["encrypted"] is True
    assert r.json()["sha256"] == st["sha256"]
    r = await client.get("/api/v1/admin/backup/download", headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].endswith('.tar.gz.enc"')
    await client.delete("/api/v1/admin/backup", headers=auth(token))

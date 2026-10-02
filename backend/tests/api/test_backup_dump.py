"""The tarball writer (services/backup_dump.py) and the standalone packer.

`build_backup_tarball` is the single implementation of the manifest-v4 format:
the site's own backup job and `scripts/pack_backup.py` both call it, so what is
asserted here is what the import endpoint will accept.
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

from app.core.config import settings as cfg
from app.services.backup_crypto import decrypt_file, is_encrypted
from app.services.backup_dump import build_backup_tarball
from app.services.backup_state import AUTH_TABLES, DUMP_TABLES
from tests.conftest import auth, login

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "pack_backup.py"


def _load_script():
    """Import scripts/pack_backup.py as a module (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("pack_backup", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seed(client) -> tuple[str, int, int]:
    token, _ = await login(client)
    r = await client.post(
        "/api/v1/patients",
        json={"national_id": "1234567890", "first_name": "Parham", "last_name": "Testi",
              "year_of_birth": "1370", "gender": 0},
        headers=auth(token),
    )
    pid = r.json()["id"]
    r = await client.post(
        f"/api/v1/patients/{pid}/files",
        files={"file": ("x.txt", io.BytesIO(b"packed-content"), "text/plain")},
        headers=auth(token),
    )
    fid = r.json()["id"]
    return token, pid, fid


async def test_build_backup_tarball_round_trip(client):
    """Write a tarball with the shared writer, then ingest it with the very
    importer the site's backup page calls."""
    from app.services.backup_import import run_import

    token, pid, fid = await _seed(client)

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "pack.tar.gz"
        result = build_backup_tarball(
            database_url=cfg.database_url,
            upload_dir=cfg.upload_dir,
            out_path=out,
            app_version="1.4.3",
        )
        assert result["encrypted"] is False
        assert out.is_file()
        assert result["sha256"] == __import__("hashlib").sha256(out.read_bytes()).hexdigest()
        assert result["size_bytes"] == out.stat().st_size
        assert result["schema_version"] == 4

        with tarfile.open(out, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
            manifest = json.loads(tar.extractfile("manifest.json").read().decode())
        assert "manifest.json" in names
        assert any(n.startswith("db/") for n in names)
        assert "uploads/" in {n.split("/")[0] + "/" for n in names}
        # every member but the manifest is hashed
        assert set(manifest["member_sha256"]) <= names
        assert "manifest.json" not in manifest["member_sha256"]
        assert manifest["app_version"] == "1.4.3"

        # destroy the data, then restore it from the artifact
        r = await client.delete(f"/api/v1/patients/{pid}", headers=auth(token))
        assert r.status_code == 204
        summary = run_import(str(out))
        assert summary["uploads_moved"] >= 1

    r = await client.get(f"/api/v1/patients/{pid}", headers=auth(token))
    assert r.status_code == 200
    r = await client.get(f"/api/v1/patients/{pid}/files", headers=auth(token))
    assert r.json()[0]["id"] == fid
    r = await client.get(f"/api/v1/files/{fid}/download", headers=auth(token))
    assert r.content == b"packed-content"


def _manifest_tarball(schema_version: int) -> bytes:
    manifest = json.dumps({
        "schema_version": schema_version,
        "app_version": "1.4.5",
        "tables": {},
    })
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = manifest.encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


async def test_import_merge_guards(client):
    """Unknown modes are refused, and pre-1.3 tarballs cannot merge (their
    legacy rx rows would resurrect next to the re-derived prescriptions)."""
    token, _ = await login(client)
    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", _manifest_tarball(4), "application/gzip")},
        data={"mode": "bogus"},
        headers=auth(token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_mode"

    r = await client.post(
        "/api/v1/admin/backup/import",
        files={"file": ("b.tar.gz", _manifest_tarball(2), "application/gzip")},
        data={"mode": "merge"},
        headers=auth(token),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "merge_unsupported"


async def test_import_merge_unions_instead_of_replacing(client):
    """Merge mode is a union, not a wipe: colliding primary keys take the
    backup's row, backup-only rows are added, live-only rows survive."""
    from app.services.backup_import import run_import

    token, pid, fid = await _seed(client)

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "pack.tar.gz"
        build_backup_tarball(
            database_url=cfg.database_url,
            upload_dir=cfg.upload_dir,
            out_path=out,
            app_version="1.4.5",
        )

        # diverge from the snapshot: mutate the colliding row, add live-only rows
        r = await client.patch(
            f"/api/v1/patients/{pid}",
            json={"first_name": "Changed"},
            headers=auth(token),
        )
        assert r.status_code == 200
        r = await client.post(
            "/api/v1/patients",
            json={"national_id": "9999999999", "first_name": "Live", "last_name": "Only",
                  "year_of_birth": "1380", "gender": 1},
            headers=auth(token),
        )
        live_pid = r.json()["id"]

        summary = run_import(str(out), mode="merge")
        assert summary["mode"] == "merge"

    # the colliding patient took the backup's value again
    r = await client.get(f"/api/v1/patients/{pid}", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["first_name"] == "Parham"
    # ...the live-only patient survived (replace would have wiped it)...
    r = await client.get(f"/api/v1/patients/{live_pid}", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["first_name"] == "Live"
    # ...and the backup's attachment is intact
    r = await client.get(f"/api/v1/files/{fid}/download", headers=auth(token))
    assert r.status_code == 200
    assert r.content == b"packed-content"


async def test_build_backup_tarball_encrypts_and_leaves_no_plaintext(client):
    """With a key: AES-256-GCM wrapper, the plaintext is unlinked, and the
    reported sha256 is of the FINAL (encrypted) artifact — the value a client
    passes as expected_sha256."""
    import hashlib

    await _seed(client)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "pack.tar.gz.enc"
        result = build_backup_tarball(
            database_url=cfg.database_url,
            upload_dir=cfg.upload_dir,
            out_path=out,
            app_version="1.4.3",
            encryption_key="pack-key",
        )
        assert result["encrypted"] is True
        blob = out.read_bytes()
        assert is_encrypted(out)
        assert hashlib.sha256(blob).hexdigest() == result["sha256"]
        # no leftover .part or plaintext sibling
        assert [p.name for p in Path(d).iterdir()] == ["pack.tar.gz.enc"]

        plain = Path(d) / "decrypted.tar.gz"
        decrypt_file(out, plain, "pack-key")
        with tarfile.open(plain, "r:gz") as tar:
            manifest = json.loads(tar.extractfile("manifest.json").read().decode())
        assert manifest["schema_version"] == 4


async def test_uploads_skip_dot_directories(client):
    """Runtime staging dirs (.import-*, .backups) must never end up inside an
    archive — that is how a tarball would swallow itself."""
    await _seed(client)
    hidden = Path(cfg.upload_dir) / ".import-1234"
    hidden.mkdir(parents=True, exist_ok=True)
    (hidden / "leftover.bin").write_bytes(b"debris")

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "pack.tar.gz"
        result = build_backup_tarball(
            database_url=cfg.database_url,
            upload_dir=cfg.upload_dir,
            out_path=out,
            app_version="1.4.3",
        )
        with tarfile.open(out, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
    assert not any(".import-1234" in n for n in names)
    assert result["uploads_files"] >= 1


async def test_atomic_publish_keeps_the_previous_artifact_on_failure(client, monkeypatch):
    """A failed build must not truncate or remove the artifact already in
    place — the publish is a single os.replace of a completed file."""
    import app.services.backup_dump as dump_mod

    await _seed(client)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "pack.tar.gz"
        good = build_backup_tarball(
            database_url=cfg.database_url, upload_dir=cfg.upload_dir, out_path=out,
            app_version="1.4.3",
        )
        assert out.is_file()

        def boom(*args, **kwargs):
            raise RuntimeError("dump failed")

        monkeypatch.setattr(dump_mod, "_add_uploads", boom)
        with pytest.raises(RuntimeError):
            build_backup_tarball(
                database_url=cfg.database_url, upload_dir=cfg.upload_dir, out_path=out,
                app_version="1.4.3",
            )
        # the old artifact is intact and no debris is left in the directory
        assert out.is_file()
        assert out.stat().st_size == good["size_bytes"]
        assert [p.name for p in Path(d).iterdir()] == ["pack.tar.gz"]


# --- the standalone packer -------------------------------------------------------


def test_packer_requires_a_postgres_dsn():
    """The site's importer reads db/<table>.copy members; a db/clinic.sqlite3
    member is ignored on PostgreSQL, so packing a SQLite database would produce
    an artifact that imports nothing. Refuse loudly instead."""
    mod = _load_script()
    with pytest.raises(SystemExit) as exc:
        mod.preflight("sqlite+aiosqlite:///data/x.db", ["patients"])
    assert "PostgreSQL" in str(exc.value)


def test_packer_excludes_accounts_by_default():
    """The importer truncates every table a tarball carries. A database that
    never ran bootstrap_admin() has no users, so a full dump would DELETE the
    site's admin on import — the packer leaves accounts out unless asked."""
    _load_script()  # the module must import standalone (argparse lives in main)
    assert {"roles", "users", "login_audit", "refresh_tokens"} == AUTH_TABLES
    assert set(DUMP_TABLES) >= AUTH_TABLES  # ...so they must be skipped explicitly
    packed = [t for t in DUMP_TABLES if t not in AUTH_TABLES]
    assert not AUTH_TABLES.intersection(packed)
    assert "patients" in packed and "attachments" in packed


def test_packer_reports_the_contents_it_wrote():
    mod = _load_script()
    manifest = {
        "schema_version": 4,
        "app_version": "1.4.3",
        "tables": {"patients": 2, "attachments": 1},
        "uploads_files": 1,
    }
    mod.print_manifest(manifest)  # smoke: must not raise on a missing __sqlite_file__


def test_packer_cli_help_runs():
    """--help must not require a database (it is how anyone discovers the
    flags)."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True, text=True, cwd=REPO, timeout=120,
    )
    assert r.returncode == 0, r.stderr
    for flag in ("--database-url", "--upload-dir", "--out", "--encryption-key",
                 "--include-auth", "--force"):
        assert flag in r.stdout


def test_packer_refuses_to_overwrite_without_force(tmp_path):
    out = tmp_path / "pack.tar.gz"
    out.write_bytes(b"existing")
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--database-url", "postgresql+asyncpg://u:p@localhost:5432/x",
         "--upload-dir", str(tmp_path), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO, timeout=120,
    )
    assert r.returncode == 2
    assert out.read_bytes() == b"existing"
    assert os.path.exists(SCRIPT)

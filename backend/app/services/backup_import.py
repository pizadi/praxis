"""Restore DB + uploads from a backup tarball (upload-side of backup.py).

Tarball layout (schema_version 4):
    manifest.json          — {"schema_version": 4, "app_version": "1.4.0",
                              "table_columns": {table: [cols...]},
                              "member_sha256": {member: hex}, ...}
    db/<table>.copy        — PostgreSQL COPY data (one file per table), or
    db/clinic.sqlite3      — SQLite (dev): the raw database file
    uploads/<name>         — the uploaded patient files (flat or nested)

The whole ARTIFACT may additionally be encrypted (PRAXISBK magic, AES-256-
GCM, see backup_crypto.py) — decrypted before the tarball is seen here.

Import semantics:
- PostgreSQL: ONE transaction — TRUNCATE every domain table, then COPY each
  dumped table (manifest column order; dump columns missing from the live
  schema are dropped, schema columns missing from the dump take defaults).
  Any error → full ROLLBACK, the running system is untouched. Serial
  sequences are re-synced from max(id) afterwards (still in-transaction).
- SQLite (dev/tests): ATTACH the archived database and copy table-by-table
  in one transaction; column lists come from the attached file itself, so
  even schema-less legacy manifests work.
- uploads/: extracted into UPLOAD_DIR/.import-<ts>/ staging and moved into
  place after the DB commit (merge — files not in the tarball stay; the
  periodic uploads-purge reclaims them after the grace period).

Version rules (enforced in the API layer):
- schema_version newer than SUPPORTED_SCHEMA_VERSION → refuse (422).
- producer app_version newer than the running app → refuse (409) unless
  the user explicitly forces the import; even forced, an unresolvable
  error rolls everything back.
- schema_version ≤ 2 (pre-1.3): attachments hung off APPOINTMENTS — the
  importer remaps dump's attachments.appointment_id → patient_id through
  the dumped appointments table (FK integrity inside one dump makes this
  total; a dangling reference violates NOT NULL/FK and rolls back loudly).
"""

import contextlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
import uuid
from pathlib import Path

from app.core.config import settings
from app.services.backup_state import DUMP_TABLES

SUPPORTED_SCHEMA_VERSION = 4

# hard caps for hostile/buggy tarballs (admins upload, but still)
MAX_MEMBER_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB per member
MAX_MEMBERS = 200_000

_status_lock = threading.Lock()
_status: dict = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "summary": None,
}


def import_status() -> dict:
    with _status_lock:
        return dict(_status)


def import_status_update(status: str, summary: dict | None, error: str | None) -> None:
    with _status_lock:
        _status.update(
            status=status,
            finished_at=None if status == "importing" else _status.get("finished_at"),
            error=error,
            summary=summary,
        )


def read_manifest(path: str) -> dict:
    """Validate the tarball's structure and return its manifest.

    Only manifest.json / db/... / uploads/... members are allowed; links and
    device nodes are rejected (zip-slip hardening)."""
    allowed = ("manifest.json", "db/", "uploads/")
    manifest: dict | None = None
    n = 0
    with tarfile.open(path, "r:gz") as tar:
        for m in tar:
            n += 1
            if n > MAX_MEMBERS:
                raise ValueError("too many members")
            if m.issym() or m.islnk() or m.isdev():
                raise ValueError(f"unsupported member type: {m.name}")
            name = m.name.lstrip("./")
            if name not in allowed and not name.startswith(("db/", "uploads/")):
                raise ValueError(f"unexpected member in tarball: {m.name}")
            if ".." in m.name.split("/") or m.name.startswith("/"):
                raise ValueError(f"unsafe member path: {m.name}")
            if m.size > MAX_MEMBER_BYTES:
                raise ValueError(f"member too large: {m.name}")
            if name == "manifest.json":
                f = tar.extractfile(m)
                if f is None:
                    raise ValueError("manifest.json is not a regular file")
                manifest = json.loads(f.read().decode("utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("manifest.json is not an object")
    if manifest is None:
        raise ValueError("manifest.json missing")
    if "tables" not in manifest:
        raise ValueError("manifest.json has no tables entry")
    return manifest


def _verify_member_hashes(tar_path: str, expected: dict[str, str]) -> None:
    """Fail fast on any corrupted/tampered member BEFORE the destructive
    DB transaction (schema_version ≥ 4 manifests carry member_sha256).

    One extra streaming pass over the archive, but an import is rare and
    the loud-early failure beats a mid-COPY rollback.
    """
    import hashlib

    if not expected:
        return
    remaining = {name.lstrip("./"): hexdigest for name, hexdigest in expected.items()}
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in tar:
            name = m.name.lstrip("./")
            if name not in remaining or m.isdir():
                continue
            want = remaining.pop(name)
            f = tar.extractfile(m)
            if f is None:
                raise ValueError(f"member is not a regular file: {m.name}")
            h = hashlib.sha256()
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
            actual = h.hexdigest()
            if actual != want:
                raise ValueError(
                    f"checksum mismatch for {m.name} — the tarball is corrupted "
                    f"(expected {want[:12]}…, got {actual[:12]}…)"
                )
            if not remaining:
                return
    if remaining:
        raise ValueError(f"tarball is missing hashed members: {sorted(remaining)}")


def run_import(tar_path: str) -> dict:
    """Execute the import; raises on any unresolvable error (the caller's
    DB transaction/lock discipline makes failures non-destructive)."""
    manifest = read_manifest(tar_path)
    _verify_member_hashes(tar_path, manifest.get("member_sha256") or {})

    summary = (
        _import_postgres(tar_path)
        if settings.database_url.startswith("postgres")
        else _import_sqlite(tar_path)
    )

    # uploads: staging inside UPLOAD_DIR (same volume/filesystem), moved
    # into place after the DB transaction has committed
    moved = _import_uploads(tar_path)
    summary["uploads_moved"] = moved
    return summary


# --- PostgreSQL ---------------------------------------------------------------------


def _pg_fallback_expr(data_type: str) -> str:
    """SQL expression filling a column the dump doesn't have.

    NOT NULL columns added after the dump need a value: text-ish → '',
    numeric/bool → 0; everything else falls to NULL (and a NOT NULL
    constraint there is treated as unresolvable → the import rolls back).
    """
    t = data_type.lower()
    if "char" in t or "text" in t:
        return "''"
    if any(k in t for k in ("int", "real", "floa", "doubl", "numeri", "decim", "bool")):
        return "0"
    return "NULL"


def _import_postgres(tar_path: str) -> dict:
    import psycopg2

    from app.services.backup_state import psycopg2_url

    dumped: dict[str, list[str]] = {}
    schema_version = 1
    with tarfile.open(tar_path, "r:gz") as tar:
        m = tar.getmember("manifest.json")
        if m is not None:
            f = tar.extractfile(m)
            if f is None:  # pragma: no cover — manifest is a regular file here
                raise RuntimeError("manifest.json is not a regular file")
            manifest = json.loads(f.read().decode("utf-8"))
            schema_version = manifest.get("schema_version", 1)
            dumped = manifest.get("table_columns", {}) or {}

        conn = psycopg2.connect(psycopg2_url())
        try:
            with conn.cursor() as cur:
                # one transaction around everything destructive. psycopg2
                # auto-sends BEGIN before the first statement — an explicit
                # BEGIN here would be a SECOND one ("there is already a
                # transaction in progress" on the server); SET TRANSACTION
                # as the first statement applies to that same transaction.
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                live_cols: dict[str, list[str]] = {}
                live_types: dict[str, dict[str, str]] = {}
                existing: set[str] = set()
                for t in DUMP_TABLES:
                    cur.execute(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = %s "
                        "ORDER BY ordinal_position",
                        (t,),
                    )
                    pairs = cur.fetchall()
                    cols: list[str] | None = [r[0] for r in pairs]
                    if cols:
                        live_cols[t] = cols
                        live_types[t] = {r[0]: r[1] for r in pairs}
                        existing.add(t)

                # destructive part starts here; any error → ROLLBACK below.
                # only tables the dump actually carries are replaced — tables
                # absent from an older dump keep their current data (an
                # uploads-only dump has no db members at all: nothing to
                # truncate — an empty TRUNCATE list is a syntax error)
                dumped_tables = {
                    m.name.lstrip("./")[len("db/") : -len(".copy")]
                    for m in tar
                    if m.name.lstrip("./").startswith("db/")
                    and m.name.lstrip("./").endswith(".copy")
                }
                to_replace = existing & dumped_tables
                if to_replace:
                    cur.execute(
                        f'TRUNCATE {", ".join(to_replace)} CASCADE'  # noqa: S608
                    )

                loaded: dict[str, int] = {}
                skew: dict[str, dict] = {}
                for t in DUMP_TABLES:
                    if t not in dumped_tables:
                        continue  # table absent from this (older) dump
                    member = tar.extractfile(f"db/{t}.copy")
                    if member is None:
                        continue
                    live = live_cols.get(t, [])
                    if schema_version >= 2 and t in dumped:
                        dump_cols = dumped[t]
                        cols = [c for c in dump_cols if c in live]
                        dropped = [c for c in dump_cols if c not in live]
                        defaulted = [c for c in live if c not in dump_cols]
                        if dropped or defaulted:
                            skew[t] = {"dropped": dropped, "defaulted": defaulted}
                    elif schema_version == 1 and t not in dumped:
                        # legacy tarball without column lists: only safe when the
                        # column count still matches the live schema
                        first = member.read(1)
                        member.seek(0)
                        if first == b"":
                            loaded[t] = 0
                            continue
                        ncols = member.readline().count(b"\t")
                        member.seek(0)
                        if ncols != len(live):
                            raise RuntimeError(
                                f"legacy backup (schema_version 1) table '{t}' has {ncols} "
                                f"columns but the live schema has {len(live)} — "
                                "re-export the backup with a compatible version"
                            )
                        cols = live  # full-row COPY
                    else:
                        cols = live_cols.get(t)

                    # pre-1.3 dump: attachments.appointment_id → patient_id via
                    # the appointments rows restored earlier in this transaction.
                    # A dangling appointment id maps to NULL → NOT NULL violation
                    # → loud rollback (FK integrity of one dump makes this
                    # impossible for a consistent backup).
                    remap_appointment = (
                        t == "attachments"
                        and schema_version <= 2
                        and "appointment_id" in (dumped.get(t) or [])
                        and "patient_id" in live
                        and "patient_id" not in (dumped.get(t) or [])
                    )

                    if remap_appointment:
                        dump_cols = dumped[t]
                        cols = [c for c in dump_cols if c in live and c != "appointment_id"]
                        tmp = f"_imp_{t}"
                        cur.execute(
                            f'CREATE TEMP TABLE "{tmp}" AS '  # noqa: S608
                            f'SELECT * FROM "{t}" WITH NO DATA'
                        )
                        # the stage table needs the dump-only column for the mapping
                        cur.execute(
                            f'ALTER TABLE "{tmp}" ADD COLUMN "appointment_id" integer'  # noqa: S608
                        )
                        stage_cols = ", ".join(f'"{c}"' for c in dump_cols)
                        cur.copy_expert(  # noqa: S608
                            f'COPY "{tmp}" ({stage_cols}) FROM STDIN', member
                        )
                        defaulted = [c for c in live if c not in cols]
                        target_cols = [c for c in cols if c != "patient_id"] + defaulted
                        target_sql = ", ".join(f'"{c}"' for c in target_cols)
                        select_exprs = [f'"{c}"' for c in cols if c != "patient_id"] + [
                            (
                                # NULL for a dangling appointment_id → NOT NULL
                                # violation → the whole import rolls back (loud)
                                "(SELECT a.patient_id FROM appointments a"
                                f' WHERE a.id = "{tmp}"."appointment_id")'
                                if c == "patient_id"
                                else _pg_fallback_expr(live_types.get(t, {}).get(c, ""))
                            )
                            for c in defaulted
                        ]
                        select_sql = ", ".join(select_exprs)
                        cur.execute(
                            f'INSERT INTO "{t}" ({target_sql}) '  # noqa: S608
                            f'SELECT {select_sql} FROM "{tmp}"'
                        )
                        cur.execute(f'DROP TABLE "{tmp}"')  # noqa: S608
                        loaded[t] = -1  # filled with real counts below
                        continue

                    if cols and len(cols) < len(live):
                        # the dump lacks columns of the live table: stage into a
                        # constraint-free temp table, then INSERT with type-aware
                        # fallbacks for the columns the dump doesn't carry
                        tmp = f"_imp_{t}"
                        cur.execute(
                            f'CREATE TEMP TABLE "{tmp}" AS '  # noqa: S608
                            f'SELECT * FROM "{t}" WITH NO DATA'
                        )
                        col_sql = f" ({', '.join(cols)})"
                        cur.copy_expert(f'COPY "{tmp}"{col_sql} FROM STDIN', member)  # noqa: S608
                        have_default = set()
                        for c in [c for c in live if c not in cols]:
                            cur.execute(
                                "SELECT column_default FROM information_schema.columns "
                                "WHERE table_schema = 'public' AND table_name = %s "
                                "AND column_name = %s",
                                (t, c),
                            )
                            row = cur.fetchone()
                            if row and row[0] is not None:
                                have_default.add(c)
                        fill = [c for c in live if c not in cols and c not in have_default]
                        target_cols = cols + fill
                        select_exprs = [f'"{c}"' for c in cols] + [
                            _pg_fallback_expr(live_types.get(t, {}).get(c, "")) for c in fill
                        ]
                        cur.execute(
                            f'INSERT INTO "{t}" ({", ".join(target_cols)}) '  # noqa: S608
                            f"SELECT {', '.join(select_exprs)} FROM \"{tmp}\""
                        )
                        cur.execute(f'DROP TABLE "{tmp}"')  # noqa: S608
                    else:
                        col_sql = f" ({', '.join(cols)})" if cols else ""
                        cur.copy_expert(f'COPY "{t}"{col_sql} FROM STDIN', member)  # noqa: S608
                    loaded[t] = -1  # filled with real counts below

                # resync serial sequences so future inserts don't collide
                for t in DUMP_TABLES:
                    if t not in loaded or "id" not in live_cols.get(t, []):
                        continue
                    cur.execute(
                        "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                        "COALESCE((SELECT MAX(id) FROM " + t + "), 1), true)",  # noqa: S608
                        (t,),
                    )
                    cur.execute(f'SELECT COUNT(*) FROM "{t}"')  # noqa: S608
                    loaded[t] = int(cur.fetchone()[0])

                # importing a pre-1.3 backup: the TRUNCATE ... CASCADE wiped
                # prescriptions (FK dependents of patients) that the old dump
                # cannot restore — re-derive them from the restored rx text
                # (same frozen parser as the 1.3 migration; same transaction)
                if schema_version <= 2 and "prescriptions" in live_cols:
                    rederived = _rederive_prescriptions_from_rx(cur)
                    if any(rederived):
                        summary_rx = {"prescriptions": rederived[0],
                                      "prescription_items": rederived[1],
                                      "prescription_item_links": rederived[2]}
                        for tbl, n in summary_rx.items():
                            loaded[tbl] = loaded.get(tbl, 0) + n
                        skew["_rederived_from_rx"] = summary_rx
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return {"tables": loaded, "schema_version": schema_version, "skew": skew}


def _rederive_prescriptions_from_rx(cur) -> tuple[int, int, int]:
    """Rebuild prescriptions/prescription_item_links from appointments.rx.

    Used after importing a pre-1.3 (schema_version ≤ 2) PostgreSQL backup:
    the dump carries no prescription tables, and TRUNCATE CASCADE on
    patients/appointments wiped whatever existed. Deterministic (same
    frozen parser as the 1.3 Alembic migration) and idempotent
    (source_appointment_id skips already-derived rows). Returns
    (prescriptions, items, links) created.
    """
    from app.services.rx_migration import (
        RX_MIN_FREQUENCY,
        normalize_item_name,
        overflow_notes,
        plan_rx_migration,
    )

    cur.execute(
        "SELECT id, patient_id, scheduled_at, rx FROM appointments "
        "WHERE rx IS NOT NULL AND rx <> ''"
    )
    rows = cur.fetchall()
    if not rows:
        return (0, 0, 0)
    planned, dictionary = plan_rx_migration(
        [(int(r[0]), int(r[1]), r[2], r[3]) for r in rows],
        min_frequency=RX_MIN_FREQUENCY,
    )

    # dictionary: upsert by normalized name (existing items may have
    # survived the truncate — prescription_items has no patient FK)
    cur.execute("SELECT id, name FROM prescription_items")
    item_id_by_key: dict[str, int] = {
        normalize_item_name(str(r[1])): int(r[0]) for r in cur.fetchall()
    }
    n_items = 0
    for key, display in sorted(dictionary.items()):
        if key in item_id_by_key:
            continue
        cur.execute(
            "INSERT INTO prescription_items (name) VALUES (%(name)s) RETURNING id",
            {"name": display[:128]},
        )
        item_id_by_key[key] = int(cur.fetchone()[0])
        n_items += 1

    cur.execute(
        "SELECT DISTINCT source_appointment_id FROM prescriptions "
        "WHERE source_appointment_id IS NOT NULL"
    )
    done = {int(r[0]) for r in cur.fetchall()}

    n_rx = 0
    n_links = 0
    rx_id_by_appt: dict[int, int] = {}
    for p in planned:
        if p.appointment_id in done:
            continue
        cur.execute(
            "INSERT INTO prescriptions (patient_id, prescribed_at, notes,"
            " source_appointment_id) VALUES (%(patient_id)s, %(prescribed_at)s,"
            " %(notes)s, %(source_appointment_id)s) RETURNING id",
            {
                "patient_id": p.patient_id,
                "prescribed_at": p.prescribed_at,
                "notes": overflow_notes(p.notes_overflow)[:10000],
                "source_appointment_id": p.appointment_id,
            },
        )
        rx_id_by_appt[int(p.appointment_id)] = int(cur.fetchone()[0])
        n_rx += 1
    for p in planned:
        rx_id = rx_id_by_appt.get(int(p.appointment_id))
        if rx_id is None:
            continue
        for link in p.links:
            item_id = item_id_by_key.get(normalize_item_name(link.name))
            if item_id is None:  # pragma: no cover — dictionary is complete
                continue
            cur.execute(
                "INSERT INTO prescription_item_links (prescription_id, item_id,"
                " quantity) VALUES (%(rx)s, %(item)s, %(qty)s)",
                {"rx": rx_id, "item": item_id, "qty": link.quantity},
            )
            n_links += 1
    return (n_rx, n_items, n_links)


# --- SQLite (dev/tests) ---------------------------------------------------------------


def _sqlite_fallback(col_type: str) -> str:
    """SQL expression filling a column the dump doesn't have (NOT NULL
    columns added after the dump): numeric/bool → 0, text → '', else NULL."""
    t = col_type.lower()
    if any(k in t for k in ("int", "real", "floa", "doubl", "numeri", "decim", "bool")):
        return "0"
    if "char" in t or "text" in t or "clob" in t:
        return "''"
    return "NULL"


def _qi(name: str) -> str:
    """Escape an identifier for embedding inside double quotes.

    Table/column names read from the imported (potentially hostile) SQLite
    file reach f-string SQL here; doubled quotes keep them contained."""
    return name.replace('"', '""')


def _rederive_prescriptions_sqlite(con: sqlite3.Connection) -> tuple[int, int, int]:
    """SQLite twin of _rederive_prescriptions_from_rx (dev/tests path)."""
    from app.services.rx_migration import (
        RX_MIN_FREQUENCY,
        normalize_item_name,
        overflow_notes,
        plan_rx_migration,
    )

    cur = con.execute(
        'SELECT id, patient_id, scheduled_at, rx FROM main.appointments '
        "WHERE rx IS NOT NULL AND rx <> ''"
    )
    rows = cur.fetchall()
    if not rows:
        return (0, 0, 0)
    planned, dictionary = plan_rx_migration(
        [(int(r[0]), int(r[1]), r[2], r[3]) for r in rows],
        min_frequency=RX_MIN_FREQUENCY,
    )

    item_id_by_key: dict[str, int] = {}
    for item_id, name in con.execute("SELECT id, name FROM main.prescription_items"):
        item_id_by_key[normalize_item_name(str(name))] = int(item_id)
    n_items = 0
    for key, display in sorted(dictionary.items()):
        if key in item_id_by_key:
            continue
        cur = con.execute(
            "INSERT INTO main.prescription_items (name) VALUES (:name)", {"name": display[:128]}
        )
        new_id = con.execute("SELECT MAX(id) FROM main.prescription_items").fetchone()[0]
        item_id_by_key[key] = int(new_id)
        n_items += 1

    done = {
        int(r[0])
        for r in con.execute(
            "SELECT DISTINCT source_appointment_id FROM main.prescriptions "
            "WHERE source_appointment_id IS NOT NULL"
        )
    }

    n_rx = 0
    n_links = 0
    rx_id_by_appt: dict[int, int] = {}
    for p in planned:
        if p.appointment_id in done:
            continue
        con.execute(
            "INSERT INTO main.prescriptions (patient_id, prescribed_at, notes,"
            " source_appointment_id) VALUES (:patient_id, :prescribed_at,"
            " :notes, :source_appointment_id)",
            {
                "patient_id": p.patient_id,
                "prescribed_at": p.prescribed_at,
                "notes": overflow_notes(p.notes_overflow)[:10000],
                "source_appointment_id": p.appointment_id,
            },
        )
        rx_id = con.execute(
            "SELECT MAX(id) FROM main.prescriptions"
        ).fetchone()[0]
        rx_id_by_appt[int(p.appointment_id)] = int(rx_id)
        n_rx += 1
    for p in planned:
        rx_id = rx_id_by_appt.get(int(p.appointment_id))
        if rx_id is None:
            continue
        for link in p.links:
            item_id = item_id_by_key.get(normalize_item_name(link.name))
            if item_id is None:  # pragma: no cover — dictionary is complete
                continue
            con.execute(
                "INSERT INTO main.prescription_item_links (prescription_id,"
                " item_id, quantity) VALUES (:rx, :item, :qty)",
                {"rx": rx_id, "item": item_id, "qty": link.quantity},
            )
            n_links += 1
    return (n_rx, n_items, n_links)


def _import_sqlite(tar_path: str) -> dict:
    db_file = settings.database_url.split("///", 1)[-1]
    aux_path: str | None = None
    # uri=True enables URI filenames on this connection — required for
    # ATTACHing the read-only archive copy below
    con = sqlite3.connect(f"file:{db_file}", uri=True, timeout=10)
    try:
        # the manifest decides whether a DB section is expected at all
        with tarfile.open(tar_path, "r:gz") as tar:
            mf = tar.extractfile("manifest.json")
            if mf is not None:
                manifest = json.loads(mf.read().decode("utf-8"))
                schema_version = manifest.get("schema_version", 1)
                dumped_tables = {
                    k
                    for k, v in (manifest.get("tables") or {}).items()
                    if k != "__sqlite_file__"
                }
        have_dumped_rows = bool(dumped_tables)

        with tarfile.open(tar_path, "r:gz") as tar:
            member = None
            for m in tar:
                if m.name.lstrip("./") == "db/clinic.sqlite3":
                    member = m
                    break
            if member is None:
                if have_dumped_rows:
                    raise RuntimeError(
                        "backup lists tables in its manifest but has no "
                        "db/clinic.sqlite3 member"
                    )
                return {"tables": {}, "schema_version": schema_version}  # uploads-only
            fd, aux_path = tempfile.mkstemp(prefix="clinic-import-", suffix=".sqlite3")
            os.close(fd)
            f = tar.extractfile(member)
            assert f is not None
            with open(aux_path, "wb") as out:
                shutil.copyfileobj(f, out)

        con.execute("PRAGMA foreign_keys=OFF")
        # uri=True on the main connection enables URI filenames (read-only aux)
        con.execute(f"ATTACH DATABASE 'file:{aux_path}?mode=ro' AS aux")  # noqa: S608
        try:
            aux_tables = [
                r[0]
                for r in con.execute("SELECT name FROM aux.sqlite_master WHERE type='table'")
                if not r[0].startswith("sqlite_")
            ]
            live_tables = {
                r[0]
                for r in con.execute("SELECT name FROM main.sqlite_master WHERE type='table'")
                if not r[0].startswith("sqlite_")
            }
            con.execute("BEGIN")
            summary_skew: dict[str, dict] = {}
            try:
                # clear only the dump's tables (absent tables keep their data)
                for t in set(aux_tables) & live_tables:
                    con.execute(f'DELETE FROM main."{_qi(t)}"')  # noqa: S608
                loaded = {}
                skew: dict[str, dict] = {}
                for t in aux_tables:
                    aux_cols = [r[1] for r in con.execute(f'PRAGMA aux.table_info("{_qi(t)}")')]  # noqa: S608
                    if t not in live_tables:
                        skew[t] = {"dropped_table": aux_cols, "defaulted": []}
                        continue  # live schema predates the dump → not importable
                    live_info = con.execute(f'PRAGMA main.table_info("{_qi(t)}")').fetchall()  # noqa: S608
                    live_types = {r[1]: str(r[2] or "TEXT") for r in live_info}
                    live_defaults = {r[1]: r[4] for r in live_info}
                    live_names = [r[1] for r in live_info]
                    dropped = [c for c in aux_cols if c not in live_names]
                    defaulted = [c for c in live_names if c not in aux_cols]
                    if dropped or defaulted:
                        skew[t] = {"dropped": dropped, "defaulted": defaulted}
                    # fill columns the dump doesn't carry: prefer the column's
                    # own DDL default, else a type-aware fallback
                    fill_exprs = []
                    for c in defaulted:
                        dflt = live_defaults.get(c)
                        if (
                            t == "attachments"
                            and c == "patient_id"
                            and "appointment_id" in aux_cols
                        ):
                            # pre-1.3 dump: map appointment_id → patient_id via
                            # the OLD appointments (aux); NULL → NOT NULL
                            # violation → loud rollback
                            fill_exprs.append(
                                '(SELECT a.patient_id FROM aux.appointments a'
                                f' WHERE a.id = aux."{_qi(t)}"."appointment_id") AS "{c}"'
                            )
                            continue
                        if dflt is not None:
                            fill_exprs.append(f"{dflt} AS \"{c}\"")
                        else:
                            fill_exprs.append(
                                f'{_sqlite_fallback(live_types.get(c, "TEXT"))} AS "{c}"'
                            )
                    common = [c for c in aux_cols if c in live_names]
                    col_sql = ", ".join(f'"{c}"' for c in common + defaulted)
                    sel_sql = ", ".join(f'"{c}"' for c in common) + (
                        (", " + ", ".join(fill_exprs)) if fill_exprs else ""
                    )
                    cur = con.execute(
                        f'INSERT INTO main."{_qi(t)}" ({col_sql}) '  # noqa: S608
                        f'SELECT {sel_sql} FROM aux."{_qi(t)}"'
                    )
                    loaded[t] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                # importing a pre-1.3 backup: prescriptions are absent from
                # the dump (or orphaned by the DELETE of their patients) —
                # re-derive from the restored rx text (same frozen parser as
                # the 1.3 migration; same transaction)
                if (
                    schema_version <= 2
                    and "prescriptions" in live_tables
                    and "appointments" in live_tables
                ):
                    n_rx, n_items, n_links = _rederive_prescriptions_sqlite(con)
                    if n_rx:
                        loaded["prescriptions"] = loaded.get("prescriptions", 0) + n_rx
                        loaded["prescription_items"] = n_items
                        loaded["prescription_item_links"] = n_links
                        skew["_rederived_from_rx"] = {
                            "prescriptions": n_rx,
                            "prescription_items": n_items,
                            "prescription_item_links": n_links,
                        }
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            else:
                summary_skew = skew
        finally:
            con.execute("DETACH DATABASE aux")
    finally:
        if aux_path:
            with contextlib.suppress(OSError):
                os.unlink(aux_path)
        con.close()
    return {"tables": loaded, "schema_version": 0, "skew": summary_skew}


# --- uploads -----------------------------------------------------------------------


def _import_uploads(tar_path: str) -> int:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    staging = upload_dir / f".import-{uuid.uuid4().hex[:12]}"
    moved = 0
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            staging.mkdir()
            for m in tar:
                name = m.name.lstrip("./")
                if not name.startswith("uploads/") or m.isdir():
                    continue
                if m.issym() or m.islnk() or m.isdev():
                    continue
                rel = name[len("uploads/") :]
                if not rel or rel.startswith("/") or ".." in rel.split("/"):
                    continue
                dest = staging / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(m)
                if f is None:
                    continue
                with open(dest, "wb") as out:
                    shutil.copyfileobj(f, out)
        # DB is committed at this point (caller ordering) — move into place
        for src in staging.rglob("*"):
            if src.is_file():
                dest = upload_dir / src.relative_to(staging)
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dest)
                moved += 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return moved

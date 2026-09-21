#!/usr/bin/env python3
"""SQLite (legacy Django) → PostgreSQL (new FastAPI system) migration.

Reads the frozen snapshot of the legacy SQLite database directly, copies rows
1:1 into the new schema (PKs preserved), relocates attachment files to UUID
storage, converts legacy free-text rx into structured prescriptions,
prints a data-quality report, and verifies counts/sums automatically.

Design constraints:
- Idempotent: safe to re-run; upserts keyed on preserved PKs (prescriptions
  keyed by source_appointment_id, dictionary items by normalized name).
- Non-destructive: never writes to the source SQLite file.
- 1:1 mapping: no renaming/normalization of legacy values, with TWO
  documented exceptions — transaction descriptions are translated from the
  legacy English types ("Visit"/"Spiro"/"Other") to their current Persian
  variants (ویزیت/اسپیرو/سایر); unmatched values are kept as-is. Legacy
  attachments hang off appointments and are re-parented to the patient
  (resolved via the appointment); legacy free-text rx is converted into
  prescriptions with the same frozen parser as the 1.3 Alembic migration
  (backend/app/services/rx_migration.py).
- Halts ONLY on duplicate national IDs or attachments with unresolvable
  appointment references (ambiguous — needs manual resolution).

Usage:
  python migrate_sqlite.py --source /path/to/db.sqlite3 \
      --files /path/to/patient_files \
      --database-url postgresql+asyncpg://clinic:pass@localhost:5434/clinic \
      [--apply]            # without --apply: dry run (no writes)

Steps: inspect → import → files → report → verify.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import logging
import re
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger("migrate")

# --- Validation rules (the NEW system's rules, for reporting only) ------------
NATIONAL_ID_RE = re.compile(r"^[0-9]{10}$")
YEAR_RE = re.compile(r"^[0-9]{4}$")
PHONE_RE = re.compile(r"^[0-9]+$")

# Legacy Django app used local (Tehran) time in naive datetimes.
SOURCE_TZ = dt.timezone(dt.timedelta(hours=3, minutes=30), "Asia/Tehran")

# Legacy transaction descriptions were English; the new UI uses Persian.
# Match is case-insensitive after whitespace-strip ("visit", " Visit ", …).
LEGACY_TXN_DESCRIPTIONS = {
    "visit": "ویزیت",
    "spiro": "اسپیرو",
    "other": "سایر",
}


def normalize_txn_description(raw: Any) -> str:
    """Translate legacy English payment types to their Persian variants."""
    desc = str(raw or "").strip()
    return LEGACY_TXN_DESCRIPTIONS.get(desc.casefold(), desc)


@dataclasses.dataclass
class Counts:
    source: int = 0
    inserted: int = 0
    skipped_existing: int = 0
    flagged: int = 0

    def row(self, name: str) -> str:
        return (
            f"  {name:<28} source={self.source:<7} inserted={self.inserted:<7}"
            f" skipped={self.skipped_existing:<7} flagged={self.flagged}"
        )


def find_table(cur: sqlite3.Cursor, *candidates: str) -> str:
    """Find a legacy table by name, tolerating the Django '<app>_<model>' prefix.

    Real-world Django names vary in case (e.g. website_patient_Tags) and app
    label (website_, patients_, …), so matching is case-insensitive. When
    multiple tables share a suffix, the shortest name wins (the M2M tables
    like website_patient_Tags also end with 'tag', but website_tag is shorter).
    """
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    folded = {t.casefold(): t for t in tables}
    for cand in candidates:
        if cand.casefold() in folded:
            return folded[cand.casefold()]
    for cand in candidates:
        suffix = f"_{cand}".casefold()
        matches = [t for t in tables if t.casefold().endswith(suffix)]
        if matches:
            return min(matches, key=len)
    raise SystemExit(
        f"Could not find table for {candidates}. Available: {sorted(tables)}"
    )


def load_source(source_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read every legacy table into memory, mapping legacy → new column names."""
    con = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    mapping = {
        "tags": find_table(cur, "patients_tag", "tag"),
        "diagnoses": find_table(cur, "patients_diagnosis", "diagnosis"),
        "patients": find_table(cur, "patients_patient", "patient"),
        "appointments": find_table(cur, "patients_appointment", "appointment"),
        "transactions": find_table(cur, "patients_transaction", "transaction"),
        "attachments": find_table(cur, "patients_attachfile", "attachfile"),
        "patient_tags": find_table(cur, "patients_patient_tags", "patient_tags"),
        "patient_diagnoses": find_table(
            cur, "patients_patient_diagnoses", "patient_diagnoses"
        ),
    }

    # legacy column name → new column name (per logical table)
    col_maps: dict[str, dict[str, str]] = {
        "tags": {"id": "id", "Name": "name"},
        "diagnoses": {"id": "id", "Name": "name"},
        "patients": {
            "index": "id",
            "ID": "national_id",
            "First_Name": "first_name",
            "Last_Name": "last_name",
            "Insurance": "insurance",
            "Year_of_Birth": "year_of_birth",
            "Phone_Number": "phone_number",
            "Gender": "gender",
        },
        "appointments": {
            "index": "id",
            "Patient_id": "patient_id",
            "Appointment_Date": "scheduled_at",
            "Notes": "notes",
            "CM": "cm",
            "HX": "hx",
            "PX": "px",
            "RX": "rx",
        },
        "transactions": {
            "id": "id",
            "Related_Appointment_id": "appointment_id",
            "Description": "description",
            "Amount": "amount",
            "POS": "pos",
        },
        "attachments": {
            "id": "id",
            "Appointment_id": "appointment_id",
            "Description": "description",
            "File": "legacy_file",
            "Notes": "notes",
        },
        "patient_tags": {},
        "patient_diagnoses": {},
    }

    tables: dict[str, list[dict[str, Any]]] = {}
    for key, table in mapping.items():
        rows = [dict(r) for r in cur.execute(f"SELECT * FROM {table}")]
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
        cmap = col_maps[key]
        if cmap:
            missing = [c for c in cmap if c not in cols]
            if missing:
                raise SystemExit(
                    f"Table {table} lacks expected columns {missing}; found {cols}"
                )
            tables[key] = [{cmap.get(k, k): v for k, v in r.items()} for r in rows]
        else:
            tables[key] = rows

    # attachments carry the legacy Appointment_id — the new schema hangs
    # files on the PATIENT, resolved below (after both tables are loaded)
    for a in tables["attachments"]:
        a["legacy_appointment_id"] = a.get("appointment_id")
        a["appointment_id"] = None
        a["patient_id"] = None

    # M2M through-tables: Django names FKs like <model>_id and <model>__id.
    # Map the FK pointing at patients → patient_id; the other → tag/diagnosis_id.
    def normalize_m2m(key: str, other: str, other_col: str) -> None:
        table = mapping[key]
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
        fk_cols = [c for c in cols if c != "id"]  # drop the M2M's own PK
        patient_col = next(
            (c for c in fk_cols if "patient" in c.lower() or c == "from_patients"),
            fk_cols[0],
        )
        other_fk = next(c for c in fk_cols if c != patient_col)
        tables[key] = [
            {"patient_id": r[patient_col], other_col: r[other_fk]} for r in tables[key]
        ]

    normalize_m2m("patient_tags", "tags", "tag_id")
    normalize_m2m("patient_diagnoses", "diagnoses", "diagnosis_id")
    con.close()
    return tables


def resolve_attachment_patients(tables: dict[str, list[dict[str, Any]]]) -> list[int]:
    """Fill attachments.patient_id from the legacy appointment's patient.

    Returns the ids of attachments that could not be resolved (dangling
    appointment reference — FK integrity of the legacy DB makes this a
    corruption signal; the caller halts).
    """
    appt_patient = {
        (a.get("id") or a.get("index")): a.get("patient_id")
        for a in tables["appointments"]
    }
    unresolved: list[int] = []
    for a in tables["attachments"]:
        pid = appt_patient.get(a.get("legacy_appointment_id"))
        if pid is None:
            unresolved.append(a.get("id"))
            continue
        a["patient_id"] = pid
    return unresolved


def plan_rx_prescriptions(
    tables: dict[str, list[dict[str, Any]]],
) -> tuple[list[Any], dict[str, str]]:
    """Convert legacy rx free text into planned prescriptions.

    Uses the SAME frozen parser as the 1.3 Alembic migration
    (app.services.rx_migration) — see that module for the semantics.
    `prescribed_at` is the appointment's date (legacy tz → UTC).
    Returns (planned prescriptions, dictionary {norm key: display name}).
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from app.services.rx_migration import plan_rx_migration

    rows = []
    for a in tables["appointments"]:
        rx = (a.get("rx") or "").strip()
        if not rx:
            continue
        rows.append(
            (
                a.get("id") or a.get("index"),
                a.get("patient_id"),
                to_utc(parse_legacy_date(a.get("scheduled_at"))),
                rx,
            )
        )
    return plan_rx_migration(rows)


def data_quality_report(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Flag legacy rows that violate the new validation rules. Non-blocking."""
    issues: list[str] = []

    nids: dict[str, list[int]] = {}
    for p in tables["patients"]:
        pid, nid = p.get("id") or p.get("index"), p.get("national_id", "")
        if nid:
            nids.setdefault(str(nid).strip(), []).append(pid)
    for nid, pids in nids.items():
        if len(pids) > 1:
            issues.append(
                f"DUPLICATE national_id={nid} across patient indexes {pids} — "
                "HALT required: resolve manually before import."
            )

    for p in tables["patients"]:
        pid = p.get("id") or p.get("index")
        nid = str(p.get("national_id") or "")
        yob = str(p.get("year_of_birth") or "")
        phone = str(p.get("phone_number") or "")
        if not NATIONAL_ID_RE.match(nid):
            issues.append(f"patient {pid}: national_id '{nid}' is not 10 digits")
        if yob and not YEAR_RE.match(yob):
            issues.append(f"patient {pid}: year_of_birth '{yob}' is not 4 digits")
        if phone and not PHONE_RE.match(phone):
            issues.append(f"patient {pid}: phone '{phone}' contains non-digits")
    return issues


def to_utc(naive_or_none: Any) -> dt.datetime | None:
    if naive_or_none is None:
        return None
    if isinstance(naive_or_none, str):
        naive_or_none = dt.datetime.fromisoformat(naive_or_none)
    if naive_or_none.tzinfo is None:
        return naive_or_none.replace(tzinfo=SOURCE_TZ).astimezone(dt.UTC)
    return naive_or_none.astimezone(dt.UTC)


def parse_legacy_date(value: Any) -> dt.datetime:
    """Django stored e.g. '2025-01-02 10:30:00' (naive local)."""
    if isinstance(value, str):
        return dt.datetime.fromisoformat(value)
    return dt.datetime(
        value.year,
        value.month,
        value.day,
        value.hour,
        value.minute,
        value.second,
        tzinfo=SOURCE_TZ,
    )


async def import_rows(
    engine: Any, tables: dict[str, list[dict[str, Any]]], apply: bool
) -> dict[str, Counts]:
    from sqlalchemy import text

    if not apply:
        # Dry run: report what would happen; verification still compares
        # counts against existing target data (likely an empty/old snapshot).
        return {k: Counts(source=len(v), skipped_existing=len(v)) for k, v in tables.items()}

    results: dict[str, Counts] = {}
    async with engine.begin() as conn:
        existing_patients = {
            r[0] for r in await conn.execute(text("SELECT id FROM patients"))
        }
        existing_tags = {r[0] for r in await conn.execute(text("SELECT id FROM tags"))}
        existing_diag = {
            r[0] for r in await conn.execute(text("SELECT id FROM diagnoses"))
        }

    # --- batched insert helper ----------------------------------------------------
    async def insert_batch(
        conn: Any, table: str, cols: list[str], rows: list[dict[str, Any]]
    ) -> None:
        if not rows:
            return
        cols_sql = ", ".join(cols)
        vals_sql = ", ".join(":" + c for c in cols)
        # chunked to keep parameter counts within driver limits
        for i in range(0, len(rows), 1000):
            await conn.execute(
                text(f"INSERT INTO {table} ({cols_sql}) VALUES ({vals_sql})"),
                rows[i : i + 1000],
            )

    # --- tags / diagnoses -------------------------------------------------------
    for name, existing, tbl in (
        ("tags", existing_tags, "tags"),
        ("diagnoses", existing_diag, "diagnoses"),
    ):
        c = Counts(source=len(tables[name]))
        new_rows = [
            {"id": t.get("id"), "name": t.get("name")}
            for t in tables[name]
            if t.get("id") not in existing
        ]
        c.skipped_existing = len(tables[name]) - len(new_rows)
        async with engine.begin() as conn:
            await insert_batch(conn, tbl, ["id", "name"], new_rows)
        c.inserted = len(new_rows)
        results[name] = c

    # --- patients --------------------------------------------------------------
    c = Counts(source=len(tables["patients"]))
    new_rows = []
    for p in tables["patients"]:
        pid = p.get("id") or p.get("index")
        if pid in existing_patients:
            continue
        new_rows.append(
            {
                "id": pid,
                "national_id": p.get("national_id"),
                "first_name": p.get("first_name"),
                "last_name": p.get("last_name"),
                "insurance": p.get("insurance"),
                "year_of_birth": p.get("year_of_birth"),
                "phone_number": p.get("phone_number") or "",
                "gender": int(p.get("gender") or 0),
            }
        )
    c.skipped_existing = len(tables["patients"]) - len(new_rows)
    async with engine.begin() as conn:
        await insert_batch(
            conn,
            "patients",
            [
                "id",
                "national_id",
                "first_name",
                "last_name",
                "insurance",
                "year_of_birth",
                "phone_number",
                "gender",
            ],
            new_rows,
        )
    c.inserted = len(new_rows)
    results["patients"] = c

    # --- appointments ------------------------------------------------------------
    c = Counts(source=len(tables["appointments"]))
    async with engine.begin() as conn:
        existing_appts = {
            r[0] for r in await conn.execute(text("SELECT id FROM appointments"))
        }
    new_rows = []
    for a in tables["appointments"]:
        aid = a.get("id") or a.get("index")
        if aid in existing_appts:
            continue
        new_rows.append(
            {
                "id": aid,
                "patient_id": a.get("patient_id"),
                "scheduled_at": to_utc(parse_legacy_date(a.get("scheduled_at"))),
                "notes": a.get("notes") or "",
                "cm": a.get("cm") or "",
                "hx": a.get("hx") or "",
                "px": a.get("px") or "",
                "rx": a.get("rx") or "",
            }
        )
    c.skipped_existing = len(tables["appointments"]) - len(new_rows)
    async with engine.begin() as conn:
        await insert_batch(
            conn,
            "appointments",
            ["id", "patient_id", "scheduled_at", "notes", "cm", "hx", "px", "rx"],
            new_rows,
        )
    c.inserted = len(new_rows)
    results["appointments"] = c

    # --- transactions --------------------------------------------------------------
    c = Counts(source=len(tables["transactions"]))
    async with engine.begin() as conn:
        existing_txns = {
            r[0] for r in await conn.execute(text("SELECT id FROM transactions"))
        }
    new_rows = []
    for t in tables["transactions"]:
        if t.get("id") in existing_txns:
            continue
        new_rows.append(
            {
                "id": t.get("id"),
                "appointment_id": t.get("appointment_id"),
                "description": normalize_txn_description(t.get("description")),
                "amount": int(t.get("amount") or 0),
                "pos": bool(t.get("pos")),
            }
        )
    c.skipped_existing = len(tables["transactions"]) - len(new_rows)
    async with engine.begin() as conn:
        await insert_batch(
            conn,
            "transactions",
            ["id", "appointment_id", "description", "amount", "pos"],
            new_rows,
        )
    c.inserted = len(new_rows)
    results["transactions"] = c

    # --- attachments (metadata; file copying handled separately) --------------------
    c = Counts(source=len(tables["attachments"]))
    async with engine.begin() as conn:
        existing_atts = {
            r[0] for r in await conn.execute(text("SELECT id FROM attachments"))
        }
    new_rows = []
    for a in tables["attachments"]:
        if a.get("id") in existing_atts:
            continue
        legacy = (a.get("legacy_file") or "").strip()
        if a.get("patient_id") is None:
            # guarded by the halt check in main() — should never happen
            raise SystemExit(
                f"attachment {a.get('id')} has no resolvable patient "
                f"(legacy appointment {a.get('legacy_appointment_id')})"
            )
        new_rows.append(
            {
                "id": a.get("id"),
                "patient_id": a.get("patient_id"),
                "description": a.get("description") or "",
                "notes": a.get("notes") or "",
                # original_filename kept only for rows that ever had a file;
                # the relocation pass fills stored/mime/size and clears
                # missing_file for files actually copied.
                "original_filename": legacy or None,
                "missing_file": bool(legacy),
                "stored_filename": None,
                "mime_type": None,
                "size_bytes": None,
            }
        )
    c.skipped_existing = len(tables["attachments"]) - len(new_rows)
    async with engine.begin() as conn:
        await insert_batch(
            conn,
            "attachments",
            [
                "id",
                "patient_id",
                "description",
                "notes",
                "stored_filename",
                "original_filename",
                "mime_type",
                "size_bytes",
                "missing_file",
            ],
            new_rows,
        )
    c.inserted = len(new_rows)
    results["attachments"] = c

    # --- prescriptions (from legacy rx free text) ---------------------------------
    results["prescriptions"], results["prescription_items"], results["rx_links"] = (
        await import_rx_prescriptions(engine, tables)
    )

    # --- M2M links --------------------------------------------------------------------
    for name, table, cols in (
        ("patient_tags", "patient_tags", ["patient_id", "tag_id"]),
        ("patient_diagnoses", "patient_diagnoses", ["patient_id", "diagnosis_id"]),
    ):
        c = Counts(source=len(tables[name]))
        async with engine.begin() as conn:
            await conn.execute(text(f"DELETE FROM {table}"))
            await insert_batch(conn, table, cols, tables[name])
        c.inserted = len(tables[name])
        results[name] = c

    return results


async def import_rx_prescriptions(
    engine: Any, tables: dict[str, list[dict[str, Any]]]
) -> tuple[Counts, Counts, Counts]:
    """Create prescriptions/prescription_items/links from legacy rx text.

    Idempotent: prescriptions are keyed by source_appointment_id (legacy
    appointment ids are preserved), dictionary items by normalized name.
    Uses the same frozen parser as the 1.3 Alembic migration.
    """
    from app.services.rx_migration import normalize_item_name, overflow_notes
    from sqlalchemy import text as sa_text

    planned, dictionary = plan_rx_prescriptions(tables)
    n_source_rx = len(
        [a for a in tables["appointments"] if (a.get("rx") or "").strip()]
    )

    async with engine.begin() as conn:
        # dictionary: dedupe against existing items by NORMALIZED name
        # (case/edge punctuation are only display variants)
        item_id_by_key: dict[str, int] = {}
        for item_id, name in (
            await conn.execute(sa_text("SELECT id, name FROM prescription_items"))
        ).all():
            item_id_by_key[normalize_item_name(str(name))] = int(item_id)

        inserted_items = 0
        for key, display in sorted(dictionary.items()):
            if key in item_id_by_key:
                continue
            new_id = (
                await conn.execute(
                    sa_text(
                        "INSERT INTO prescription_items (name) VALUES (:name)"
                        " RETURNING id"
                    ),
                    {"name": display[:128]},
                )
            ).scalar_one()
            item_id_by_key[key] = int(new_id)
            inserted_items += 1

        done_appts = {
            int(r[0])
            for r in await conn.execute(
                sa_text(
                    "SELECT source_appointment_id FROM prescriptions"
                    " WHERE source_appointment_id IS NOT NULL"
                )
            )
        }

        new_rx_rows = []
        for p in planned:
            if p.appointment_id in done_appts:
                continue
            new_rx_rows.append(
                {
                    "patient_id": p.patient_id,
                    "prescribed_at": p.prescribed_at,
                    "notes": overflow_notes(p.notes_overflow)[:10000],
                    "source_appointment_id": p.appointment_id,
                }
            )
        if new_rx_rows:
            await conn.execute(
                sa_text(
                    "INSERT INTO prescriptions (patient_id, prescribed_at, notes,"
                    " source_appointment_id) VALUES (:patient_id, :prescribed_at,"
                    " :notes, :source_appointment_id)"
                ),
                new_rx_rows,
            )

        # links: only for prescriptions created on THIS run (a re-run must
        # not re-insert links of prescriptions that already have them —
        # uq_prescription_item_links_pair would reject the duplicates);
        # planned links are already deduped per prescription by normalized key
        new_appt_ids = {p.appointment_id for p in new_rx_rows}
        rx_id_by_appt = {
            int(r[0]): int(r[1])
            for r in await conn.execute(
                sa_text(
                    "SELECT source_appointment_id, id FROM prescriptions"
                    " WHERE source_appointment_id IS NOT NULL"
                )
            )
            if int(r[0]) in new_appt_ids
        }
        link_rows = []
        for p in planned:
            rx_id = rx_id_by_appt.get(p.appointment_id)
            if rx_id is None:  # skipped (previously imported)
                continue
            for link in p.links:
                item_id = item_id_by_key.get(normalize_item_name(link.name))
                if item_id is None:  # pragma: no cover — dictionary is complete
                    continue
                link_rows.append(
                    {"prescription_id": rx_id, "item_id": item_id, "quantity": link.quantity}
                )
        if link_rows:
            await conn.execute(
                sa_text(
                    "INSERT INTO prescription_item_links (prescription_id,"
                    " item_id, quantity) VALUES (:prescription_id, :item_id,"
                    " :quantity)"
                ),
                link_rows,
            )

    rx_counts = Counts(
        source=n_source_rx,
        inserted=len(new_rx_rows),
        skipped_existing=n_source_rx - len(new_rx_rows),
    )
    item_counts = Counts(source=len(dictionary), inserted=inserted_items)
    link_counts = Counts(
        source=sum(len(p.links) for p in planned), inserted=len(link_rows)
    )
    return rx_counts, item_counts, link_counts


async def update_attachment_meta(
    engine: Any, tables: dict[str, list[dict[str, Any]]], upload_dir: Path, apply: bool
) -> None:
    from sqlalchemy import text

    upload_dir.mkdir(parents=True, exist_ok=True)
    # Skip attachments that were already migrated on a previous run
    async with engine.connect() as conn:
        existing = {
            r[0]: r[1]
            for r in await conn.execute(
                text(
                    "SELECT id, stored_filename FROM attachments"
                    " WHERE stored_filename IS NOT NULL"
                )
            )
        }
    copied = note_only = missing = 0
    # NOTE: no content-hash dedup across rows — uq_attachments_stored_filename_live
    # forbids two LIVE rows sharing one stored_filename, so each attachment
    # row gets its own copy (identical legacy content is stored multiple
    # times by design). Re-run safety comes from the existing-skip above:
    # rows already relocated (stored_filename set) are never reprocessed.
    for a in tables["attachments"]:
        legacy = (a.get("legacy_file") or "").strip()
        aid = a.get("id")
        if aid in existing:
            continue  # already relocated in a previous run
        if not legacy:
            # Legacy rows with an empty File field are note-only records:
            # no file was ever uploaded. Keep as metadata-only rows.
            note_only += 1
            continue
        src = files_dir_lookup(legacy)
        if src and src.is_file():
            size = src.stat().st_size
            mime = guess_mime(src.name)
            stored = f"{uuid.uuid4().hex}{Path(legacy).suffix}"
            if apply:
                shutil.copy2(src, upload_dir / stored)
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE attachments SET stored_filename = :s,"
                            " original_filename = :o, mime_type = :m, size_bytes = :sz,"
                            " missing_file = FALSE WHERE id = :id"
                        ),
                        {
                            "s": stored,
                            "o": Path(legacy).name,
                            "m": mime,
                            "sz": size,
                            "id": aid,
                        },
                    )
            copied += 1
        else:
            # A file was referenced but is absent on disk — genuine data loss.
            missing += 1
            log.warning("attachment %s: physical file missing for %r", aid, legacy)
    log.info(
        "file relocation: copied=%s note-only=%s missing=%s",
        copied,
        note_only,
        missing,
    )


def _file_size(p: Path) -> int:
    return p.stat().st_size


def _file_sha(p: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_FILES_DIR: Path | None = None


def files_dir_lookup(legacy: str) -> Path | None:
    if _FILES_DIR is None or not legacy:
        return None
    return _FILES_DIR / Path(legacy).name


def guess_mime(name: str) -> str:
    import mimetypes

    return mimetypes.guess_type(name)[0] or "application/octet-stream"


async def set_sequences(engine: Any, apply: bool) -> None:
    """Bump identity sequences past the imported max PKs (PostgreSQL only)."""
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return

    seqs = {
        "tags": "tags_id_seq",
        "diagnoses": "diagnoses_id_seq",
        "prescription_items": "prescription_items_id_seq",
        "patients": "patients_id_seq",
        "appointments": "appointments_id_seq",
        "transactions": "transactions_id_seq",
        "attachments": "attachments_id_seq",
        "prescriptions": "prescriptions_id_seq",
        "prescription_item_links": "prescription_item_links_id_seq",
        "users": "users_id_seq",
    }
    async with engine.begin() as conn:
        for table, seq in seqs.items():
            row = await conn.execute(text(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}"))
            next_val = row.scalar()
            if apply:
                await conn.execute(
                    text(f"SELECT setval('{seq}', :v)"), {"v": int(next_val)}
                )


async def verify(
    engine: Any,
    tables: dict[str, list[dict[str, Any]]],
    apply: bool,
    rx_expected: tuple[int, int, int] | None = None,
) -> bool:
    """Compare source vs target counts and money sums; print pass/fail.

    In dry-run mode nothing was written, so target comparisons are skipped;
    we only verify internal source consistency (FK references inside the
    legacy snapshot) and the money-sum split by payment method.

    ``rx_expected``: (prescriptions, items, links) planned counts for the
    rx → prescriptions conversion (target may be higher when the DB
    already holds rows; only monotonic growth is checked).
    """
    from sqlalchemy import text

    ok = True
    print("\n=== VERIFICATION ===")

    # --- source-internal checks (always) --------------------------------------
    src_pos = sum(int(t.get("amount") or 0) for t in tables["transactions"] if t.get("pos"))
    src_cash = sum(
        int(t.get("amount") or 0) for t in tables["transactions"] if not t.get("pos")
    )
    src_total = src_pos + src_cash
    recomputed = sum(int(t.get("amount") or 0) for t in tables["transactions"])
    sum_ok = src_total == recomputed
    if not sum_ok:
        ok = False
    print(
        f"  [{'OK ' if sum_ok else 'FAIL'}] source money split:"
        f" POS={src_pos} CASH={src_cash} total={src_total}"
    )

    src_patients = {p.get("id") or p.get("index") for p in tables["patients"]}
    dangling_src = [
        a.get("id") or a.get("index")
        for a in tables["appointments"]
        if a.get("patient_id") not in src_patients
    ]
    src_fk_ok = not dangling_src
    if not src_fk_ok:
        ok = False
    print(
        f"  [{'OK ' if src_fk_ok else 'FAIL'}] source appointments reference"
        f" existing patients ({len(dangling_src)} dangling)"
    )

    if not apply:
        print("  [SKIP] target comparison skipped — dry run writes nothing")
        return ok

    # --- target comparisons (apply mode) --------------------------------------
    async with engine.begin() as conn:
        for name, table in (
            ("tags", "tags"),
            ("diagnoses", "diagnoses"),
            ("patients", "patients"),
            ("appointments", "appointments"),
            ("transactions", "transactions"),
            ("attachments", "attachments"),
        ):
            src = len(tables[name])
            tgt = (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar()
            match = "OK " if src == tgt else "FAIL"
            if src != tgt:
                ok = False
            print(f"  [{match}] {name:<14} source={src:<7} target={tgt}")

        # rx conversion: the planned rows must all be present (target can
        # exceed the plan only via pre-existing/user-created rows)
        if rx_expected is not None:
            for label, table, expected in (
                ("prescriptions", "prescriptions", rx_expected[0]),
                ("prescription_items", "prescription_items", rx_expected[1]),
                ("prescription_item_links", "prescription_item_links", rx_expected[2]),
            ):
                tgt = (
                    await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                ).scalar()
                match = "OK " if int(tgt) >= expected else "FAIL"
                if int(tgt) < expected:
                    ok = False
                print(f"  [{match}] {label:<14} expected>={expected:<7} target={tgt}")

        src_pos = sum(int(t.get("amount") or 0) for t in tables["transactions"] if t.get("pos"))
        src_cash = sum(
            int(t.get("amount") or 0) for t in tables["transactions"] if not t.get("pos")
        )
        tgt_pos = (
            await conn.execute(text("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE pos"))
        ).scalar()
        tgt_cash = (
            await conn.execute(
                text("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE NOT pos")
            )
        ).scalar()
        pos_ok = int(tgt_pos) == src_pos
        cash_ok = int(tgt_cash) == src_cash
        if not (pos_ok and cash_ok):
            ok = False
        print(
            f"  [{'OK ' if pos_ok else 'FAIL'}] POS total"
            f"  source={src_pos:<10} target={tgt_pos}"
        )
        print(
            f"  [{'OK ' if cash_ok else 'FAIL'}] CASH total"
            f" source={src_cash:<10} target={tgt_cash}"
        )

        # per-patient appointment counts: single grouped query, compare maps
        src_counts: dict[int, int] = {}
        for a in tables["appointments"]:
            pid = a.get("patient_id")
            src_counts[pid] = src_counts.get(pid, 0) + 1
        tgt_counts = {
            r[0]: r[1]
            for r in await conn.execute(
                text("SELECT patient_id, COUNT(*) FROM appointments GROUP BY patient_id")
            )
        }
        mismatches = 0
        for pid, src in src_counts.items():
            if tgt_counts.get(pid, 0) != src:
                mismatches += 1
                print(
                    f"  [FAIL] patient {pid}: appointments"
                    f" source={src} target={tgt_counts.get(pid, 0)}"
                )
        if mismatches:
            ok = False
        else:
            print("  [OK ] per-patient appointment counts match")

        orphans = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM appointments a"
                    " LEFT JOIN patients p ON p.id = a.patient_id WHERE p.id IS NULL"
                )
            )
        ).scalar()
        orphan_ok = int(orphans) == 0
        if not orphan_ok:
            ok = False
        print(f"  [{'OK ' if orphan_ok else 'FAIL'}] orphan appointments: {orphans}")

        # M2M link integrity (target side: links to nonexistent rows)
        for link_table, other_table, col in (
            ("patient_tags", "tags", "tag_id"),
            ("patient_diagnoses", "diagnoses", "diagnosis_id"),
        ):
            dangling = (
                await conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {link_table} l"
                        f" LEFT JOIN {other_table} o ON o.id = l.{col}"
                        " WHERE o.id IS NULL"
                    )
                )
            ).scalar()
            link_ok = int(dangling) == 0
            if not link_ok:
                ok = False
            print(
                f"  [{'OK ' if link_ok else 'FAIL'}] dangling {link_table}: {dangling}"
            )
    return ok


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Legacy db.sqlite3 (read-only)")
    parser.add_argument("--files", required=True, type=Path, help="Legacy patient_files/ directory")
    parser.add_argument("--database-url", required=True, help="Target PostgreSQL URL")
    parser.add_argument("--upload-dir", required=True, type=Path, help="New uploads directory")
    parser.add_argument("--apply", action="store_true", help="Actually write (default: dry-run)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    global _FILES_DIR
    _FILES_DIR = args.files

    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN (no writes)'}")
    print(f"Source DB: {args.source}")
    print(f"Source files: {args.files}")
    print(f"Target: {args.database_url.split('@')[-1]}")

    if not args.source.is_file():
        log.error("Source database not found: %s", args.source)
        return 2
    if not args.files.is_dir():
        log.error("Legacy files dir not found: %s", args.files)
        return 2

    tables = load_source(args.source)
    print("\n=== SOURCE CONTENTS ===")
    for k in (
        "tags",
        "diagnoses",
        "patients",
        "appointments",
        "transactions",
        "attachments",
        "patient_tags",
        "patient_diagnoses",
    ):
        print(f"  {k:<18} {len(tables[k])} rows")

    # attachments hang on PATIENTS in the new schema — resolve via the
    # legacy appointment; a dangling reference is corruption → halt
    unresolved_atts = resolve_attachment_patients(tables)
    if unresolved_atts:
        log.error(
            "attachments whose legacy appointment_id has no matching"
            " appointment row: %s — resolve manually before importing",
            unresolved_atts,
        )
        return 3

    issues = data_quality_report(tables)
    print("\n=== DATA-QUALITY REPORT (non-blocking) ===")
    if not issues:
        print("  clean — no legacy rows violate the new validation rules")
    else:
        for i in issues:
            print(f"  - {i}")

    dupes = [i for i in issues if i.startswith("DUPLICATE")]
    if dupes and args.apply:
        log.error("Refusing to APPLY with duplicate national IDs present. Resolve first.")
        return 3

    # rx → structured prescriptions (same parser as the 1.3 Alembic migration)
    planned, dictionary = plan_rx_prescriptions(tables)
    n_overflow = sum(1 for p in planned if p.notes_overflow)
    print("\n=== RX CONVERSION PLAN ===")
    print(f"  appointments with rx text : {len(planned)}")
    print(f"  prescriptions to create   : {len(planned)}")
    print(f"  dictionary items (≥ freq) : {len(dictionary)}")
    print(f"  item links                : {sum(len(p.links) for p in planned)}")
    print(
        f"  prescriptions with free-text overflow in notes: {n_overflow}"
        " (original rx text is also preserved in appointments.rx)"
    )

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(args.database_url)

    # Import rows
    counts = await import_rows(engine, tables, args.apply)
    print("\n=== IMPORT ===")
    for name, c in counts.items():
        print(c.row(name))

    # Payment-type translation report (legacy English → Persian)
    buckets: dict[str, int] = {}
    for t in tables["transactions"]:
        translated = normalize_txn_description(t.get("description"))
        buckets[translated] = buckets.get(translated, 0) + 1
    print("\n=== PAYMENT TYPE TRANSLATION (legacy → current) ===")
    for legacy_en, persian in LEGACY_TXN_DESCRIPTIONS.items():
        n = buckets.pop(persian, 0)
        print(f"  {legacy_en:<8} → {persian}: {n} rows")
    for desc, n in sorted(buckets.items(), key=lambda kv: -kv[1]):
        print(f"  (kept as-is) {desc!r}: {n} rows")

    # File relocation + metadata
    print("\n=== FILE RELOCATION ===")
    n_found = n_missing = n_note_only = 0
    referenced: set[str] = set()
    for a in tables["attachments"]:
        legacy = (a.get("legacy_file") or "").strip()
        if not legacy:
            n_note_only += 1
            continue
        referenced.add(Path(legacy).name)
        if (args.files / Path(legacy).name).is_file():
            n_found += 1
        else:
            n_missing += 1
    unreferenced = 0
    if args.files.is_dir():
        disk = {p.name for p in args.files.iterdir() if p.is_file()}
        unreferenced = len(disk - referenced)
    print(
        f"  would copy {n_found} files | note-only rows (no file): {n_note_only}"
        f" | referenced but absent on disk: {n_missing}"
        f" | on disk but unreferenced by DB rows: {unreferenced}"
    )
    if args.apply:
        await update_attachment_meta(engine, tables, args.upload_dir, True)
        await set_sequences(engine, True)
        print(f"  files copied into {args.upload_dir} (UUID names, DB metadata updated)")

    ok = await verify(
        engine,
        tables,
        args.apply,
        rx_expected=(
            len(planned),
            len(dictionary),
            sum(len(p.links) for p in planned),
        ),
    )
    await engine.dispose()

    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    if ok and not args.apply:
        print("Re-run with --apply to perform the actual migration.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

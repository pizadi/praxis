#!/usr/bin/env python3
"""Independent post-import verification: SQLite legacy vs PostgreSQL target.

Deliberately does NOT reuse migrate_sqlite.py's own verification logic."""

import random
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

SRC = Path("old_database/db.sqlite3")
UPLOADS = Path("work/real-uploads")

src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
dst = create_engine("postgresql+psycopg2://clinic:testpass@localhost:5432/clinic")

def _referenced_bytes(src: sqlite3.Connection) -> int:
    """Bytes of files on disk that ARE referenced by DB rows (what we copy)."""
    from pathlib import Path as P

    total = 0
    for (f,) in src.execute(
        "SELECT File FROM website_attachfile WHERE File IS NOT NULL AND TRIM(File)!=''"
    ):
        p = P("old_database/patient_files") / f.split("/")[-1]
        if p.is_file():
            total += p.stat().st_size
    return total


checks = []
with dst.connect() as c:
    # 1. row counts
    for src_t, dst_t in [
        ("website_patient", "patients"),
        ("website_appointment", "appointments"),
        ("website_transaction", "transactions"),
        ("website_attachfile", "attachments"),
        ("website_tag", "tags"),
        ("website_diagnosis", "diagnoses"),
    ]:
        s = src.execute(f'SELECT COUNT(*) FROM "{src_t}"').fetchone()[0]
        d = c.execute(text(f"SELECT COUNT(*) FROM {dst_t}")).scalar()
        checks.append((f"count {dst_t}", s, d, s == d))

    # 2. money sums exact (bigint, no float)
    for label, sql_s, sql_d in [
        (
            "POS sum",
            "SELECT COALESCE(SUM(Amount),0) FROM website_transaction WHERE POS=1",
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE pos",
        ),
        (
            "CASH sum",
            "SELECT COALESCE(SUM(Amount),0) FROM website_transaction WHERE POS=0",
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE NOT pos",
        ),
    ]:
        s = src.execute(sql_s).fetchone()[0]
        d = c.execute(text(sql_d)).scalar()
        checks.append((label, s, d, s == d))

    # 3. field-by-field patient comparison (first / last / random / dirty)
    pids = [
        src.execute('SELECT MIN("index") FROM website_patient').fetchone()[0],
        src.execute('SELECT MAX("index") FROM website_patient').fetchone()[0],
        src.execute(
            'SELECT "index" FROM website_patient WHERE ID=?', ("1111111111",)
        ).fetchone()[0],
        5, 763, 1582, 3544,  # the dirty-phone patients from the quality report
    ]
    for pid in pids:
        srow = src.execute(
            "SELECT ID, First_Name, Last_Name, Insurance, Year_of_Birth,"
            ' Phone_Number, Gender FROM website_patient WHERE "index"=?',
            (pid,),
        ).fetchone()
        drow = c.execute(
            text(
                "SELECT national_id, first_name, last_name, insurance,"
                " year_of_birth, phone_number, gender FROM patients WHERE id=:i"
            ),
            {"i": pid},
        ).fetchone()
        same = tuple(srow) == tuple(drow)
        checks.append((f"patient {pid} all fields", "ok", "ok", same))

    # 4. M2M link counts
    s = src.execute("SELECT COUNT(*) FROM website_patient_Tags").fetchone()[0]
    d = c.execute(text("SELECT COUNT(*) FROM patient_tags")).scalar()
    checks.append(("count patient_tags", s, d, s == d))
    s = src.execute("SELECT COUNT(*) FROM website_patient_Diagnoses").fetchone()[0]
    d = c.execute(text("SELECT COUNT(*) FROM patient_diagnoses")).scalar()
    checks.append(("count patient_diagnoses", s, d, s == d))

    # 5. note text survived (non-empty counts)
    for label, col in [("appt notes", "Notes"), ("CM", "CM"), ("HX", "HX"), ("RX", "RX")]:
        s = src.execute(f"SELECT COUNT(*) FROM website_appointment WHERE {col} != ''").fetchone()[0]
        d = c.execute(text(f"SELECT COUNT(*) FROM appointments WHERE {col.lower()} != ''")).scalar()
        checks.append((f"non-empty {label}", s, d, s == d))

    # 6. attachments: note-only vs file rows
    s = src.execute(
        "SELECT COUNT(*) FROM website_attachfile"
        " WHERE File IS NULL OR TRIM(File)=''"
    ).fetchone()[0]
    d = c.execute(
        text(
            "SELECT COUNT(*) FROM attachments"
            " WHERE stored_filename IS NULL AND missing_file = FALSE"
        )
    ).scalar()
    checks.append(("note-only attachments", s, d, s == d))
    # 6b. file-backed rows: referenced = stored + genuinely-missing-on-disk (7)
    s = src.execute(
        "SELECT COUNT(*) FROM website_attachfile"
        " WHERE File IS NOT NULL AND TRIM(File)!=''"
    ).fetchone()[0]
    stored = c.execute(
        text("SELECT COUNT(*) FROM attachments WHERE stored_filename IS NOT NULL")
    ).scalar()
    missing = c.execute(
        text("SELECT COUNT(*) FROM attachments WHERE missing_file = TRUE")
    ).scalar()
    # expected: stored 4934, missing 7, and stored+missing == referenced
    checks.append(
        ("file-backed attachments", s, f"stored={stored} missing={missing}",
         stored == 4934 and stored + missing == s)
    )

    # 7. timestamps: spot-check tz conversion (Tehran +03:30 → UTC)
    aid = src.execute('SELECT MIN("index") FROM website_appointment').fetchone()[0]
    srow = src.execute(
        'SELECT Appointment_Date FROM website_appointment WHERE "index"=?', (aid,)
    ).fetchone()[0]
    d = c.execute(text("SELECT scheduled_at FROM appointments WHERE id=:i"), {"i": aid}).scalar()
    import datetime as dt

    s_dt = dt.datetime.fromisoformat(srow).replace(
        tzinfo=dt.timezone(dt.timedelta(hours=3, minutes=30))
    )
    checks.append((f"appt {aid} tz conversion", str(srow), str(d), s_dt == d))

    # 8. physical files: sizes match for a random sample of 100
    rows = c.execute(
        text(
            "SELECT stored_filename, size_bytes FROM attachments"
            " WHERE stored_filename IS NOT NULL"
        )
    ).fetchall()
    bad = []
    for stored, size in random.sample(rows, 100):
        p = UPLOADS / stored
        if not p.is_file() or p.stat().st_size != size:
            bad.append(stored)
    checks.append(("100 random file sizes", len(rows), f"{len(bad)} bad", not bad))

    # 9. total uploaded bytes == bytes of referenced+present source files
    dst_bytes = sum(p.stat().st_size for p in UPLOADS.iterdir())
    expected = _referenced_bytes(src)
    checks.append(("total copied bytes", expected, dst_bytes, dst_bytes == expected))

print(f"{'CHECK':<44} {'SRC':>14} {'DST':>14}  RESULT")
print("-" * 80)
all_ok = True
for label, s, d, ok in checks:
    all_ok &= bool(ok)
    print(f"{label:<44} {str(s)[:14]:>14} {str(d)[:14]:>14}  {'OK' if ok else 'FAIL'}")
print("-" * 80)
print("ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
sys.exit(0 if all_ok else 1)

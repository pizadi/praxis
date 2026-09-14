#!/usr/bin/env python3
"""Build a synthetic legacy SQLite DB (Django schema) for testing the migration."""

import sqlite3
import sys
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/legacy/db.sqlite3")
OUT.parent.mkdir(parents=True, exist_ok=True)
if OUT.exists():
    OUT.unlink()

con = sqlite3.connect(OUT)
cur = con.cursor()
cur.executescript(
    """
CREATE TABLE patients_tag (id INTEGER PRIMARY KEY, Name varchar(128) UNIQUE);
CREATE TABLE patients_diagnosis (id INTEGER PRIMARY KEY, Name varchar(128) UNIQUE);
CREATE TABLE patients_patient (
    "index" INTEGER PRIMARY KEY AUTOINCREMENT,
    ID varchar(10) UNIQUE,
    First_Name varchar(128) NOT NULL,
    Last_Name varchar(128) NOT NULL,
    Insurance varchar(128),
    Year_of_Birth varchar(4) NOT NULL,
    Phone_Number varchar(20) NOT NULL,
    Gender integer NOT NULL
);
CREATE TABLE patients_appointment (
    "index" INTEGER PRIMARY KEY AUTOINCREMENT,
    Patient_id INTEGER NOT NULL REFERENCES patients_patient("index") ON DELETE CASCADE,
    Appointment_Date datetime NOT NULL,
    Notes text NOT NULL,
    CM text NOT NULL,
    HX text NOT NULL,
    PX text NOT NULL,
    RX text NOT NULL
);
CREATE TABLE patients_transaction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    Related_Appointment_id INTEGER NOT NULL
        REFERENCES patients_appointment("index") ON DELETE CASCADE,
    Description varchar(128) NOT NULL,
    Amount bigint NOT NULL,
    POS bool NOT NULL
);
CREATE TABLE patients_attachfile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    Appointment_id INTEGER NOT NULL
        REFERENCES patients_appointment("index") ON DELETE CASCADE,
    Description varchar(128) NOT NULL,
    File varchar(100),
    Notes text NOT NULL
);
CREATE TABLE patients_patient_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL
);
CREATE TABLE patients_patient_diagnoses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    diagnosis_id INTEGER NOT NULL
);
"""
)

cur.execute("INSERT INTO patients_tag VALUES (1, 'VIP')")
cur.execute("INSERT INTO patients_tag VALUES (2, 'Diabetic')")
cur.execute("INSERT INTO patients_diagnosis VALUES (1, 'Migraine')")
cur.execute("INSERT INTO patients_diagnosis VALUES (2, 'Hypertension')")

cur.executemany(
    "INSERT INTO patients_patient VALUES (?,?,?,?,?,?,?,?)",
    [
        (1, "1234567890", "Parham", "Testi", "Tamin", "1990", "09121234567", 0),
        (2, "0987654321", "Sara", "Sadeghi", None, "1985", "09121112222", 1),
        # dirty row: year with 3 digits + phone with letters (new rules would flag)
        (3, "1111111111", "Ali", "Dirty", None, "990", "abc", 0),
    ],
)
cur.executemany(
    "INSERT INTO patients_appointment VALUES (?,?,?,?,?,?,?,?)",
    [
        (1, 1, "2026-09-10 10:30:00", "n1", "cm1", "hx1", "px1", "rx1"),
        (2, 1, "2026-09-11 09:00:00", "n2", "cm2", "hx2", "px2", "rx2"),
        (3, 2, "2026-09-10 16:00:00", "n3", "", "", "", ""),
    ],
)
cur.executemany(
    "INSERT INTO patients_transaction VALUES (?,?,?,?,?)",
    [
        (1, 1, "visit", 500000, 1),
        (2, 1, "lab", 200000, 0),
        (3, 3, "visit", 300000, 1),
    ],
)
cur.executemany(
    "INSERT INTO patients_attachfile VALUES (?,?,?,?,?)",
    [
        (1, 1, "lab report", "patient_files/1234567890-2026-09-10-10.30.00.pdf", ""),
        (2, 3, "note", "patient_files/0987654321-2026-09-10-16.00.00.jpg", ""),
        (3, 2, "lost file", "patient_files/missing.bin", ""),
    ],
)
cur.executemany(
    "INSERT INTO patients_patient_tags VALUES (?,?,?)",
    [(1, 1, 1), (2, 1, 2), (3, 2, 1)],
)
cur.executemany(
    "INSERT INTO patients_patient_diagnoses VALUES (?,?,?)",
    [(1, 1, 1), (2, 1, 2), (3, 2, 2)],
)
con.commit()
con.close()

# physical files
files = OUT.parent / "patient_files"
files.mkdir(exist_ok=True)
(files / "1234567890-2026-09-10-10.30.00.pdf").write_bytes(b"%PDF-1.4 fake lab report")
(files / "0987654321-2026-09-10-16.00.00.jpg").write_bytes(b"\xff\xd8 jpeg bytes")
# missing.bin intentionally NOT created

print(f"Legacy test DB at {OUT}, files in {files}")

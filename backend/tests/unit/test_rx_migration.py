"""The rx→prescriptions parser (app/services/rx_migration.py) — FROZEN rules.

These rules converted the historical legacy data (Alembic migration AND
scripts/migrate_sqlite.py share the module); changing them rewrites history.
They are pinned here and in tests/parity-adjacent corpus terms — never
"fix" the parser to make these tests pass differently.
"""

import datetime as dt

from app.services.rx_migration import (
    RX_MIN_FREQUENCY,
    extract_name_quantity,
    normalize_item_name,
    overflow_notes,
    plan_rx_migration,
    split_rx_items,
)


def test_split_rx_items():
    assert split_rx_items("asthma, rhinitis\r\nP1 20,doxy") == [
        "asthma",
        "rhinitis",
        "P1 20",
        "doxy",
    ]
    assert split_rx_items("  ") == []
    assert split_rx_items("single") == ["single"]


def test_extract_name_quantity():
    # trailing pure integer → quantity
    assert extract_name_quantity("P1 20") == ("P1", 20)
    assert extract_name_quantity("sym 160") == ("sym", 160)
    # Persian digits normalized first
    assert extract_name_quantity("P1 ۲۰") == ("P1", 20)
    # decimals / fractions / bare numbers stay in the name
    assert extract_name_quantity("alprazolam 1/2") == ("alprazolam 1/2", None)
    assert extract_name_quantity("alprazolam0.5") == ("alprazolam0.5", None)
    assert extract_name_quantity("250") == ("250", None)
    # multi-token: last integer wins, rest of the name is kept
    assert extract_name_quantity("Azithromycin 250 12") == ("Azithromycin 250", 12)
    assert extract_name_quantity("sym 160 PRN") == ("sym 160 PRN", None)


def test_normalize_item_name():
    assert normalize_item_name("  Asthma   2 ") == "asthma 2"
    assert normalize_item_name("COPD.") == "copd"
    assert normalize_item_name("doxy...") == "doxy"
    assert normalize_item_name("---") == ""


def test_plan_dictionary_admission_and_overflow():
    rows = [
        (1, 10, None, "asthma 2, rhinitis"),
        (2, 11, None, "asthma 2"),
        (3, 12, None, "ASTHMA,  rhinitis"),
        (4, 13, None, "i should see ct for bx and repeat pft"),
        (5, 14, None, "---"),
    ]
    planned, dictionary = plan_rx_migration(rows)

    # 'asthma' (3×) and 'rhinitis' (2×) → only asthma passes the ≥3 threshold
    assert RX_MIN_FREQUENCY == 3
    assert dictionary == {"asthma": "asthma"}
    by_appt = {p.appointment_id: p for p in planned}
    # quantities were parsed ("asthma 2" → asthma, qty 2); both "asthma 2"
    # and "ASTHMA," normalize to 'asthma' — deduped, first quantity wins
    assert [(lk.name, lk.quantity) for lk in by_appt[1].links] == [("asthma", 2)]
    # 'rhinitis' seen 2× (< 3) → verbatim overflow
    assert "rhinitis" in by_appt[1].notes_overflow
    # one-off sentence → overflow, never a dictionary entry
    assert "i should see ct for bx and repeat pft" in by_appt[4].notes_overflow
    assert by_appt[4].links == []
    # rx that yields nothing at all produces no prescription
    assert 5 not in by_appt
    # overflow formatting
    assert overflow_notes("some text") == "سایر موارد نسخه قدیمی:\nsome text"
    assert overflow_notes("") == ""


def test_plan_prescribed_at_and_patient():
    at = dt.datetime(2025, 1, 2, 10, 0, tzinfo=dt.UTC)
    planned, _ = plan_rx_migration([(7, 42, at, "doxy, P1 20")])
    assert planned[0].patient_id == 42
    assert planned[0].prescribed_at == at
    assert planned[0].appointment_id == 7
    # 'doxy' seen once → overflow; 'P1 20' → link qty 20 (also below threshold,
    # but the plan keeps links only for admitted names — single-row corpus
    # admits nothing)
    assert planned[0].links == []
    assert planned[0].notes_overflow == "doxy\nP1 20"

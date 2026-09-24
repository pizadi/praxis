"""Machine-enforced freeze for the legacy rx parser: golden v1 corpus."""

import datetime as dt
import json
import pathlib

import pytest

from app.services.rx_migration import (
    RX_MIN_FREQUENCY,
    extract_name_quantity,
    normalize_item_name,
    overflow_notes,
    plan_rx_migration,
    split_rx_items,
)

CORPUS_PATH = pathlib.Path(__file__).parents[3] / "testdata" / "rx_migration_v1.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def test_parser_version_matches_golden_corpus():
    assert CORPUS["min_frequency"] == RX_MIN_FREQUENCY
    from app.services import rx_migration

    assert CORPUS["parser_version"] == rx_migration.PARSER_VERSION


@pytest.mark.parametrize("case", CORPUS["split_cases"], ids=lambda c: repr(c["input"]))
def test_split_cases(case):
    assert split_rx_items(case["input"]) == case["expected"]


@pytest.mark.parametrize(
    "case", CORPUS["name_quantity_cases"], ids=lambda c: repr(c["input"])
)
def test_name_and_quantity_cases(case):
    assert extract_name_quantity(case["input"]) == (case["name"], case["quantity"])


@pytest.mark.parametrize("case", CORPUS["normalize_cases"], ids=lambda c: c["input"])
def test_normalize_cases(case):
    assert normalize_item_name(case["input"]) == case["expected"]


def test_plan_corpus_is_frozen():
    rows = [
        (
            int(appointment_id),
            int(patient_id),
            dt.datetime.fromisoformat(prescribed_at) if prescribed_at else None,
            rx,
        )
        for appointment_id, patient_id, prescribed_at, rx in CORPUS["plan_rows"]
    ]
    planned, dictionary = plan_rx_migration(rows, CORPUS["min_frequency"])
    actual = []
    for item in planned:
        actual.append(
            {
                "appointment_id": item.appointment_id,
                "patient_id": item.patient_id,
                "prescribed_at": (
                    item.prescribed_at.isoformat() if item.prescribed_at else None
                ),
                "links": [
                    {"name": link.name, "quantity": link.quantity}
                    for link in item.links
                ],
                "notes_overflow": item.notes_overflow,
            }
        )
    assert actual == CORPUS["planned"]
    assert dictionary == CORPUS["dictionary"]


def test_overflow_header_is_frozen():
    assert overflow_notes("some text") == "سایر موارد نسخه قدیمی:\nsome text"
    assert overflow_notes("") == ""

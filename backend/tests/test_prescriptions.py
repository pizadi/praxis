"""Structured prescriptions (v1.3) + the legacy rx parser they were migrated with.

Covers:
- rx_migration parsing rules (splitting, quantity extraction, normalization,
  frequency-based dictionary admission, verbatim overflow) — these rules are
  FROZEN: the Alembic data migration and scripts/migrate_sqlite.py both use
  them, so changing them rewrites history.
- the prescriptions API: CRUD, autocomplete, item auto-creation, duplicate
  rejection, permission gating, trash round-trip.
"""

import datetime as dt

from tests.conftest import auth, login, make_user


async def _mk_patient(client, token, nid="1234567890") -> int:
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": nid,
            "first_name": "Test",
            "last_name": "Testi",
            "year_of_birth": "1990",
            "gender": 0,
        },
        headers=auth(token),
    )
    assert r.status_code == 201
    return r.json()["id"]


# --- parser unit tests -------------------------------------------------------------


def test_split_rx_items():
    from app.services.rx_migration import split_rx_items

    assert split_rx_items("asthma, rhinitis\r\nP1 20,doxy") == [
        "asthma",
        "rhinitis",
        "P1 20",
        "doxy",
    ]
    assert split_rx_items("  ") == []
    assert split_rx_items("single") == ["single"]


def test_extract_name_quantity():
    from app.services.rx_migration import extract_name_quantity

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
    from app.services.rx_migration import normalize_item_name

    assert normalize_item_name("  Asthma   2 ") == "asthma 2"
    assert normalize_item_name("COPD.") == "copd"
    assert normalize_item_name("doxy...") == "doxy"
    assert normalize_item_name("---") == ""


def test_plan_dictionary_admission_and_overflow():
    from app.services.rx_migration import RX_MIN_FREQUENCY, overflow_notes, plan_rx_migration

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
    from app.services.rx_migration import plan_rx_migration

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


# --- API tests -----------------------------------------------------------------------


async def test_prescription_crud_and_auto_create(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)

    # create with a mix of existing/unknown names + quantities
    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={
            "items": [
                {"name": "P1", "quantity": 20},
                {"name": "doxy"},
                {"item_id": 999999},
            ],
            "notes": "بعد از غذا",
        },
        headers=auth(token),
    )
    assert r.status_code == 422  # unknown item_id

    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={
            "items": [{"name": "P1", "quantity": 20}, {"name": "doxy"}],
            "notes": "بعد از غذا",
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == pid
    assert body["created_by_username"] == "admin"
    assert body["notes"] == "بعد از غذا"
    names = {i["item_name"]: i["quantity"] for i in body["items"]}
    assert names == {"P1": 20, "doxy": None}

    # the unknown names were auto-registered in the dictionary
    r = await client.get("/api/v1/prescription-items", headers=auth(token))
    items = {i["name"] for i in r.json()["items"]}
    assert {"P1", "doxy"} <= items

    # case-insensitive match reuses the dictionary (no dupes)
    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={"items": [{"name": "  p1 "}]},
        headers=auth(token),
    )
    assert r.status_code == 201
    assert [i["item_id"] for i in r.json()["items"]] == [
        i["item_id"] for i in body["items"] if i["item_name"] == "P1"
    ]
    r = await client.get("/api/v1/prescription-items", headers=auth(token))
    assert r.json()["total"] == 2

    # duplicate within one prescription → 409
    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={"items": [{"name": "doxy"}, {"name": "doxy", "quantity": 2}]},
        headers=auth(token),
    )
    assert r.status_code == 409

    # list newest-first, with item names resolved
    r = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["total"] == 2

    # PATCH: replace items, edit notes
    listed = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(token))
    rx2 = listed.json()["items"][0]
    r = await client.patch(
        f"/api/v1/prescriptions/{rx2['id']}",
        json={"items": [{"name": "co amoxi", "quantity": 1}], "notes": "ویرایش شد"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert [i["item_name"] for i in r.json()["items"]] == ["co amoxi"]
    assert r.json()["notes"] == "ویرایش شد"

    # DELETE → soft → trash → restore keeps links
    r = await client.delete(f"/api/v1/prescriptions/{rx2['id']}", headers=auth(token))
    assert r.status_code == 204
    r = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(token))
    assert r.json()["total"] == 1
    r = await client.get("/api/v1/admin/trash/prescriptions", headers=auth(token))
    assert r.json()["total"] == 1
    r = await client.post(
        f"/api/v1/admin/trash/prescriptions/{rx2['id']}/restore", headers=auth(token)
    )
    assert r.status_code == 200
    r = await client.get(f"/api/v1/prescriptions/{rx2['id']}", headers=auth(token))
    assert r.status_code == 200
    assert [i["item_name"] for i in r.json()["items"]] == ["co amoxi"]


async def test_prescription_item_autocomplete_and_rename(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={"items": [{"name": "Seroflo 250"}, {"name": "NAC"}]},
        headers=auth(token),
    )

    # search filter
    r = await client.get(
        "/api/v1/prescription-items", params={"q": "ser"}, headers=auth(token)
    )
    assert [i["name"] for i in r.json()["items"]] == ["Seroflo 250"]

    # rename propagates (links reference the item id)
    item_id = r.json()["items"][0]["id"]
    r = await client.patch(
        f"/api/v1/prescription-items/{item_id}",
        json={"name": "Seroflo 250 Diskus"},
        headers=auth(token),
    )
    assert r.status_code == 200
    r = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(token))
    assert r.json()["items"][0]["items"][0]["item_name"] == "Seroflo 250 Diskus"

    # duplicate rename → 409
    r = await client.patch(
        f"/api/v1/prescription-items/{item_id}", json={"name": "nac"}, headers=auth(token)
    )
    assert r.status_code == 409

    # soft delete hides it from autocomplete; existing links are kept
    r = await client.delete(f"/api/v1/prescription-items/{item_id}", headers=auth(token))
    assert r.status_code == 204
    r = await client.get("/api/v1/prescription-items", headers=auth(token))
    assert "Seroflo 250 Diskus" not in {i["name"] for i in r.json()["items"]}
    r = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(token))
    assert len(r.json()["items"][0]["items"]) == 2
    # trash round-trip
    r = await client.post(
        f"/api/v1/admin/trash/prescription_items/{item_id}/restore", headers=auth(token)
    )
    assert r.status_code == 200


async def test_prescription_permission_gating(client):
    token, _ = await login(client)
    await make_user(client, token, "recep1", role="receptionist")
    await make_user(client, token, "drhouse", role="doctor")
    recep, _ = await login(client, "recep1", "passw0rd123")
    doctor, _ = await login(client, "drhouse", "passw0rd123")
    pid = await _mk_patient(client, token)

    # receptionist: no read, no write
    r = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(recep))
    assert r.status_code == 403
    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={"items": [{"name": "x"}]},
        headers=auth(recep),
    )
    assert r.status_code == 403
    r = await client.get("/api/v1/prescription-items", headers=auth(recep))
    assert r.status_code == 403

    # doctor: read + write
    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={"items": [{"name": "P1", "quantity": 1}]},
        headers=auth(doctor),
    )
    assert r.status_code == 201
    rx = r.json()
    r = await client.get(f"/api/v1/patients/{pid}/prescriptions", headers=auth(doctor))
    assert r.status_code == 200
    assert r.json()["items"][0]["created_by_username"] == "drhouse"

    # doctor cannot purge trash (admin-only) — delete stays soft
    r = await client.delete(f"/api/v1/prescriptions/{rx['id']}", headers=auth(doctor))
    assert r.status_code == 204
    r = await client.delete(
        f"/api/v1/admin/trash/prescriptions/{rx['id']}", headers=auth(doctor)
    )
    assert r.status_code == 403

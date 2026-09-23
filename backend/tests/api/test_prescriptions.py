"""Prescriptions API: CRUD, autocomplete, dictionary management, perms.

The FROZEN rx→prescriptions parser lives in unit/test_rx_migration.py.
"""

import datetime as dt

from tests.conftest import auth, login, make_user
from tests.factories import mk_patient

# --- API tests -----------------------------------------------------------------------


async def test_prescription_crud_and_auto_create(client):
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]

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


async def test_patch_prescription_keeps_same_items(client):
    """PATCH keeping the SAME item pairs (only quantity/order changed) must
    not hit uq_prescription_item_links_pair — kept pairs are delete+inserted
    in one transaction."""
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={"items": [{"name": "P1", "quantity": 20}, {"name": "doxy"}]},
        headers=auth(token),
    )
    assert r.status_code == 201
    rx_id = r.json()["id"]

    # same items, changed quantities + order
    r = await client.patch(
        f"/api/v1/prescriptions/{rx_id}",
        json={"items": [{"name": "doxy", "quantity": 2}, {"name": "P1", "quantity": 5}]},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    got = {i["item_name"]: i["quantity"] for i in r.json()["items"]}
    assert got == {"P1": 5, "doxy": 2}

    # ...and a repeat replace that keeps a pair again
    r = await client.patch(
        f"/api/v1/prescriptions/{rx_id}",
        json={"items": [{"name": "P1"}]},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert [(i["item_name"], i["quantity"]) for i in r.json()["items"]] == [("P1", None)]


async def test_prescription_item_autocomplete_and_rename(client):
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
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


async def test_prescription_item_direct_create(client):
    """POST /prescription-items: the dictionary normally self-registers from
    prescriptions; the panel can also register items directly."""
    token, _ = await login(client)

    # create → 201, audited
    r = await client.post(
        "/api/v1/prescription-items", json={"name": "  آسموتول  "}, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "آسموتول"  # stripped
    item_id = r.json()["id"]
    r = await client.get("/api/v1/admin/audit", params={"limit": 50}, headers=auth(token))
    entry = next(
        e for e in r.json()["items"]
        if e["entity_type"] == "prescription_item" and e["action"] == "create"
    )
    assert entry["summary"] == "آسموتول"

    # case-insensitive duplicate → 409 (same semantics as the auto-registration)
    r = await client.post(
        "/api/v1/prescription-items", json={"name": "آسموتول"}, headers=auth(token)
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "name_taken"
    r = await client.post(
        "/api/v1/prescription-items", json={"name": "  aspirin  "}, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/v1/prescription-items", json={"name": "ASPIRIN"}, headers=auth(token)
    )
    assert r.status_code == 409

    # blank name → 422
    r = await client.post("/api/v1/prescription-items", json={"name": "   "}, headers=auth(token))
    assert r.status_code == 422

    # a soft-deleted name is reusable (partial unique index: live rows only)
    r = await client.delete(f"/api/v1/prescription-items/{item_id}", headers=auth(token))
    assert r.status_code == 204
    r = await client.post(
        "/api/v1/prescription-items", json={"name": "آسموتول"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"] != item_id

    # the created item feeds prescription autocomplete (no auto-registration needed)
    pid = (await mk_patient(client, token))["id"]
    r = await client.post(
        f"/api/v1/patients/{pid}/prescriptions",
        json={"items": [{"item_id": r.json()["id"]}]},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text


async def test_prescription_permission_gating(client):
    token, _ = await login(client)
    await make_user(client, token, "recep1", role="receptionist")
    await make_user(client, token, "drhouse", role="doctor")
    recep, _ = await login(client, "recep1", "passw0rd123")
    doctor, _ = await login(client, "drhouse", "passw0rd123")
    pid = (await mk_patient(client, token))["id"]

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
    # direct dictionary creation is prescriptions.write too
    r = await client.post("/api/v1/prescription-items", json={"name": "x"}, headers=auth(recep))
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


async def test_prescriptions_date_filter(client):
    """date= restricts to one APP_TIMEZONE day (prescribed_at) — the
    appointment view's same-day prescriptions tab."""

    from app.db.session import APP_TZ

    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]

    # one pre-dated prescription, one for "now" (defaults to the current time)
    for at in ("2020-01-01T10:00:00+03:30", None):
        body: dict = {"items": [{"name": "P1"}]}
        if at:
            body["prescribed_at"] = at
        r = await client.post(
            f"/api/v1/patients/{pid}/prescriptions", json=body, headers=auth(token)
        )
        assert r.status_code == 201, r.text

    today = dt.datetime.now(APP_TZ).date().isoformat()
    r = await client.get(
        f"/api/v1/patients/{pid}/prescriptions",
        params={"date": today},
        headers=auth(token),
    )
    assert r.json()["total"] == 1

    r = await client.get(
        f"/api/v1/patients/{pid}/prescriptions",
        params={"date": "2020-01-01"},
        headers=auth(token),
    )
    assert r.json()["total"] == 1

    r = await client.get(
        f"/api/v1/patients/{pid}/prescriptions",
        params={"date": "2019-12-31"},
        headers=auth(token),
    )
    assert r.json()["total"] == 0

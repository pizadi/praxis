"""Day-wide payments panel: GET /payments date filtering and visibility."""

import datetime as dt

from app.db.session import APP_TZ
from tests.conftest import auth, login, make_user


def _today() -> str:
    """The API defaults to «today in APP_TZ» — the tests must use the same
    day (UTC and Tehran dates differ between ~20:30 and 00:00 UTC)."""
    return dt.datetime.now(APP_TZ).strftime("%Y-%m-%d")


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


async def _mk_appt(client, token, patient_id, at) -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/appointments",
        json={"scheduled_at": at},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _mk_txn(client, token, appt_id, description, amount, pos) -> dict:
    r = await client.post(
        f"/api/v1/appointments/{appt_id}/transactions",
        json={"description": description, "amount": amount, "pos": pos},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_today_payments_day_filtering(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)

    today = _today()
    # "today" in Tehran may differ from UTC — pick an in-day appointment time
    a1 = await _mk_appt(client, token, pid, f"{today}T09:00:00+03:30")
    a2 = await _mk_appt(client, token, pid, f"{today}T18:00:00+03:30")
    # a payment from another day must not leak in
    a3 = await _mk_appt(client, token, pid, "2020-05-05T10:00:00+03:30")

    t1 = await _mk_txn(client, token, a1["id"], "ویزیت", 300000, True)
    t2 = await _mk_txn(client, token, a2["id"], "اسپیرو", 150000, False)
    await _mk_txn(client, token, a3["id"], "ویزیت قدیمی", 100000, True)

    r = await client.get("/api/v1/payments", headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    amounts = {i["amount"] for i in body["items"]}
    assert amounts == {300000, 150000}
    # newest appointment first
    assert body["items"][0]["appointment_id"] == a2["id"]

    # patient fields present
    item = body["items"][0]
    assert item["patient_id"] == pid
    assert item["patient_first_name"] == "Test"
    assert item["patient_last_name"] == "Testi"

    # explicit date param filters to that day
    r = await client.get("/api/v1/payments", params={"date": "2020-05-05"}, headers=auth(token))
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] != t1["id"]
    assert r.json()["items"][0]["amount"] == 100000

    # pos flag round-trips (cash vs card)
    pos_flags = {i["id"]: i["pos"] for i in body["items"]}
    assert pos_flags[t1["id"]] is True
    assert pos_flags[t2["id"]] is False


async def test_today_payments_soft_delete_visibility(client):
    token, _ = await login(client)
    pid = await _mk_patient(client, token)
    today = _today()
    a1 = await _mk_appt(client, token, pid, f"{today}T09:00:00+03:30")
    a2 = await _mk_appt(client, token, pid, f"{today}T12:00:00+03:30")
    await _mk_txn(client, token, a1["id"], "ویزیت", 100000, True)
    await _mk_txn(client, token, a2["id"], "ویزیت", 200000, True)

    r = await client.get("/api/v1/payments", headers=auth(token))
    assert r.json()["total"] == 2

    # deleting the appointment hides its payments from the day view
    await client.delete(f"/api/v1/appointments/{a1['id']}", headers=auth(token))
    r = await client.get("/api/v1/payments", headers=auth(token))
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["amount"] == 200000


async def test_payments_receptionist_allowed(client):
    admin, _ = await login(client)
    await make_user(client, admin, "recep1", role="receptionist")
    recep_token, _ = await login(client, "recep1", "passw0rd123")
    r = await client.get("/api/v1/payments", headers=auth(recep_token))
    assert r.status_code == 200
    assert r.json()["total"] == 0

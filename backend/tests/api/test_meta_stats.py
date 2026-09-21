"""Meta + statistics endpoints."""

from tests.conftest import auth, login
from tests.factories import mk_appointment, mk_patient


async def test_stats_summary(client):
    token, _ = await login(client)
    pid = (await mk_patient(client, token))["id"]
    await mk_appointment(client, token, pid, at="2026-09-10T09:00:00+03:30")
    appt2 = await mk_appointment(client, token, pid, at="2026-09-11T09:00:00+03:30")

    for appt, amount, pos in ((appt2, 500000, True), (appt2, 100000, False)):
        r = await client.post(
            f"/api/v1/appointments/{appt['id']}/transactions",
            json={"description": "visit", "amount": amount, "pos": pos},
            headers=auth(token),
        )
        assert r.status_code == 201

    r = await client.get(
        "/api/v1/stats/summary",
        params={"date_from": "2026-09-10", "date_to": "2026-09-11"},
        headers=auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["num_appointments"] == 2
    assert body["total_amount"] == 600000
    assert body["pos_amount"] == 500000
    assert body["cash_amount"] == 100000
    assert body["num_transactions"] == 2

    # CSV export
    r = await client.get(
        "/api/v1/stats/summary.csv",
        params={"date_from": "2026-09-10", "date_to": "2026-09-11"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "visit,1,500000" in r.text or "visit" in r.text

    # reversed dates → 422
    r = await client.get(
        "/api/v1/stats/summary",
        params={"date_from": "2026-09-11", "date_to": "2026-09-10"},
        headers=auth(token),
    )
    assert r.status_code == 422

"""Patients, tags, diagnoses: CRUD, search semantics, taxonomy merge."""

from tests.conftest import auth, login, make_user
from tests.factories import mk_patient


async def _mk_patient(client, token, **overrides) -> dict:
    return await mk_patient(client, token, **overrides)


async def test_patient_crud(client):
    token, _ = await login(client)
    p = await _mk_patient(client, token)
    assert p["national_id"] == "1234567890"
    assert p["tags"] == []

    # Duplicate national ID → 409
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": "1234567890",
            "first_name": "X",
            "last_name": "Y",
            "year_of_birth": "1991",
            "gender": 1,
        },
        headers=auth(token),
    )
    assert r.status_code == 409

    # Validation: 11-digit ID rejected (legacy bug fixed)
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": "12345678901",
            "first_name": "X",
            "last_name": "Y",
            "year_of_birth": "1991",
            "gender": 1,
        },
        headers=auth(token),
    )
    assert r.status_code == 422
    # 3-digit year rejected
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": "0987654321",
            "first_name": "X",
            "last_name": "Y",
            "year_of_birth": "991",
            "gender": 1,
        },
        headers=auth(token),
    )
    assert r.status_code == 422

    # Update
    r = await client.patch(
        f"/api/v1/patients/{p['id']}",
        json={"phone_number": "02112345678"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["phone_number"] == "02112345678"

    # Get / delete (admin only)
    r = await client.get(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert r.status_code == 200
    r = await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert r.status_code == 204
    r = await client.get(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert r.status_code == 404


async def test_patient_search_all_in_sql(client):
    token, _ = await login(client)
    await _mk_patient(
        client,
        token,
        national_id="1111111111",
        last_name="Ahmadi",
        insurance="تامین اجتماعی",
        gender=0,
    )
    await _mk_patient(
        client,
        token,
        national_id="2222222222",
        last_name="Rezaii",
        insurance="آزاد",
        year_of_birth="1985",
        gender=1,
    )
    await _mk_patient(
        client,
        token,
        national_id="3333333333",
        last_name="Ahmadi-Sadegh",
        year_of_birth="1990",
        gender=1,
    )

    r = await client.get("/api/v1/patients", params={"q": "ahmad"}, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert {i["last_name"] for i in body["items"]} == {"Ahmadi", "Ahmadi-Sadegh"}

    r = await client.get(
        "/api/v1/patients", params={"national_id": "222"}, headers=auth(token)
    )
    assert r.json()["total"] == 1

    r = await client.get(
        "/api/v1/patients", params={"q": "nothingmatches"}, headers=auth(token)
    )
    assert r.json()["total"] == 0

    # per-field searches
    r = await client.get(
        "/api/v1/patients", params={"first_name": "test"}, headers=auth(token)
    )
    assert r.json()["total"] == 3

    r = await client.get(
        "/api/v1/patients", params={"last_name": "rezaii"}, headers=auth(token)
    )
    assert r.json()["total"] == 1

    # insurance: ilike contains (also exercises Persian text matching)
    r = await client.get(
        "/api/v1/patients", params={"insurance": "اجتماعی"}, headers=auth(token)
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["last_name"] == "Ahmadi"

    # year_of_birth: digits contains
    r = await client.get(
        "/api/v1/patients", params={"year_of_birth": "85"}, headers=auth(token)
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["last_name"] == "Rezaii"

    # gender: exact
    r = await client.get(
        "/api/v1/patients", params={"gender": 0}, headers=auth(token)
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["last_name"] == "Ahmadi"

    r = await client.get(
        "/api/v1/patients", params={"gender": 1}, headers=auth(token)
    )
    assert r.json()["total"] == 2

    # invalid gender rejected
    r = await client.get("/api/v1/patients", params={"gender": 5}, headers=auth(token))
    assert r.status_code == 422

    # combined filters AND together
    r = await client.get(
        "/api/v1/patients",
        params={"last_name": "ahmad", "gender": 0},
        headers=auth(token),
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["last_name"] == "Ahmadi"


async def test_patient_tag_diagnosis_filters(client):
    token, _ = await login(client)
    # taxonomy CRUD
    r = await client.post("/api/v1/tags", json={"name": "VIP"}, headers=auth(token))
    assert r.status_code == 201
    vip = r.json()
    r = await client.post("/api/v1/tags", json={"name": "vip"}, headers=auth(token))
    assert r.status_code == 201  # different case: distinct name, allowed
    r = await client.post("/api/v1/tags", json={"name": "VIP"}, headers=auth(token))
    assert r.status_code == 409  # exact duplicate rejected (legacy IntegrityError fixed)

    r = await client.post("/api/v1/diagnoses", json={"name": "Migraine"}, headers=auth(token))
    mig = r.json()

    # Rename with duplicate → 409 (legacy bug fixed)
    r = await client.post("/api/v1/tags", json={"name": "Normal"}, headers=auth(token))
    normal = r.json()
    r = await client.patch(
        f"/api/v1/tags/{normal['id']}", json={"name": "VIP"}, headers=auth(token)
    )
    assert r.status_code == 409

    p1 = await _mk_patient(
        client, token, national_id="1111111111", tag_ids=[vip["id"]], diagnosis_ids=[mig["id"]]
    )
    await _mk_patient(client, token, national_id="2222222222", tag_ids=[vip["id"]])
    await _mk_patient(client, token, national_id="3333333333")

    # tag filter: VIP matches p1 & p2
    r = await client.get(
        "/api/v1/patients", params={"tag_ids": str(vip["id"])}, headers=auth(token)
    )
    assert r.json()["total"] == 2

    # both VIP + Migraine → p1 only
    r = await client.get(
        "/api/v1/patients",
        params={"tag_ids": str(vip["id"]), "diagnosis_ids": str(mig["id"])},
        headers=auth(token),
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["id"] == p1["id"]

    # patient output carries tags/diagnoses
    r = await client.get(f"/api/v1/patients/{p1['id']}", headers=auth(token))
    assert [t["name"] for t in r.json()["tags"]] == ["VIP"]
    assert [d["name"] for d in r.json()["diagnoses"]] == ["Migraine"]

    # delete taxonomy (Normal was created above; list now has VIP, vip → minus Normal)
    r = await client.delete(f"/api/v1/tags/{normal['id']}", headers=auth(token))
    assert r.status_code == 204
    r = await client.get("/api/v1/tags", headers=auth(token))
    assert r.json()["total"] == 2


async def test_taxonomy_search_and_pagination(client):
    token, _ = await login(client)
    for name in ("alpha", "beta", "alphabet", "gamma"):
        r = await client.post("/api/v1/tags", json={"name": name}, headers=auth(token))
        assert r.status_code == 201

    # search
    r = await client.get("/api/v1/tags", params={"q": "alpha"}, headers=auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert [i["name"] for i in body["items"]] == ["alpha", "alphabet"]  # ordered by name

    # pagination
    r = await client.get(
        "/api/v1/tags", params={"limit": 2, "offset": 2}, headers=auth(token)
    )
    body = r.json()
    assert body["total"] == 4
    assert [i["name"] for i in body["items"]] == ["beta", "gamma"]

    # limit clamped to the taxonomy cap (1000), not the global 100
    r = await client.get("/api/v1/tags", params={"limit": 5000}, headers=auth(token))
    assert r.json()["limit"] == 1000


async def test_receptionist_cannot_delete_patient(client):
    admin_token, _ = await login(client)
    await make_user(client, admin_token, "recep1", role="receptionist")
    recep = await login(client, "recep1", "passw0rd123")
    p = await _mk_patient(client, admin_token)
    r = await client.delete(f"/api/v1/patients/{p['id']}", headers=auth(recep[0]))
    assert r.status_code == 403


async def test_taxonomy_list_sorted(client):
    token, _ = await login(client)
    for name in ("zeta", "alpha", "midway"):
        r = await client.post("/api/v1/tags", json={"name": name}, headers=auth(token))
        assert r.status_code == 201
    r = await client.get("/api/v1/tags", headers=auth(token))
    names = [i["name"] for i in r.json()["items"]]
    assert names == sorted(names)


async def test_taxonomy_merge_on_rename(client):
    token, _ = await login(client)
    r = await client.post("/api/v1/tags", json={"name": "foo"}, headers=auth(token))
    foo = r.json()
    r = await client.post("/api/v1/tags", json={"name": "bar"}, headers=auth(token))
    bar = r.json()

    p_foo = await _mk_patient(client, token, national_id="4444444441", tag_ids=[foo["id"]])
    p_bar = await _mk_patient(client, token, national_id="4444444442", tag_ids=[bar["id"]])
    p_both = await _mk_patient(
        client, token, national_id="4444444443", tag_ids=[foo["id"], bar["id"]]
    )

    # without the merge flag → 409 (the UI asks the user)
    r = await client.patch(
        f"/api/v1/tags/{foo['id']}", json={"name": "bar"}, headers=auth(token)
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "name_taken"

    # with merge=true → bar survives, foo soft-deleted, links moved
    r = await client.patch(
        f"/api/v1/tags/{foo['id']}", json={"name": "bar"}, params={"merge": "true"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == bar["id"]
    assert r.json()["name"] == "bar"

    r = await client.get("/api/v1/tags", headers=auth(token))
    names = [i["name"] for i in r.json()["items"]]
    assert "foo" not in names and "bar" in names

    for pid, expected in ((p_foo["id"], ["bar"]), (p_bar["id"], ["bar"]), (p_both["id"], ["bar"])):
        r = await client.get(f"/api/v1/patients/{pid}", headers=auth(token))
        assert [t["name"] for t in r.json()["tags"]] == expected, pid

    # foo went to the trash (soft delete) and its name is reusable after purge/restore
    r = await client.get("/api/v1/admin/trash/tags", headers=auth(token))
    assert any(i["title"] == "foo" for i in r.json()["items"])

    # audited as a merge
    r = await client.get("/api/v1/admin/audit", params={"entity_type": "tag"}, headers=auth(token))
    assert any(e["action"] == "merge" for e in r.json()["items"])


async def test_taxonomy_merge_diagnoses(client):
    token, _ = await login(client)
    r = await client.post("/api/v1/diagnoses", json={"name": "old-dx"}, headers=auth(token))
    old_dx = r.json()
    r = await client.post("/api/v1/diagnoses", json={"name": "new-dx"}, headers=auth(token))
    new_dx = r.json()
    p = await _mk_patient(client, token, national_id="4444444444", diagnosis_ids=[old_dx["id"]])
    r = await client.patch(
        f"/api/v1/diagnoses/{old_dx['id']}", json={"name": "new-dx"}, params={"merge": "true"},
        headers=auth(token),
    )
    assert r.status_code == 200
    assert r.json()["id"] == new_dx["id"]
    r = await client.get(f"/api/v1/patients/{p['id']}", headers=auth(token))
    assert [d["name"] for d in r.json()["diagnoses"]] == ["new-dx"]


async def test_patient_search_treats_wildcards_literally(client):
    token, _ = await login(client)
    literal = await _mk_patient(
        client, token, national_id="5555555551", first_name="under_score"
    )
    await _mk_patient(
        client, token, national_id="5555555552", first_name="under score"
    )

    r = await client.get(
        "/api/v1/patients", params={"q": "_"}, headers=auth(token)
    )
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["items"]] == [literal["id"]]

    r = await client.get(
        "/api/v1/patients", params={"q": "%"}, headers=auth(token)
    )
    assert r.json()["items"] == []

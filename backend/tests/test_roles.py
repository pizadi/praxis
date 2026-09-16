"""Roles & permission catalog tests."""

from tests.conftest import auth, login, make_user


async def get_role_id(client, token: str, name: str) -> int:
    roles = (await client.get("/api/v1/roles", headers=auth(token))).json()
    return next(r["id"] for r in roles["items"] if r["name"] == name)


async def test_system_roles_seeded(client):
    token = (await login(client))[0]
    r = await client.get("/api/v1/roles", headers=auth(token))
    assert r.status_code == 200
    by_name = {r_["name"]: r_ for r_ in r.json()["items"]}
    assert set(by_name) >= {"admin", "doctor", "receptionist"}
    assert by_name["admin"]["is_system"] is True
    assert "users.manage" in by_name["admin"]["permissions"]
    assert "medical_notes.view" in by_name["doctor"]["permissions"]
    assert "medical_notes.view" not in by_name["receptionist"]["permissions"]


async def test_permission_catalog_endpoint(client):
    token = (await login(client))[0]
    r = await client.get("/api/v1/roles/permissions", headers=auth(token))
    assert r.status_code == 200
    groups = r.json()
    keys = [i["key"] for g in groups for i in g["items"]]
    assert "patients.read" in keys
    assert all(g["group"] and g["items"] for g in groups)


async def test_role_crud_and_enforcement(client):
    token = (await login(client))[0]

    # create a role that can only read patients
    r = await client.post(
        "/api/v1/roles",
        json={"name": "reader", "permissions": ["patients.read"]},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]

    r = await client.post(
        "/api/v1/users",
        json={"username": "reader1", "password": "passw0rd123", "role_id": role_id},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    user_perms = r.json()["permissions"]
    assert user_perms == ["patients.read"]

    reader = await login(client, "reader1", "passw0rd123")

    # can list patients…
    r = await client.get("/api/v1/patients", headers=auth(reader[0]))
    assert r.status_code == 200
    # …but cannot create one
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": "0012345678",
            "first_name": "الف",
            "last_name": "ب",
            "year_of_birth": "1370",
            "gender": 0,
        },
        headers=auth(reader[0]),
    )
    assert r.status_code == 403
    # …and cannot manage roles
    r = await client.get("/api/v1/roles", headers=auth(reader[0]))
    assert r.status_code == 403

    # grant patients.create → enforcement changes immediately (no re-login)
    r = await client.patch(
        f"/api/v1/roles/{role_id}",
        json={"permissions": ["patients.read", "patients.create"]},
        headers=auth(token),
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": "0012345678",
            "first_name": "الف",
            "last_name": "ب",
            "year_of_birth": "1370",
            "gender": 0,
        },
        headers=auth(reader[0]),
    )
    assert r.status_code == 201


async def test_role_validation(client):
    token = (await login(client))[0]
    # unknown permission key → 422
    r = await client.post(
        "/api/v1/roles", json={"name": "bad", "permissions": ["not.a.perm"]},
        headers=auth(token),
    )
    assert r.status_code == 422
    # duplicate name → 409
    r = await client.post(
        "/api/v1/roles", json={"name": "doctor", "permissions": []},
        headers=auth(token),
    )
    assert r.status_code == 409


async def test_admin_role_locked(client):
    token = (await login(client))[0]
    admin_id = await get_role_id(client, token, "admin")
    r = await client.patch(
        f"/api/v1/roles/{admin_id}", json={"permissions": []}, headers=auth(token)
    )
    assert r.status_code == 409
    r = await client.delete(f"/api/v1/roles/{admin_id}", headers=auth(token))
    assert r.status_code == 409
    # other system roles cannot be deleted either, but their perms are editable
    doc_id = await get_role_id(client, token, "doctor")
    r = await client.delete(f"/api/v1/roles/{doc_id}", headers=auth(token))
    assert r.status_code == 409


async def test_role_delete_in_use(client):
    token = (await login(client))[0]
    r = await client.post(
        "/api/v1/roles", json={"name": "temp", "permissions": ["patients.read"]},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    role_id = r.json()["id"]
    await make_user(client, token, "tempuser", role="temp")

    # in use → 409
    r = await client.delete(f"/api/v1/roles/{role_id}", headers=auth(token))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "role_in_use"

    # reassign the user, then delete works and the row lands in the trash
    users = (await client.get("/api/v1/users?limit=100", headers=auth(token))).json()
    uid = next(u["id"] for u in users["items"] if u["username"] == "tempuser")
    recep_id = await get_role_id(client, token, "receptionist")
    r = await client.patch(f"/api/v1/users/{uid}", json={"role_id": recep_id},
                           headers=auth(token))
    assert r.status_code == 200
    r = await client.delete(f"/api/v1/roles/{role_id}", headers=auth(token))
    assert r.status_code == 204
    trash = (
        await client.get("/api/v1/admin/trash/roles", headers=auth(token))
    ).json()
    assert any(item["id"] == role_id for item in trash["items"])

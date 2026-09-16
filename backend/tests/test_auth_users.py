"""Auth, users, and role-based access tests."""

from tests.conftest import auth, login, make_user


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["db"] is True


async def test_login_bad_credentials(client):
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert r.status_code == 401
    # Same error for unknown user (no username enumeration)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "ghost", "password": "wrong"}
    )
    assert r.status_code == 401


async def test_login_and_me(client):
    access, _ = await login(client)
    r = await client.get("/api/v1/auth/me", headers=auth(access))
    assert r.status_code == 200
    assert r.json()["username"] == "admin"
    assert r.json()["role_name"] == "admin"
    assert "users.manage" in r.json()["permissions"]


async def test_refresh_rotation(client):
    access, refresh = await login(client)
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    new_pair = r.json()
    assert new_pair["refresh_token"] != refresh
    # Old refresh token must now be rejected (single use)
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401
    # New one works
    r = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new_pair["refresh_token"]}
    )
    assert r.status_code == 200


async def test_access_rejects_refresh_token(client):
    _, refresh = await login(client)
    r = await client.get("/api/v1/auth/me", headers=auth(refresh))
    assert r.status_code == 401


async def test_logout_revokes_refresh(client):
    _, refresh = await login(client)
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    assert r.status_code == 204
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401


async def test_endpoints_require_auth(client):
    for method, path in (
        ("get", "/api/v1/patients"),
        ("get", "/api/v1/tags"),
        ("get", "/api/v1/stats/summary"),
    ):
        r = await getattr(client, method)(path)
        assert r.status_code == 401, path


async def test_user_crud_and_roles(client):
    admin = await login(client)
    token = admin[0]
    await make_user(client, token, "drhouse", role="doctor")
    await make_user(client, token, "recep1", role="receptionist")

    # Admin lists users
    r = await client.get("/api/v1/users", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["total"] == 3

    # Duplicate username → 409
    roles = (await client.get("/api/v1/roles", headers=auth(token))).json()
    doctor_role_id = next(r["id"] for r in roles["items"] if r["name"] == "doctor")
    r = await client.post(
        "/api/v1/users",
        json={"username": "drhouse", "password": "passw0rd123", "role_id": doctor_role_id},
        headers=auth(token),
    )
    assert r.status_code == 409

    # Non-admin cannot list users
    dr = await login(client, "drhouse", "passw0rd123")
    r = await client.get("/api/v1/users", headers=auth(dr[0]))
    assert r.status_code == 403

    # Deactivate receptionist → login fails
    users = (await client.get("/api/v1/users?limit=100", headers=auth(token))).json()
    recep_id = next(u["id"] for u in users["items"] if u["username"] == "recep1")
    r = await client.patch(
        f"/api/v1/users/{recep_id}", json={"is_active": False}, headers=auth(token)
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep1", "password": "passw0rd123"}
    )
    assert r.status_code == 401

    # Cannot delete yourself
    me = (await client.get("/api/v1/auth/me", headers=auth(token))).json()
    r = await client.delete(f"/api/v1/users/{me['id']}", headers=auth(token))
    assert r.status_code == 422

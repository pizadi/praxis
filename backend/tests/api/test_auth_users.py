"""Auth, users, and role-based access tests."""

import datetime as dt

from sqlalchemy import text

from tests.conftest import auth, login, make_user


def csrf_headers(client) -> dict[str, str]:
    token = client.cookies.get("praxis_csrf")
    assert token
    return {"X-CSRF-Token": token}


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
    access, refresh = await login(client)
    raw_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    refresh_cookies = [
        header for header in raw_login.headers.get_list("set-cookie")
        if header.startswith("praxis_refresh=")
    ]
    assert len(refresh_cookies) == 1
    assert "HttpOnly" in refresh_cookies[0]
    assert "Path=/api/v1/auth" in refresh_cookies[0]
    assert "SameSite=strict" in refresh_cookies[0]
    me = await client.get("/api/v1/auth/me", headers=auth(access))
    assert refresh not in me.text
    assert "refresh_token" not in raw_login.json()
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["role_name"] == "admin"
    assert "users.manage" in me.json()["permissions"]


async def test_refresh_rotation(client):
    _, old_refresh = await login(client)
    old_csrf = client.cookies.get("praxis_csrf")
    assert old_csrf

    r = await client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": old_csrf}
    )
    assert r.status_code == 200
    new_refresh = r.cookies.get("praxis_refresh")
    new_csrf = r.cookies.get("praxis_csrf")
    assert new_refresh and new_refresh != old_refresh
    assert new_csrf and new_csrf != old_csrf
    assert "refresh_token" not in r.json()

    # The old refresh cookie must now be rejected (single use).
    client.cookies.clear()
    client.cookies.set(
        "praxis_refresh", old_refresh, domain="test.local", path="/api/v1/auth"
    )
    client.cookies.set("praxis_csrf", new_csrf or "", domain="test.local", path="/")
    r = await client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": new_csrf or ""}
    )
    assert r.status_code == 401

    # The newly rotated cookie works.
    await login(client)
    current_csrf = client.cookies.get("praxis_csrf")
    r = await client.post(
        "/api/v1/auth/refresh", headers={"X-CSRF-Token": current_csrf or ""}
    )
    assert r.status_code == 200


async def test_access_rejects_refresh_token(client):
    _, refresh = await login(client)
    r = await client.get("/api/v1/auth/me", headers=auth(refresh))
    assert r.status_code == 401


async def test_logout_revokes_refresh(client):
    _, refresh = await login(client)
    csrf = csrf_headers(client)
    r = await client.post("/api/v1/auth/logout", headers=csrf)
    assert r.status_code == 204
    assert client.cookies.get("praxis_refresh") is None

    # Replaying the revoked cookie is rejected (restore the cookies deleted
    # by logout so the request reaches token validation).
    client.cookies.set("praxis_refresh", refresh)
    client.cookies.set("praxis_csrf", csrf["X-CSRF-Token"])
    r = await client.post("/api/v1/auth/refresh", headers=csrf)
    assert r.status_code == 401


async def test_cookie_refresh_requires_csrf(client):
    await login(client)
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


async def test_endpoints_require_auth(client):
    for method, path in (
        ("get", "/api/v1/patients"),
        ("get", "/api/v1/tags"),
        ("get", "/api/v1/stats/summary"),
    ):
        r = await getattr(client, method)(path)
        assert r.status_code == 401, path


async def test_login_lockout_after_repeated_failures(client):
    await make_user(client, (await login(client))[0], "recep1")
    # a different username must stay unaffected (lockout is per-username)
    for i in range(5):
        r = await client.post(
            "/api/v1/auth/login", json={"username": "recep1", "password": f"wrong{i}"}
        )
        assert r.status_code == 401
    # 6th attempt — even with the CORRECT password — is locked out
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep1", "password": "passw0rd123"}
    )
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "login_locked"
    # another username is untouched
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert r.status_code == 200
    # expiring the failure window unlocks the account
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE login_audit SET created_at = :t WHERE success = 0")
            if "sqlite" in db.bind.dialect.name
            else text("UPDATE login_audit SET created_at = :t WHERE success = false"),
            {"t": dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)},
        )
        await db.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep1", "password": "passw0rd123"}
    )
    assert r.status_code == 200


async def test_password_change_revokes_refresh_tokens(client):
    token = (await login(client))[0]
    await make_user(client, token, "recep2")
    await login(client, "recep2", "passw0rd123")
    users = (await client.get("/api/v1/users?limit=100", headers=auth(token))).json()
    uid = next(u["id"] for u in users["items"] if u["username"] == "recep2")
    # The API keeps the documented 8-character minimum; a short edit must be
    # rejected before the password is changed or refresh tokens are revoked.
    r = await client.patch(
        f"/api/v1/users/{uid}", json={"password": "short"}, headers=auth(token)
    )
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["loc"] == ["body", "password"]
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep2", "password": "passw0rd123"}
    )
    assert r.status_code == 200

    r = await client.patch(
        f"/api/v1/users/{uid}", json={"password": "new-pass-456"}, headers=auth(token)
    )
    assert r.status_code == 200
    # the pre-change refresh token must be dead
    r = await client.post(
        "/api/v1/auth/refresh", headers=csrf_headers(client)
    )
    assert r.status_code == 401
    # ...and the old password no longer logs in
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep2", "password": "passw0rd123"}
    )
    assert r.status_code == 401
    r = await client.post(
        "/api/v1/auth/login", json={"username": "recep2", "password": "new-pass-456"}
    )
    assert r.status_code == 200


async def test_logout_writes_audit_row(client):
    access, _ = await login(client)
    r = await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert r.status_code == 204
    r = await client.get(
        "/api/v1/admin/audit", params={"entity_type": "session"}, headers=auth(access)
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert items[0]["action"] == "logout"
    assert items[0]["username"] == "admin"


async def test_bootstrap_heals_admin_role_permissions(client):
    """The admin role is UI-locked, so bootstrap keeps it at the full catalog.

    Heals databases whose roles were seeded before a permission existed
    (create_all-built DBs are stamped at head — data migrations never run).
    Editable system roles (doctor) must NOT be force-updated.
    """
    import json

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.main import ensure_system_roles
    from app.models import Role

    async with SessionLocal() as db:
        await db.execute(
            text("UPDATE roles SET permissions_json = :j WHERE name = 'admin'"),
            {"j": json.dumps(["patients.read"])},
        )
        await db.execute(
            text("UPDATE roles SET permissions_json = :j WHERE name = 'doctor'"),
            {"j": json.dumps(["patients.read"])},
        )
        await db.commit()

        await ensure_system_roles(db)

        admin = await db.scalar(select(Role).where(Role.name == "admin"))
        assert "patients.read" in json.loads(admin.permissions_json)
        assert "users.manage" in json.loads(admin.permissions_json)
        # editable role: bootstrap seeding never rewrites existing rows
        doctor = await db.scalar(select(Role).where(Role.name == "doctor"))
        assert json.loads(doctor.permissions_json) == ["patients.read"]


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

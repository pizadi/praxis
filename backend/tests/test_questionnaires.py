"""Questionnaire templates + responses: format validation, CRUD, patient
subtree soft-delete/trash, audit trail."""

from tests.conftest import auth, login, make_user

VALID_FORMAT = {
    "version": 1,
    "title": "پرسش‌نامه درد",
    "questions": [
        {
            "key": "pain_level",
            "label": "شدت درد",
            "type": "number",
            "required": True,
            "min": 0,
            "max": 10,
            "integer": True,
        },
        {
            "key": "mobility",
            "label": "تحرک",
            "type": "choice",
            "required": False,
            "options": [
                {"value": "bad", "label": "بد", "score": 0},
                {"value": "ok", "label": "متوسط", "score": 1},
                {"value": "good", "label": "خوب", "score": 2},
            ],
        },
        {
            "key": "notes",
            "label": "توضیحات",
            "type": "string",
            "required": False,
            "multiline": True,
            "max_length": 500,
        },
    ],
}


async def create_template(client, token: str, name: str = "درد", fmt=None) -> dict:
    r = await client.post(
        "/api/v1/questionnaires/templates",
        json={"name": name, "description": "", "format": fmt or VALID_FORMAT},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def create_patient(client, token: str, national_id: str = "0012345678") -> dict:
    r = await client.post(
        "/api/v1/patients",
        json={
            "national_id": national_id,
            "first_name": "الف",
            "last_name": "ب",
            "year_of_birth": "1370",
            "gender": 0,
        },
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- templates ------------------------------------------------------------------


async def test_template_crud_and_admin_only(client):
    admin = (await login(client))[0]
    await make_user(client, admin, "recep1", role="receptionist")
    recep = (await login(client, "recep1", "passw0rd123"))[0]

    # receptionist can list (questionnaires.read) but not manage templates
    r = await client.get(
        "/api/v1/questionnaires/templates", headers=auth(recep)
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/questionnaires/templates",
        json={"name": "x", "format": VALID_FORMAT},
        headers=auth(recep),
    )
    assert r.status_code == 403

    created = await create_template(client, admin)
    assert created["format"]["questions"][0]["key"] == "pain_level"

    # duplicate name → 409
    r = await client.post(
        "/api/v1/questionnaires/templates",
        json={"name": "درد", "format": VALID_FORMAT},
        headers=auth(admin),
    )
    assert r.status_code == 409

    # update format
    r = await client.patch(
        f"/api/v1/questionnaires/templates/{created['id']}",
        json={"description": "توضیح"},
        headers=auth(admin),
    )
    assert r.status_code == 200
    assert r.json()["description"] == "توضیح"

    # soft delete → list empty, trash has it
    r = await client.delete(
        f"/api/v1/questionnaires/templates/{created['id']}", headers=auth(admin)
    )
    assert r.status_code == 204
    r = await client.get("/api/v1/questionnaires/templates", headers=auth(admin))
    assert r.json()["total"] == 0
    trash = (
        await client.get("/api/v1/admin/trash/questionnaire_templates", headers=auth(admin))
    ).json()
    assert any(i["id"] == created["id"] for i in trash["items"])


async def test_template_format_validation_matrix(client):
    admin = (await login(client))[0]

    async def try_format(fmt):
        return await client.post(
            "/api/v1/questionnaires/templates",
            json={"name": "t", "format": fmt},
            headers=auth(admin),
        )

    # bad key
    bad = {"questions": [{"key": "Has Space", "label": "x", "type": "string"}]}
    assert (await try_format(bad)).status_code == 422
    # empty questions
    assert (await try_format({"questions": []})).status_code == 422
    # duplicate keys
    dup = {
        "questions": [
            {"key": "a", "label": "x", "type": "string"},
            {"key": "a", "label": "y", "type": "string"},
        ]
    }
    assert (await try_format(dup)).status_code == 422
    # number: min > max
    badrange = {
        "questions": [
            {"key": "n", "label": "x", "type": "number", "min": 10, "max": 0}
        ]
    }
    assert (await try_format(badrange)).status_code == 422
    # choice: fewer than 2 options / duplicate option values
    oneopt = {
        "questions": [
            {"key": "c", "label": "x", "type": "choice", "options": [{"value": "a", "label": "A"}]}
        ]
    }
    assert (await try_format(oneopt)).status_code == 422
    dupopt = {
        "questions": [
            {
                "key": "c",
                "label": "x",
                "type": "choice",
                "options": [
                    {"value": "a", "label": "A"},
                    {"value": "a", "label": "A2"},
                ],
            }
        ]
    }
    assert (await try_format(dupopt)).status_code == 422
    # unknown type
    assert (
        await try_format({"questions": [{"key": "s", "label": "x", "type": "boolean"}]})
    ).status_code == 422
    # unknown top-level key
    assert (
        await try_format({"questions": [{"key": "s", "label": "x", "type": "string"}], "huh": 1})
    ).status_code == 422
    # valid passes
    assert (await try_format(VALID_FORMAT)).status_code == 201


async def test_template_validate_endpoint(client):
    admin = (await login(client))[0]
    r = await client.post(
        "/api/v1/questionnaires/templates/validate",
        json={"name": "x", "format": VALID_FORMAT},
        headers=auth(admin),
    )
    assert r.status_code == 200
    bad = dict(VALID_FORMAT, questions=[{"key": "bad key!", "label": "x", "type": "string"}])
    r = await client.post(
        "/api/v1/questionnaires/templates/validate",
        json={"name": "x", "format": bad},
        headers=auth(admin),
    )
    assert r.status_code == 422


# --- responses ------------------------------------------------------------------


async def test_response_crud_and_answer_validation(client):
    admin = (await login(client))[0]
    tpl = await create_template(client, admin)
    pat = await create_patient(client, admin)

    good = {"pain_level": 7, "mobility": "ok", "notes": "کمی بهبود"}
    r = await client.post(
        f"/api/v1/patients/{pat['id']}/questionnaires",
        json={"template_id": tpl["id"], "answers": good},
        headers=auth(admin),
    )
    assert r.status_code == 201, r.text
    resp = r.json()
    assert resp["answers"] == good
    assert resp["template_name"] == "درد"
    assert resp["created_by_username"] == "admin"

    # multiple responses for the same template are allowed
    r = await client.post(
        f"/api/v1/patients/{pat['id']}/questionnaires",
        json={"template_id": tpl["id"], "answers": {"pain_level": 3}},
        headers=auth(admin),
    )
    assert r.status_code == 201

    # invalid answers → 422 with field errors (null/missing is always OK —
    # fields are nullable; `required` is a UI-level constraint only)
    for bad_answers in (
        {"pain_level": 11},                      # out of range
        {"pain_level": 1.5},                     # not integer
        {"pain_level": 1, "mobility": "great"},  # unknown choice
        {"pain_level": 1, "bogus": 1},           # unknown key
        {"pain_level": 1, "notes": 42},          # wrong type
    ):
        r = await client.post(
            f"/api/v1/patients/{pat['id']}/questionnaires",
            json={"template_id": tpl["id"], "answers": bad_answers},
            headers=auth(admin),
        )
        assert r.status_code == 422, bad_answers

    # absent/empty fields are always acceptable (nullable)
    r = await client.post(
        f"/api/v1/patients/{pat['id']}/questionnaires",
        json={"template_id": tpl["id"], "answers": {"mobility": "ok"}},
        headers=auth(admin),
    )
    assert r.status_code == 201, r.text

    # list for patient (receptionist can read)
    await make_user(client, admin, "recep1", role="receptionist")
    recep = (await login(client, "recep1", "passw0rd123"))[0]
    r = await client.get(
        f"/api/v1/patients/{pat['id']}/questionnaires", headers=auth(recep)
    )
    assert r.status_code == 200
    assert r.json()["total"] == 3

    # update: optional question can be nulled; required ones too (nullable)
    r = await client.patch(
        f"/api/v1/questionnaires/responses/{resp['id']}",
        json={"answers": {"pain_level": 4, "mobility": None, "notes": None}},
        headers=auth(admin),
    )
    assert r.status_code == 200
    assert r.json()["answers"]["pain_level"] == 4
    r = await client.patch(
        f"/api/v1/questionnaires/responses/{resp['id']}",
        json={"answers": {"pain_level": None}},
        headers=auth(admin),
    )
    assert r.status_code == 200

    # delete → trash
    r = await client.delete(
        f"/api/v1/questionnaires/responses/{resp['id']}", headers=auth(admin)
    )
    assert r.status_code == 204
    trash = (
        await client.get("/api/v1/admin/trash/questionnaire_responses", headers=auth(admin))
    ).json()
    assert any(i["id"] == resp["id"] for i in trash["items"])


async def test_response_patient_subtree_and_restore(client):
    admin = (await login(client))[0]
    tpl = await create_template(client, admin)
    pat = await create_patient(client, admin)
    r = await client.post(
        f"/api/v1/patients/{pat['id']}/questionnaires",
        json={"template_id": tpl["id"], "answers": {"pain_level": 2}},
        headers=auth(admin),
    )
    resp = r.json()

    # soft-deleted patient hides responses; restore brings them back
    r = await client.delete(f"/api/v1/patients/{pat['id']}", headers=auth(admin))
    assert r.status_code == 204
    r = await client.get(
        f"/api/v1/patients/{pat['id']}/questionnaires", headers=auth(admin)
    )
    assert r.status_code == 404  # patient itself is gone from live views
    trash = (
        await client.get("/api/v1/admin/trash/questionnaire_responses", headers=auth(admin))
    ).json()
    # directly-deleted rows only — the response was NOT stamped, so not listed
    assert trash["total"] == 0

    r = await client.post(
        f"/api/v1/admin/trash/patients/{pat['id']}/restore", headers=auth(admin)
    )
    assert r.status_code == 200
    r = await client.get(
        f"/api/v1/patients/{pat['id']}/questionnaires", headers=auth(admin)
    )
    assert r.json()["total"] == 1

    # deleting the response itself, then restoring before purging
    r = await client.delete(
        f"/api/v1/questionnaires/responses/{resp['id']}", headers=auth(admin)
    )
    assert r.status_code == 204
    r = await client.post(
        f"/api/v1/admin/trash/questionnaire_responses/{resp['id']}/restore",
        headers=auth(admin),
    )
    assert r.status_code == 200
    r = await client.get(
        f"/api/v1/questionnaires/responses/{resp['id']}", headers=auth(admin)
    )
    assert r.status_code == 200

    # delete again, then purge (admin only) removes it for good
    r = await client.delete(
        f"/api/v1/questionnaires/responses/{resp['id']}", headers=auth(admin)
    )
    assert r.status_code == 204
    r = await client.delete(
        f"/api/v1/admin/trash/questionnaire_responses/{resp['id']}",
        headers=auth(admin),
    )
    assert r.status_code == 204
    r = await client.get(
        f"/api/v1/questionnaires/responses/{resp['id']}", headers=auth(admin)
    )
    assert r.status_code == 404


async def test_template_delete_keeps_responses_readable(client):
    """A soft-deleted template hides its picker entry; stored responses keep
    the FK. The list-join filters deleted templates, so responses of a deleted
    template are not listed — restore the template to see them again."""
    admin = (await login(client))[0]
    tpl = await create_template(client, admin)
    pat = await create_patient(client, admin)
    r = await client.post(
        f"/api/v1/patients/{pat['id']}/questionnaires",
        json={"template_id": tpl["id"], "answers": {"pain_level": 5}},
        headers=auth(admin),
    )
    assert r.status_code == 201
    await client.delete(f"/api/v1/questionnaires/templates/{tpl['id']}", headers=auth(admin))
    r = await client.get(
        f"/api/v1/patients/{pat['id']}/questionnaires", headers=auth(admin)
    )
    assert r.json()["total"] == 0
    # restore template → response visible again (no snapshot; render merges)
    await client.post(
        f"/api/v1/admin/trash/questionnaire_templates/{tpl['id']}/restore",
        headers=auth(admin),
    )
    r = await client.get(
        f"/api/v1/patients/{pat['id']}/questionnaires", headers=auth(admin)
    )
    assert r.json()["total"] == 1


async def test_questionnaire_audit_trail(client):
    admin = (await login(client))[0]
    tpl = await create_template(client, admin)
    pat = await create_patient(client, admin)
    await client.post(
        f"/api/v1/patients/{pat['id']}/questionnaires",
        json={"template_id": tpl["id"], "answers": {"pain_level": 1}},
        headers=auth(admin),
    )
    r = await client.get(
        "/api/v1/admin/audit?entity_type=questionnaire_response", headers=auth(admin)
    )
    assert r.status_code == 200
    entries = r.json()["items"]
    assert any(e["action"] == "create" for e in entries)
    r = await client.get(
        "/api/v1/admin/audit?entity_type=questionnaire_template", headers=auth(admin)
    )
    assert any(e["action"] == "create" for e in r.json()["items"])


# --- score formula ----------------------------------------------------------------


async def test_score_formula_template_validation(client):
    admin = (await login(client))[0]
    counter = {"n": 0}

    async def try_format(fmt):
        counter["n"] += 1
        return await client.post(
            "/api/v1/questionnaires/templates",
            json={"name": f"t{counter['n']}", "format": fmt},
            headers=auth(admin),
        )

    # valid formula round-trips
    ok = {**VALID_FORMAT, "score_formula": "pain_level * 2 + mobility"}
    r = await try_format(ok)
    assert r.status_code == 201, r.text
    assert r.json()["format"]["score_formula"] == "pain_level * 2 + mobility"

    # empty string = no scoring
    assert (await try_format({**VALID_FORMAT, "score_formula": ""})).status_code == 201

    # functions are supported (min/max 1+ args, abs exactly 1)
    fns = {
        **VALID_FORMAT,
        "score_formula": "min(pain_level, 10) + max(mobility, 0) + abs(0 - pain_level)",
    }
    assert (await try_format(fns)).status_code == 201

    # syntax errors
    for bad in ("pain_level +* 2", "pain_level +", "(pain_level", "pain_level 2", "2."):
        assert (
            await try_format({**VALID_FORMAT, "score_formula": bad})
        ).status_code == 422, bad

    # unknown key / string question referenced / unknown function / bad arity
    assert (
        await try_format({**VALID_FORMAT, "score_formula": "nope + 1"})
    ).status_code == 422
    assert (
        await try_format({**VALID_FORMAT, "score_formula": "notes + 1"})
    ).status_code == 422
    assert (
        await try_format({**VALID_FORMAT, "score_formula": "clamp(pain_level, 0, 1)"})
    ).status_code == 422
    assert (
        await try_format({**VALID_FORMAT, "score_formula": "abs(pain_level, 2)"})
    ).status_code == 422

    # validate endpoint accepts/rejects formulas the same way, persisting nothing
    r = await client.post(
        "/api/v1/questionnaires/templates/validate",
        json={"name": "t", "format": ok},
        headers=auth(admin),
    )
    assert r.status_code == 200
    r = await client.post(
        "/api/v1/questionnaires/templates/validate",
        json={"name": "t", "format": {**VALID_FORMAT, "score_formula": "nope + 1"}},
        headers=auth(admin),
    )
    assert r.status_code == 422
    r = await client.get("/api/v1/questionnaires/templates", headers=auth(admin))
    # only the three valid variants from this test were saved
    assert r.json()["total"] == 3


async def test_min_max_answer_boundaries(client):
    """Exact min/max values are accepted; one step beyond is rejected."""
    admin = (await login(client))[0]
    tpl = await create_template(client, admin)
    pat = await create_patient(client, admin)

    for good in ({"pain_level": 0}, {"pain_level": 10}):
        r = await client.post(
            f"/api/v1/patients/{pat['id']}/questionnaires",
            json={"template_id": tpl["id"], "answers": good},
            headers=auth(admin),
        )
        assert r.status_code == 201, good
        assert r.json()["answers"] == good

    for bad in ({"pain_level": -1}, {"pain_level": 11}, {"pain_level": 10.5}):
        r = await client.post(
            f"/api/v1/patients/{pat['id']}/questionnaires",
            json={"template_id": tpl["id"], "answers": bad},
            headers=auth(admin),
        )
        assert r.status_code == 422, bad
        fields = r.json()["error"]["details"]["fields"]
        assert set(fields) == {"pain_level"}


async def test_responses_report_endpoint(client):
    admin = (await login(client))[0]
    tpl = await create_template(client, admin)
    pat1 = await create_patient(client, admin, "0012345678")
    pat2 = await create_patient(client, admin, "0022345678")
    for pat, pain in ((pat1, 2), (pat1, 5), (pat2, 9)):
        r = await client.post(
            f"/api/v1/patients/{pat['id']}/questionnaires",
            json={"template_id": tpl["id"], "answers": {"pain_level": pain}},
            headers=auth(admin),
        )
        assert r.status_code == 201

    # receptionist (questionnaires.read) can read the report
    await make_user(client, admin, "recep1", role="receptionist")
    recep = (await login(client, "recep1", "passw0rd123"))[0]

    r = await client.get(
        f"/api/v1/questionnaires/responses?template_id={tpl['id']}", headers=auth(recep)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert [i["answers"]["pain_level"] for i in body["items"]] == [9, 5, 2]  # newest first
    assert all(i["patient_national_id"] in ("0012345678", "0022345678") for i in body["items"])
    assert all(i["template_name"] == "درد" for i in body["items"])
    assert all(i["created_by_username"] == "admin" for i in body["items"])

    # pagination
    r = await client.get(
        f"/api/v1/questionnaires/responses?template_id={tpl['id']}&limit=2&offset=0",
        headers=auth(admin),
    )
    assert len(r.json()["items"]) == 2 and r.json()["total"] == 3
    r = await client.get(
        f"/api/v1/questionnaires/responses?template_id={tpl['id']}&limit=2&offset=2",
        headers=auth(admin),
    )
    assert len(r.json()["items"]) == 1 and r.json()["total"] == 3

    # soft-deleted patient hides its responses (subtree rule)
    await client.delete(f"/api/v1/patients/{pat2['id']}", headers=auth(admin))
    r = await client.get(
        f"/api/v1/questionnaires/responses?template_id={tpl['id']}", headers=auth(admin)
    )
    assert r.json()["total"] == 2
    await client.post(
        f"/api/v1/admin/trash/patients/{pat2['id']}/restore", headers=auth(admin)
    )

    # soft-deleted template → 404 (the report only lists live templates)
    await client.delete(f"/api/v1/questionnaires/templates/{tpl['id']}", headers=auth(admin))
    r = await client.get(
        f"/api/v1/questionnaires/responses?template_id={tpl['id']}", headers=auth(admin)
    )
    assert r.status_code == 404

    # unknown template → 404
    r = await client.get(
        "/api/v1/questionnaires/responses?template_id=99999", headers=auth(admin)
    )
    assert r.status_code == 404


async def test_responses_date_filter(client):
    """date= restricts patient responses to one APP_TIMEZONE day — the
    appointment view's same-day questionnaires tab."""
    import datetime as dt

    from app.db.session import APP_TZ

    token, _ = await login(client)
    tpl = await create_template(client, token)
    pid = (await create_patient(client, token))["id"]
    r = await client.post(
        f"/api/v1/patients/{pid}/questionnaires",
        json={"template_id": tpl["id"], "answers": {"pain_level": 2}},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text

    today = dt.datetime.now(APP_TZ).date().isoformat()
    r = await client.get(
        f"/api/v1/patients/{pid}/questionnaires",
        params={"date": today},
        headers=auth(token),
    )
    assert r.json()["total"] == 1

    r = await client.get(
        f"/api/v1/patients/{pid}/questionnaires",
        params={"date": "2001-01-01"},
        headers=auth(token),
    )
    assert r.json()["total"] == 0

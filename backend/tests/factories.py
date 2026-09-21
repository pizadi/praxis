"""API builders — one source of truth for creating domain objects in tests.

Each factory hits the real API (integration-faithful) and returns the parsed
response body. Tests assert persisted fields on the CREATE response (the
multipart-upload bug survived a whole suite because only post-PATCH values
were checked).
"""

import io
from typing import Any

from httpx import AsyncClient

from tests.conftest import auth

PATIENT_BODY: dict[str, Any] = {
    "national_id": "1234567890",
    "first_name": "Test",
    "last_name": "Testi",
    "year_of_birth": "1990",
    "phone_number": "09121234567",
    "gender": 0,
}


def _r(client: AsyncClient, token: str):
    return {"headers": auth(token)}


async def mk_patient(client: AsyncClient, token: str, **overrides) -> dict:
    body = {**PATIENT_BODY, **overrides}
    r = await client.post("/api/v1/patients", json=body, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()


async def mk_appointment(
    client: AsyncClient,
    token: str,
    patient_id: int,
    at: str = "2026-09-10T10:30:00+03:30",
    **overrides,
) -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/appointments",
        json={"scheduled_at": at, **overrides},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def mk_file(
    client: AsyncClient,
    token: str,
    patient_id: int,
    filename: str = "x.txt",
    content: bytes = b"hello",
    mime: str = "text/plain",
    **data,
) -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/files",
        data=data,
        files={"file": (filename, io.BytesIO(content), mime)},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def mk_note_file(client: AsyncClient, token: str, patient_id: int, **body) -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/files/note",
        json={"description": "note", **body},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def mk_transaction(
    client: AsyncClient, token: str, appointment_id: int, description: str = "ویزیت",
    amount: int = 100000, pos: bool = True,
) -> dict:
    r = await client.post(
        f"/api/v1/appointments/{appointment_id}/transactions",
        json={"description": description, "amount": amount, "pos": pos},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


QUESTION_FORMAT = {
    "version": 1,
    "title": "پرسش‌نامه درد",
    "questions": [
        {"key": "pain_level", "label": "شدت درد", "type": "number", "required": True,
         "min": 0, "max": 10, "integer": True},
        {"key": "mobility", "label": "تحرک", "type": "choice", "required": False,
         "options": [
             {"value": "bad", "label": "بد", "score": 0},
             {"value": "ok", "label": "متوسط", "score": 1},
             {"value": "good", "label": "خوب", "score": 2},
         ]},
        {"key": "notes", "label": "توضیحات", "type": "string", "required": False,
         "multiline": True, "max_length": 500},
    ],
}


async def mk_template(
    client: AsyncClient, token: str, name: str = "درد", fmt: dict | None = None
) -> dict:
    r = await client.post(
        "/api/v1/questionnaires/templates",
        json={"name": name, "description": "", "format": fmt or QUESTION_FORMAT},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def mk_response(
    client: AsyncClient, token: str, patient_id: int, template_id: int,
    answers: dict | None = None,
) -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/questionnaires",
        json={"template_id": template_id, "answers": answers or {"pain_level": 2}},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def mk_prescription(
    client: AsyncClient, token: str, patient_id: int,
    items: list[dict] | None = None, **body,
) -> dict:
    r = await client.post(
        f"/api/v1/patients/{patient_id}/prescriptions",
        json={"items": items or [{"name": "P1"}], **body},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def mk_tag(client: AsyncClient, token: str, name: str) -> dict:
    r = await client.post("/api/v1/tags", json={"name": name}, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()


async def mk_diagnosis(client: AsyncClient, token: str, name: str) -> dict:
    r = await client.post("/api/v1/diagnoses", json={"name": name}, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()

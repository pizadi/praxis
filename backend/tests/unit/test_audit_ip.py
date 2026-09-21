"""audit.py unit tests: client-IP resolution + update diffs."""

from starlette.requests import Request


def _request(
    headers: dict[str, str] | None = None, client_host: str | None = "10.0.0.1"
) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": b"",
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_forwarded_for_wins_leftmost():
    from app.services.audit import _client_ip

    r = _request({"X-Forwarded-For": "203.0.113.7, 10.0.0.1, 10.0.0.2"})
    assert _client_ip(r) == "203.0.113.7"


def test_real_ip_fallback():
    from app.services.audit import _client_ip

    r = _request({"X-Real-IP": "198.51.100.9"})
    assert _client_ip(r) == "198.51.100.9"
    r = _request({"X-Real-IP": " 198.51.100.9 "})
    assert _client_ip(r) == "198.51.100.9"


def test_xff_beats_real_ip():
    from app.services.audit import _client_ip

    r = _request({"X-Forwarded-For": "203.0.113.7", "X-Real-IP": "198.51.100.9"})
    assert _client_ip(r) == "203.0.113.7"


def test_peer_address_fallback():
    from app.services.audit import _client_ip

    assert _client_ip(_request()) == "10.0.0.1"


def test_blank_xff_falls_through():
    from app.services.audit import _client_ip

    assert _client_ip(_request({"X-Forwarded-For": " , ,"})) == "10.0.0.1"


def test_truncated_to_64_chars():
    from app.services.audit import _client_ip

    r = _request({"X-Forwarded-For": "a" * 100})
    assert len(_client_ip(r)) == 64


def test_diff_details_reports_only_changes():
    from app.services.audit import diff_details

    before = {"stage": 0, "notes": "x", "same": 1}
    after = {"stage": 1, "notes": "x", "same": 1}
    assert diff_details(before, after, ["stage", "notes", "same"]) == {
        "stage": {"old": 0, "new": 1}
    }


def test_diff_details_ignores_fields_missing_from_after():
    from app.services.audit import diff_details

    assert diff_details({"a": 1}, {}, ["a"]) == {}

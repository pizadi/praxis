"""Production API documentation must not expose the route/schema map."""


def _paths(app) -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def test_api_docs_available_outside_production(monkeypatch) -> None:
    monkeypatch.setenv("CLINIC_ENV", "test")
    from app.main import create_app

    paths = _paths(create_app())
    assert "/docs" in paths
    assert "/redoc" in paths
    assert "/openapi.json" in paths


def test_api_docs_disabled_in_production(monkeypatch) -> None:
    monkeypatch.setenv("CLINIC_ENV", "production")
    from app.main import create_app

    paths = _paths(create_app())
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths
    assert "/health" in paths

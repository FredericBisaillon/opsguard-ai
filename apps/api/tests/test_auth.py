from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from opsguard_api.config import Settings, get_settings
from opsguard_api.main import app
from opsguard_api.security import API_KEY_ERROR_DETAIL, API_KEY_HEADER_NAME

TEST_API_KEY = "test-secret-api-key"


@pytest.fixture
def strict_auth_settings() -> Iterator[Settings]:
    settings = Settings(
        database_url=get_settings().database_url,
        require_api_key=True,
        ops_guard_api_key=SecretStr(TEST_API_KEY),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


def auth_headers(api_key: str = TEST_API_KEY) -> dict[str, str]:
    return {API_KEY_HEADER_NAME: api_key}


def test_health_remains_public_without_api_key(
    strict_auth_settings: Settings,
) -> None:
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_protected_endpoint_rejects_missing_api_key(
    strict_auth_settings: Settings,
) -> None:
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.post(
            "/documents",
            json={
                "title": "Auth test document",
                "source_type": "uploaded_file",
                "source_path": "data/raw/auth-test.txt",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_KEY_ERROR_DETAIL}


def test_protected_endpoint_rejects_invalid_api_key(
    strict_auth_settings: Settings,
) -> None:
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.post(
            "/documents",
            headers=auth_headers("wrong-api-key"),
            json={
                "title": "Auth test document",
                "source_type": "uploaded_file",
                "source_path": "data/raw/auth-test.txt",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_KEY_ERROR_DETAIL}


def test_protected_endpoint_accepts_valid_api_key(
    strict_auth_settings: Settings,
) -> None:
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            headers=auth_headers(),
            json={
                "document_id": 999999999,
                "title": "Auth should reach route logic",
                "severity": "medium",
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_ai_review_endpoint_rejects_missing_api_key(
    strict_auth_settings: Settings,
) -> None:
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.post(
            "/ai/review-tasks/suggest",
            json={
                "query": "Suggest a review task.",
                "document_id": 1,
                "top_k": 5,
                "auto_create": False,
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_KEY_ERROR_DETAIL}


def test_audit_events_reject_missing_api_key(
    strict_auth_settings: Settings,
) -> None:
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.get("/audit-events")

    assert response.status_code == 401
    assert response.json() == {"detail": API_KEY_ERROR_DETAIL}


def test_review_task_write_rejects_missing_api_key(
    strict_auth_settings: Settings,
) -> None:
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            json={
                "document_id": 1,
                "title": "Auth should block this write.",
                "severity": "high",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": API_KEY_ERROR_DETAIL}


def test_api_key_is_not_exposed_in_error_response(
    strict_auth_settings: Settings,
) -> None:
    configured_secret = TEST_API_KEY
    provided_secret = "wrong-secret-that-must-not-echo"
    assert strict_auth_settings.require_api_key is True

    with TestClient(app) as client:
        response = client.get(
            "/audit-events",
            headers=auth_headers(provided_secret),
        )

    response_text = response.text

    assert response.status_code == 401
    assert response.json() == {"detail": API_KEY_ERROR_DETAIL}
    assert configured_secret not in response_text
    assert provided_secret not in response_text


def test_strict_mode_without_configured_api_key_rejects_generically() -> None:
    settings = Settings(
        database_url=get_settings().database_url,
        require_api_key=True,
        ops_guard_api_key=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        with TestClient(app) as client:
            response = client.get("/audit-events", headers=auth_headers())
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 401
    assert response.json() == {"detail": API_KEY_ERROR_DETAIL}

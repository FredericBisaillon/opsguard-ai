import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from opsguard_api.config import Settings, get_settings

API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_ERROR_DETAIL = "Invalid or missing API key"


def _configured_api_key(settings: Settings) -> str | None:
    if settings.ops_guard_api_key is None:
        return None

    api_key = settings.ops_guard_api_key.get_secret_value()
    if not api_key:
        return None

    return api_key


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER_NAME)] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.require_api_key:
        return

    expected_api_key = _configured_api_key(settings)
    provided_api_key = x_api_key or ""

    if expected_api_key is None or not secrets.compare_digest(
        provided_api_key,
        expected_api_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=API_KEY_ERROR_DETAIL,
        )

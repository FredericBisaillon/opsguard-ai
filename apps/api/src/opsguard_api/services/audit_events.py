import json
import re
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsguard_api.models import (
    AuditEvent,
    AuditEventSource,
    AuditEventStatus,
    AuditEventType,
)
from opsguard_api.schemas import AuditEventCreateInternal

MAX_METADATA_JSON_CHARS = 4000
MAX_METADATA_STRING_CHARS = 500
MAX_METADATA_LIST_ITEMS = 50
MAX_METADATA_DICT_KEYS = 50
MAX_METADATA_DEPTH = 4
MAX_SUMMARY_CHARS = 500

_DROPPED = object()
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "credential",
    "embedding",
    "password",
    "prompt",
    "secret",
    "token",
    "context_text",
    "raw_context",
)
_OPENAI_KEY_PATTERN = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b([-A-Za-z0-9_]*api[_-]?key|[-A-Za-z0-9_]*secret|"
    r"[-A-Za-z0-9_]*token|[-A-Za-z0-9_]*password|"
    r"[-A-Za-z0-9_]*credential)\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)
_REDACTED_SECRET = "[REDACTED_SECRET]"


class AuditEventError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_audit_event(
    db: Session,
    event_in: AuditEventCreateInternal,
    *,
    commit: bool = True,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_in.event_type.value,
        actor_type=event_in.actor_type.value,
        actor_id=event_in.actor_id,
        document_id=event_in.document_id,
        review_task_id=event_in.review_task_id,
        source=event_in.source.value,
        status=event_in.status.value,
        summary=_truncate_text(event_in.summary.strip(), MAX_SUMMARY_CHARS),
        event_metadata=sanitize_metadata(event_in.metadata),
    )

    db.add(event)
    if commit:
        db.commit()
        db.refresh(event)
    else:
        db.flush()

    return event


def list_audit_events(
    db: Session,
    *,
    event_type: AuditEventType | None = None,
    document_id: int | None = None,
    review_task_id: int | None = None,
    status: AuditEventStatus | None = None,
    source: AuditEventSource | None = None,
    limit: int = 100,
) -> list[AuditEvent]:
    statement = select(AuditEvent).order_by(
        AuditEvent.created_at.desc(),
        AuditEvent.id.desc(),
    )

    if event_type is not None:
        statement = statement.where(AuditEvent.event_type == event_type.value)
    if document_id is not None:
        statement = statement.where(AuditEvent.document_id == document_id)
    if review_task_id is not None:
        statement = statement.where(AuditEvent.review_task_id == review_task_id)
    if status is not None:
        statement = statement.where(AuditEvent.status == status.value)
    if source is not None:
        statement = statement.where(AuditEvent.source == source.value)

    return list(db.scalars(statement.limit(limit)).all())


def get_audit_event(db: Session, event_id: int) -> AuditEvent:
    event = db.get(AuditEvent, event_id)
    if event is None:
        raise AuditEventError("Audit event not found.", status_code=404)

    return event


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None

    sanitized = _sanitize_value(metadata, depth=0)
    if not isinstance(sanitized, dict) or not sanitized:
        return None

    return _fit_metadata_size(sanitized)


def _sanitize_value(value: Any, *, depth: int) -> Any:
    if depth > MAX_METADATA_DEPTH:
        return _DROPPED

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, StrEnum):
        return value.value

    if isinstance(value, str):
        return _safe_metadata_string(value)

    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:MAX_METADATA_DICT_KEYS]:
            key = str(raw_key)
            if _is_sensitive_key(key):
                continue

            sanitized_value = _sanitize_value(raw_value, depth=depth + 1)
            if sanitized_value is _DROPPED:
                continue
            sanitized_dict[key] = sanitized_value

        return sanitized_dict or _DROPPED

    if isinstance(value, list | tuple | set):
        sanitized_list: list[Any] = []
        for item in list(value)[:MAX_METADATA_LIST_ITEMS]:
            sanitized_item = _sanitize_value(item, depth=depth + 1)
            if sanitized_item is not _DROPPED:
                sanitized_list.append(sanitized_item)

        return sanitized_list

    return _truncate_text(str(value), MAX_METADATA_STRING_CHARS)


def _fit_metadata_size(metadata: dict[str, Any]) -> dict[str, Any]:
    fitted: dict[str, Any] = {}
    truncated = False

    for key, value in metadata.items():
        candidate = {**fitted, key: value}
        if len(json.dumps(candidate, default=str)) > MAX_METADATA_JSON_CHARS:
            truncated = True
            break
        fitted = candidate

    if truncated:
        fitted["truncated"] = True

    return fitted or {"truncated": True}


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.lower().replace("-", "_")
    return any(part in normalized_key for part in _SENSITIVE_KEY_PARTS)


def _safe_metadata_string(text: str) -> str:
    redacted = _OPENAI_KEY_PATTERN.sub(_REDACTED_SECRET, text)
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}={_REDACTED_SECRET}",
        redacted,
    )
    return _truncate_text(redacted, MAX_METADATA_STRING_CHARS)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    if max_chars <= 3:
        return text[:max_chars]

    return f"{text[: max_chars - 3].rstrip()}..."

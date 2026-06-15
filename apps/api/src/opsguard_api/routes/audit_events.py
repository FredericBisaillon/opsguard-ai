from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from opsguard_api.db import get_db
from opsguard_api.models import (
    AuditEvent,
    AuditEventSource,
    AuditEventStatus,
    AuditEventType,
)
from opsguard_api.schemas import AuditEventRead
from opsguard_api.services import audit_events as audit_events_service

router = APIRouter(prefix="/audit-events", tags=["audit-events"])


@router.get("", response_model=list[AuditEventRead])
def list_audit_events(
    event_type: AuditEventType | None = None,
    document_id: int | None = Query(default=None, gt=0),
    review_task_id: int | None = Query(default=None, gt=0),
    status: AuditEventStatus | None = None,
    source: AuditEventSource | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    return audit_events_service.list_audit_events(
        db=db,
        event_type=event_type,
        document_id=document_id,
        review_task_id=review_task_id,
        status=status,
        source=source,
        limit=limit,
    )


@router.get("/{event_id}", response_model=AuditEventRead)
def get_audit_event(
    event_id: int,
    db: Session = Depends(get_db),
) -> AuditEvent:
    try:
        return audit_events_service.get_audit_event(db=db, event_id=event_id)
    except audit_events_service.AuditEventError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

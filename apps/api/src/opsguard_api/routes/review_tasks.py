from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from opsguard_api.db import get_db
from opsguard_api.models import ReviewTask, ReviewTaskSeverity, ReviewTaskStatus
from opsguard_api.schemas import ReviewTaskCreate, ReviewTaskRead, ReviewTaskUpdate
from opsguard_api.services import review_tasks as review_tasks_service

router = APIRouter(prefix="/review-tasks", tags=["review-tasks"])


@router.post(
    "",
    response_model=ReviewTaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_review_task(
    task_in: ReviewTaskCreate,
    db: Session = Depends(get_db),
) -> ReviewTask:
    try:
        return review_tasks_service.create_review_task(db=db, task_in=task_in)
    except review_tasks_service.ReviewTaskError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[ReviewTaskRead])
def list_review_tasks(
    document_id: int | None = Query(default=None, gt=0),
    status: ReviewTaskStatus | None = None,
    severity: ReviewTaskSeverity | None = None,
    db: Session = Depends(get_db),
) -> list[ReviewTask]:
    return review_tasks_service.list_review_tasks(
        db=db,
        document_id=document_id,
        status=status,
        severity=severity,
    )


@router.get("/{task_id}", response_model=ReviewTaskRead)
def get_review_task(
    task_id: int,
    db: Session = Depends(get_db),
) -> ReviewTask:
    try:
        return review_tasks_service.get_review_task(db=db, task_id=task_id)
    except review_tasks_service.ReviewTaskError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.patch("/{task_id}", response_model=ReviewTaskRead)
def update_review_task(
    task_id: int,
    task_in: ReviewTaskUpdate,
    db: Session = Depends(get_db),
) -> ReviewTask:
    try:
        return review_tasks_service.update_review_task(
            db=db,
            task_id=task_id,
            task_in=task_in,
        )
    except review_tasks_service.ReviewTaskError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{task_id}/dismiss", response_model=ReviewTaskRead)
def dismiss_review_task(
    task_id: int,
    db: Session = Depends(get_db),
) -> ReviewTask:
    try:
        return review_tasks_service.dismiss_review_task(db=db, task_id=task_id)
    except review_tasks_service.ReviewTaskError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

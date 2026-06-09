from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from opsguard_api.config import Settings, get_settings
from opsguard_api.db import get_db
from opsguard_api.models import Document, DocumentChunk
from opsguard_api.schemas import (
    DocumentChunkingRead,
    DocumentChunkRead,
    DocumentCreate,
    DocumentExtractionRead,
    DocumentRead,
)
from opsguard_api.services import documents as documents_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def create_document(
    document_in: DocumentCreate,
    db: Session = Depends(get_db),
) -> Document:
    return documents_service.create_document(db, document_in)


@router.post(
    "/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Document:
    try:
        return documents_service.create_uploaded_document(
            db=db,
            upload=file,
            title=title,
            settings=settings,
        )
    except documents_service.DocumentUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("", response_model=list[DocumentRead])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return documents_service.list_documents(db)


@router.post(
    "/{document_id}/extract-text",
    response_model=DocumentExtractionRead,
)
def extract_document_text(
    document_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> documents_service.DocumentExtractionResult:
    try:
        return documents_service.extract_document_text(
            db=db,
            document_id=document_id,
            settings=settings,
        )
    except documents_service.DocumentTextExtractionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/{document_id}/chunk",
    response_model=DocumentChunkingRead,
)
def chunk_document(
    document_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> documents_service.DocumentChunkingResult:
    try:
        return documents_service.chunk_document(
            db=db,
            document_id=document_id,
            settings=settings,
        )
    except documents_service.DocumentChunkingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkRead],
)
def list_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[DocumentChunk]:
    try:
        return documents_service.list_document_chunks(db=db, document_id=document_id)
    except documents_service.DocumentChunkingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

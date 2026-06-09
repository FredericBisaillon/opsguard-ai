from sqlalchemy import select
from sqlalchemy.orm import Session

from opsguard_api.models import Document, DocumentStatus
from opsguard_api.schemas import DocumentCreate


def create_document(db: Session, document_in: DocumentCreate) -> Document:
    document = Document(
        title=document_in.title,
        source_type=document_in.source_type,
        source_path=document_in.source_path,
        status=DocumentStatus.UPLOADED.value,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return document


def list_documents(db: Session) -> list[Document]:
    statement = select(Document).order_by(
        Document.created_at.desc(),
        Document.id.desc(),
    )
    return list(db.scalars(statement).all())

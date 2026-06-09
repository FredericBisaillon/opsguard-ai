from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from opsguard_api.config import PROJECT_ROOT, Settings
from opsguard_api.models import Document, DocumentStatus
from opsguard_api.schemas import DocumentCreate

CHUNK_SIZE_BYTES = 1024 * 1024
DOCUMENT_TITLE_MAX_LENGTH = 255
UPLOADED_FILE_SOURCE_TYPE = "uploaded_file"
ALLOWED_UPLOAD_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".md": {"text/markdown", "text/plain"},
    ".txt": {"text/plain"},
}


class DocumentUploadError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DocumentTextExtractionError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class SavedUpload:
    absolute_path: Path
    source_path: str


@dataclass(frozen=True)
class SavedExtraction:
    extracted_text_path: str
    character_count: int


@dataclass(frozen=True)
class DocumentExtractionResult:
    document_id: int
    status: str
    extracted_text_path: str
    character_count: int
    message: str


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


def create_uploaded_document(
    db: Session,
    upload: UploadFile,
    title: str | None,
    settings: Settings,
) -> Document:
    document_title = _document_title(title, upload.filename)
    saved_upload = _save_upload_file(upload, settings)
    document_in = DocumentCreate(
        title=document_title,
        source_type=UPLOADED_FILE_SOURCE_TYPE,
        source_path=saved_upload.source_path,
    )

    try:
        return create_document(db, document_in)
    except Exception:
        saved_upload.absolute_path.unlink(missing_ok=True)
        raise


def list_documents(db: Session) -> list[Document]:
    statement = select(Document).order_by(
        Document.created_at.desc(),
        Document.id.desc(),
    )
    return list(db.scalars(statement).all())


def extract_document_text(
    db: Session,
    document_id: int,
    settings: Settings,
) -> DocumentExtractionResult:
    from opsguard_api.services.extraction import TextExtractionError, extract_text

    document = db.get(Document, document_id)
    if document is None:
        raise DocumentTextExtractionError("Document not found.", status_code=404)

    try:
        source_path = _resolved_document_source_path(document.source_path, settings)
        _update_document_status(db, document, DocumentStatus.EXTRACTING)

        extracted_text = extract_text(source_path)
        saved_extraction = _save_extracted_text(
            document_id=document.id,
            text=extracted_text,
            settings=settings,
        )

        _update_document_status(db, document, DocumentStatus.TEXT_EXTRACTED)
        return DocumentExtractionResult(
            document_id=document.id,
            status=DocumentStatus.TEXT_EXTRACTED.value,
            extracted_text_path=saved_extraction.extracted_text_path,
            character_count=saved_extraction.character_count,
            message="Text extracted successfully.",
        )
    except DocumentTextExtractionError:
        _update_document_status(db, document, DocumentStatus.EXTRACTION_FAILED)
        raise
    except TextExtractionError as exc:
        _update_document_status(db, document, DocumentStatus.EXTRACTION_FAILED)
        raise DocumentTextExtractionError(exc.message) from exc


def _document_title(title: str | None, filename: str | None) -> str:
    document_title = (title or "").strip()
    if not document_title:
        document_title = Path(filename or "uploaded-document").name

    if not document_title:
        document_title = "uploaded-document"

    if len(document_title) > DOCUMENT_TITLE_MAX_LENGTH:
        raise DocumentUploadError("Title must be 255 characters or fewer.")

    return document_title


def _save_upload_file(upload: UploadFile, settings: Settings) -> SavedUpload:
    extension = _validated_extension(upload.filename, upload.content_type)
    upload_dir = _resolved_upload_dir(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid4().hex}{extension}"
    target_path = (upload_dir / stored_filename).resolve()
    if not target_path.is_relative_to(upload_dir):
        raise DocumentUploadError("Upload path is outside the configured directory.")

    bytes_written = 0
    try:
        upload.file.seek(0)
        with target_path.open("wb") as output_file:
            while chunk := upload.file.read(CHUNK_SIZE_BYTES):
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_size_bytes:
                    message = (
                        f"File exceeds the {settings.max_upload_size_mb} MB "
                        "upload limit."
                    )
                    raise DocumentUploadError(
                        message,
                        status_code=413,
                    )
                output_file.write(chunk)

        if bytes_written == 0:
            raise DocumentUploadError("Uploaded file cannot be empty.")
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    return SavedUpload(
        absolute_path=target_path,
        source_path=_source_path_for_database(target_path),
    )


def _validated_extension(filename: str | None, content_type: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise DocumentUploadError(
            "Only PDF, Markdown, and plain text files are supported."
        )

    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_content_type not in ALLOWED_UPLOAD_CONTENT_TYPES[extension]:
        raise DocumentUploadError("File content type does not match an allowed type.")

    return extension


def _resolved_upload_dir(upload_dir: Path) -> Path:
    if upload_dir.is_absolute():
        return upload_dir.resolve()

    return (PROJECT_ROOT / upload_dir).resolve()


def _resolved_extracted_text_dir(extracted_text_dir: Path) -> Path:
    if extracted_text_dir.is_absolute():
        return extracted_text_dir.resolve()

    return (PROJECT_ROOT / extracted_text_dir).resolve()


def _resolved_document_source_path(source_path: str, settings: Settings) -> Path:
    upload_dir = _resolved_upload_dir(settings.upload_dir)
    candidate_path = Path(source_path)
    if candidate_path.is_absolute():
        resolved_source_path = candidate_path.resolve()
    else:
        resolved_source_path = (PROJECT_ROOT / candidate_path).resolve()

    if not resolved_source_path.is_relative_to(upload_dir):
        raise DocumentTextExtractionError(
            "Document source path is outside the configured upload directory."
        )

    if not resolved_source_path.is_file():
        raise DocumentTextExtractionError("Source file not found.", status_code=404)

    return resolved_source_path


def _save_extracted_text(
    document_id: int,
    text: str,
    settings: Settings,
) -> SavedExtraction:
    extracted_text_dir = _resolved_extracted_text_dir(settings.extracted_text_dir)
    extracted_text_dir.mkdir(parents=True, exist_ok=True)

    target_path = (extracted_text_dir / f"document-{document_id}.txt").resolve()
    if not target_path.is_relative_to(extracted_text_dir):
        raise DocumentTextExtractionError(
            "Extraction path is outside the configured directory.",
            status_code=500,
        )

    try:
        target_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise DocumentTextExtractionError(
            "Failed to save extracted text.",
            status_code=500,
        ) from exc

    return SavedExtraction(
        extracted_text_path=_source_path_for_database(target_path),
        character_count=len(text),
    )


def _update_document_status(
    db: Session,
    document: Document,
    status: DocumentStatus,
) -> None:
    document.status = status.value
    db.add(document)
    db.commit()
    db.refresh(document)


def _source_path_for_database(target_path: Path) -> str:
    try:
        return target_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return target_path.as_posix()

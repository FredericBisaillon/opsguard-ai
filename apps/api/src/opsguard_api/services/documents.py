from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from opsguard_api.config import PROJECT_ROOT, Settings
from opsguard_api.constants import DEFAULT_EMBEDDING_DIMENSIONS
from opsguard_api.models import Document, DocumentChunk, DocumentStatus
from opsguard_api.schemas import DocumentCreate
from opsguard_api.services.embeddings import (
    EmbeddingClient,
    EmbeddingClientError,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)

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


class DocumentChunkingError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DocumentEmbeddingError(Exception):
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


@dataclass(frozen=True)
class DocumentChunkingResult:
    document_id: int
    status: str
    chunk_count: int
    chunk_max_chars: int
    chunk_overlap_chars: int
    message: str


@dataclass(frozen=True)
class DocumentEmbeddingResult:
    document_id: int
    status: str
    embedding_model: str
    embedding_dimensions: int
    embedded_chunk_count: int
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


def chunk_document(
    db: Session,
    document_id: int,
    settings: Settings,
) -> DocumentChunkingResult:
    from opsguard_api.services.chunking import chunk_text

    document = db.get(Document, document_id)
    if document is None:
        raise DocumentChunkingError("Document not found.", status_code=404)

    if document.status not in {
        DocumentStatus.TEXT_EXTRACTED.value,
        DocumentStatus.CHUNKED.value,
        DocumentStatus.CHUNKING_FAILED.value,
    }:
        raise DocumentChunkingError(
            "Document text must be extracted before chunking.",
            status_code=409,
        )

    try:
        _validate_chunking_settings(settings)
        extracted_text_path = _resolved_extracted_text_path(document.id, settings)
        _update_document_status(db, document, DocumentStatus.CHUNKING)

        try:
            extracted_text = extracted_text_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DocumentChunkingError(
                "Failed to read extracted text.",
                status_code=500,
            ) from exc

        if not extracted_text.strip():
            raise DocumentChunkingError("Extracted text is empty.")

        text_chunks = chunk_text(
            text=extracted_text,
            max_chars=settings.chunk_max_chars,
            overlap_chars=settings.chunk_overlap_chars,
        )
        if not text_chunks:
            raise DocumentChunkingError("Extracted text did not produce any chunks.")

        db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        db.add_all(
            [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=text_chunk.chunk_index,
                    content=text_chunk.content,
                    character_count=text_chunk.character_count,
                    section_title=text_chunk.section_title,
                    start_char=text_chunk.start_char,
                    end_char=text_chunk.end_char,
                )
                for text_chunk in text_chunks
            ]
        )
        document.status = DocumentStatus.CHUNKED.value
        db.add(document)
        db.commit()
        db.refresh(document)

        return DocumentChunkingResult(
            document_id=document.id,
            status=DocumentStatus.CHUNKED.value,
            chunk_count=len(text_chunks),
            chunk_max_chars=settings.chunk_max_chars,
            chunk_overlap_chars=settings.chunk_overlap_chars,
            message="Document chunked successfully.",
        )
    except DocumentChunkingError:
        _update_document_status(db, document, DocumentStatus.CHUNKING_FAILED)
        raise
    except ValueError as exc:
        _update_document_status(db, document, DocumentStatus.CHUNKING_FAILED)
        raise DocumentChunkingError(str(exc), status_code=500) from exc


def list_document_chunks(db: Session, document_id: int) -> list[DocumentChunk]:
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentChunkingError("Document not found.", status_code=404)

    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(db.scalars(statement).all())


def embed_document_chunks(
    db: Session,
    document_id: int,
    settings: Settings,
    embedding_client: EmbeddingClient,
) -> DocumentEmbeddingResult:
    document = db.get(Document, document_id)
    if document is None:
        raise DocumentEmbeddingError("Document not found.", status_code=404)

    if document.status not in {
        DocumentStatus.CHUNKED.value,
        DocumentStatus.EMBEDDED.value,
        DocumentStatus.EMBEDDING_FAILED.value,
    }:
        raise DocumentEmbeddingError(
            "Document must be chunked before embedding.",
            status_code=409,
        )

    chunks = _document_chunks_for_embedding(db, document.id)
    if not chunks:
        raise DocumentEmbeddingError(
            "Document has no chunks to embed.",
            status_code=409,
        )

    try:
        _validate_embedding_settings(settings, embedding_client)
        embedding_client.validate_configuration()
    except EmbeddingConfigurationError as exc:
        raise DocumentEmbeddingError(exc.message, status_code=500) from exc

    try:
        _update_document_status(db, document, DocumentStatus.EMBEDDING)
        embedded_chunk_count = 0

        for chunk_batch in _batched(chunks, settings.embedding_batch_size):
            embeddings = embedding_client.embed_texts(
                [chunk.content for chunk in chunk_batch]
            )
            if len(embeddings) != len(chunk_batch):
                raise DocumentEmbeddingError(
                    "Embedding provider returned an unexpected number of vectors.",
                    status_code=502,
                )

            for chunk, embedding in zip(chunk_batch, embeddings, strict=True):
                _validate_embedding_vector(embedding, embedding_client.dimensions)
                chunk.embedding = embedding
                db.add(chunk)
                embedded_chunk_count += 1

        document.status = DocumentStatus.EMBEDDED.value
        db.add(document)
        db.commit()
        db.refresh(document)

        return DocumentEmbeddingResult(
            document_id=document.id,
            status=DocumentStatus.EMBEDDED.value,
            embedding_model=embedding_client.model,
            embedding_dimensions=embedding_client.dimensions,
            embedded_chunk_count=embedded_chunk_count,
            message="Document chunks embedded successfully.",
        )
    except DocumentEmbeddingError:
        db.rollback()
        _update_document_status(db, document, DocumentStatus.EMBEDDING_FAILED)
        raise
    except EmbeddingProviderError as exc:
        db.rollback()
        _update_document_status(db, document, DocumentStatus.EMBEDDING_FAILED)
        raise DocumentEmbeddingError(exc.message, status_code=502) from exc
    except EmbeddingClientError as exc:
        db.rollback()
        _update_document_status(db, document, DocumentStatus.EMBEDDING_FAILED)
        raise DocumentEmbeddingError(exc.message, status_code=500) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        _update_document_status(db, document, DocumentStatus.EMBEDDING_FAILED)
        raise DocumentEmbeddingError(
            "Failed to store embeddings.",
            status_code=500,
        ) from exc


def _document_chunks_for_embedding(
    db: Session,
    document_id: int,
) -> list[DocumentChunk]:
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(db.scalars(statement).all())


def _validate_embedding_settings(
    settings: Settings,
    embedding_client: EmbeddingClient,
) -> None:
    if settings.embedding_dimensions != DEFAULT_EMBEDDING_DIMENSIONS:
        raise EmbeddingConfigurationError(
            "EMBEDDING_DIMENSIONS must match the database vector dimension "
            f"({DEFAULT_EMBEDDING_DIMENSIONS})."
        )

    if embedding_client.dimensions != settings.embedding_dimensions:
        raise EmbeddingConfigurationError(
            "Embedding client dimensions do not match EMBEDDING_DIMENSIONS."
        )


def _validate_embedding_vector(
    embedding: list[float],
    expected_dimensions: int,
) -> None:
    if len(embedding) != expected_dimensions:
        raise DocumentEmbeddingError(
            "Embedding provider returned vectors with unexpected dimensions.",
            status_code=502,
        )


def _batched(
    chunks: list[DocumentChunk],
    batch_size: int,
) -> list[list[DocumentChunk]]:
    return [
        chunks[index : index + batch_size]
        for index in range(0, len(chunks), batch_size)
    ]


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


def _resolved_extracted_text_path(document_id: int, settings: Settings) -> Path:
    extracted_text_dir = _resolved_extracted_text_dir(settings.extracted_text_dir)
    extracted_text_path = (extracted_text_dir / f"document-{document_id}.txt").resolve()
    if not extracted_text_path.is_relative_to(extracted_text_dir):
        raise DocumentChunkingError(
            "Extracted text path is outside the configured directory.",
            status_code=500,
        )

    if not extracted_text_path.is_file():
        raise DocumentChunkingError("Extracted text file not found.", status_code=404)

    return extracted_text_path


def _validate_chunking_settings(settings: Settings) -> None:
    if settings.chunk_overlap_chars >= settings.chunk_max_chars:
        raise DocumentChunkingError(
            "CHUNK_OVERLAP_CHARS must be smaller than CHUNK_MAX_CHARS.",
            status_code=500,
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

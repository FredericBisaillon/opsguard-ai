from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

TEXT_EXTENSIONS = {".md", ".txt"}
PDF_EXTENSION = ".pdf"
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {PDF_EXTENSION}


class TextExtractionError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def extract_text(source_path: Path) -> str:
    extension = source_path.suffix.lower()

    if extension in TEXT_EXTENSIONS:
        return _extract_utf8_text(source_path)

    if extension == PDF_EXTENSION:
        return _extract_pdf_text(source_path)

    raise TextExtractionError("Document type is not supported for text extraction.")


def _extract_utf8_text(source_path: Path) -> str:
    try:
        text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TextExtractionError("Text files must be UTF-8 encoded.") from exc

    return _require_text(text, "File does not contain extractable text.")


def _extract_pdf_text(source_path: Path) -> str:
    try:
        reader = PdfReader(source_path)
        page_text = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, OSError, KeyError, TypeError, ValueError) as exc:
        raise TextExtractionError("PDF text extraction failed.") from exc

    return _require_text(
        "\n\n".join(text for text in page_text if text),
        "PDF does not contain extractable text.",
    )


def _require_text(text: str, message: str) -> str:
    if not text.strip():
        raise TextExtractionError(message)

    return text

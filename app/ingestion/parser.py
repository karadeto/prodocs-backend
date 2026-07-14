"""Document parsing: bytes -> page-wise markdown.

Primary: docling (layout-aware, handles scans/images via OCR models).
Fallback: pypdf text extraction (dev environments without the docling install;
works for born-digital PDFs only).
"""

import asyncio
import io
import tempfile
from pathlib import Path

from pydantic import BaseModel


class ParsedPage(BaseModel):
    page: int  # 1-based
    markdown: str


class ParseResult(BaseModel):
    pages: list[ParsedPage]
    full_markdown: str


class ParseError(Exception):
    pass


def _docling_available() -> bool:
    try:
        import docling  # noqa: F401
        return True
    except ImportError:
        return False


def _parse_with_docling(data: bytes, suffix: str) -> ParseResult:
    from docling.document_converter import DocumentConverter

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp = Path(f.name)
    try:
        result = DocumentConverter().convert(tmp)
        doc = result.document
        page_numbers = sorted(doc.pages.keys()) if doc.pages else [1]
        pages = []
        for n in page_numbers:
            md = doc.export_to_markdown(page_no=n)
            pages.append(ParsedPage(page=n, markdown=md))
        full = doc.export_to_markdown()
        return ParseResult(pages=pages, full_markdown=full)
    finally:
        tmp.unlink(missing_ok=True)


def _parse_with_pypdf(data: bytes) -> ParseResult:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [
        ParsedPage(page=i + 1, markdown=(p.extract_text() or "").strip())
        for i, p in enumerate(reader.pages)
    ]
    full = "\n\n".join(p.markdown for p in pages)
    if not full.strip():
        raise ParseError(
            "No extractable text (scanned PDF?). Install the 'parse' extra for docling OCR."
        )
    return ParseResult(pages=pages, full_markdown=full)


_SUFFIXES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}


async def parse_document(data: bytes, mime_type: str) -> ParseResult:
    suffix = _SUFFIXES.get(mime_type)
    if suffix is None:
        raise ParseError(f"Unsupported mime type: {mime_type}")

    if _docling_available():
        return await asyncio.to_thread(_parse_with_docling, data, suffix)

    if mime_type != "application/pdf":
        raise ParseError("Image parsing requires docling (install the 'parse' extra).")
    return await asyncio.to_thread(_parse_with_pypdf, data)

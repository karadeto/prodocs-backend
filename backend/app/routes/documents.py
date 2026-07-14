import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.db import get_session
from app.ingestion.routing import ensure_system_folders
from app.ingestion.worker import defer_ingestion
from app.models import Document, DocumentFact, IngestionEvent
from app.storage import get_storage

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _doc_dto(doc: Document) -> dict:
    return {
        "id": str(doc.id),
        "title": doc.title,
        "status": doc.status,
        "needs_review": doc.needs_review,
        "routing_source": doc.routing_source,
        "routing_reason": doc.routing_reason,
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "page_count": doc.page_count,
        "failed_stage": doc.failed_stage,
        "error": doc.error,
        "created_at": doc.created_at.isoformat(),
    }


@router.post("", status_code=201)
async def upload_document(
    file: UploadFile,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME:
        raise HTTPException(415, f"Unsupported file type: {mime}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 50 MB)")
    if not data:
        raise HTTPException(400, "Empty file")

    await ensure_system_folders(session, user_id)

    doc_id = uuid.uuid4()
    filename = file.filename or "document"
    blob_key = f"{user_id}/{doc_id}/{filename}"
    await get_storage().put(blob_key, data, mime)

    doc = Document(
        id=doc_id, user_id=user_id, title=filename, original_filename=filename,
        mime_type=mime, blob_key=blob_key, status="processing",
    )
    session.add(doc)
    await session.commit()

    await defer_ingestion(doc_id)
    return _doc_dto(doc)


@router.get("")
async def list_documents(
    folder_id: UUID | None = None,
    status: str | None = None,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    q = (
        select(Document, DocumentFact)
        .outerjoin(DocumentFact, DocumentFact.document_id == Document.id)
        .where(Document.user_id == user_id)
    )
    if folder_id is not None:
        q = q.where(Document.folder_id == folder_id)
    if status is not None:
        q = q.where(Document.status == status)
    rows = (await session.execute(q.order_by(Document.created_at.desc()).limit(200))).all()
    out = []
    for doc, fact in rows:
        dto = _doc_dto(doc)
        dto["vendor"] = fact.vendor_name if fact else None
        dto["doc_type"] = fact.doc_type if fact else None
        dto["doc_date"] = fact.doc_date.isoformat() if fact and fact.doc_date else None
        dto["total_gross"] = float(fact.total_gross) if fact and fact.total_gross is not None else None
        dto["currency"] = fact.currency if fact else None
        out.append(dto)
    return out


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    doc = await _load(session, user_id, document_id)
    fact = (await session.execute(
        select(DocumentFact).where(DocumentFact.document_id == document_id)
    )).scalar_one_or_none()
    dto = _doc_dto(doc)
    if fact:
        dto["fact"] = {
            "doc_type": fact.doc_type, "vendor": fact.vendor_name,
            "date": fact.doc_date.isoformat() if fact.doc_date else None,
            "total_gross": float(fact.total_gross) if fact.total_gross is not None else None,
            "currency": fact.currency, "identifiers": fact.identifiers, "summary": fact.summary,
        }
    return dto


@router.get("/{document_id}/file")
async def download_document(
    document_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    doc = await _load(session, user_id, document_id)
    url = await get_storage().presigned_url(doc.blob_key)
    if url:
        return RedirectResponse(url, status_code=307)
    data = await get_storage().get(doc.blob_key)
    return Response(content=data, media_type=doc.mime_type)


@router.get("/{document_id}/events")
async def document_events(
    document_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Full ingestion audit trail — every stage and LLM decision for this document."""
    await _load(session, user_id, document_id)  # ownership check
    events = (await session.execute(
        select(IngestionEvent).where(IngestionEvent.document_id == document_id)
        .order_by(IngestionEvent.created_at)
    )).scalars().all()
    return [{"stage": e.stage, "status": e.status, "detail": e.detail, "error": e.error,
             "duration_ms": e.duration_ms, "at": e.created_at.isoformat()} for e in events]


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    doc = await _load(session, user_id, document_id)
    doc.status = "processing"
    doc.error = None
    doc.failed_stage = None
    await session.commit()
    await defer_ingestion(document_id)
    return {"status": "queued"}


async def _load(session: AsyncSession, user_id: UUID, document_id: UUID) -> Document:
    doc = (await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc

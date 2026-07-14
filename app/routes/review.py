"""Review inbox: the human-in-the-loop that makes routing converge.

Confirming or moving a document creates a durable RoutingRule for its vendor,
so the same sender is never LLM-routed again.
"""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.db import get_session
from app.ingestion.routing import normalize_vendor
from app.models import Document, DocumentFact, Folder, RoutingRule

router = APIRouter(prefix="/review", tags=["review"])


@router.get("")
async def review_inbox(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(
        select(Document, DocumentFact)
        .outerjoin(DocumentFact, DocumentFact.document_id == Document.id)
        .where(Document.user_id == user_id, Document.needs_review.is_(True),
               Document.status == "ready")
        .order_by(Document.created_at.desc())
    )).all()
    return [{
        "id": str(doc.id), "title": doc.title,
        "folder_id": str(doc.folder_id) if doc.folder_id else None,
        "routing_source": doc.routing_source, "routing_reason": doc.routing_reason,
        "vendor": fact.vendor_name if fact else None,
        "doc_type": fact.doc_type if fact else None,
        "created_at": doc.created_at.isoformat(),
    } for doc, fact in rows]


class ReviewIn(BaseModel):
    action: Literal["confirm", "move"]
    folder_id: UUID | None = None  # required for "move"


@router.post("/{document_id}")
async def resolve_review(
    document_id: UUID,
    body: ReviewIn,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    doc = (await session.execute(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Document not found")

    if body.action == "move":
        if body.folder_id is None:
            raise HTTPException(400, "folder_id required for move")
        folder = (await session.execute(
            select(Folder).where(Folder.id == body.folder_id, Folder.user_id == user_id)
        )).scalar_one_or_none()
        if folder is None:
            raise HTTPException(404, "Target folder not found")
        doc.folder_id = folder.id
        doc.routing_source = "user"
        doc.routing_reason = "Moved by user in review."

    doc.needs_review = False
    rule_created = await _learn_rule(session, user_id, doc)
    await session.commit()
    return {"status": "ok", "rule_created": rule_created,
            "folder_id": str(doc.folder_id) if doc.folder_id else None}


async def _learn_rule(session: AsyncSession, user_id: UUID, doc: Document) -> bool:
    """vendor -> confirmed folder becomes a permanent deterministic rule."""
    if doc.folder_id is None:
        return False
    fact = (await session.execute(
        select(DocumentFact).where(DocumentFact.document_id == doc.id)
    )).scalar_one_or_none()
    vendor_norm = normalize_vendor(fact.vendor_name if fact else None)
    if not vendor_norm:
        return False
    stmt = (
        pg_insert(RoutingRule)
        .values(user_id=user_id, vendor_normalized=vendor_norm,
                target_folder_id=doc.folder_id, created_from_document_id=doc.id)
        .on_conflict_do_update(
            constraint="ux_rules_user_vendor",
            set_={"target_folder_id": doc.folder_id, "created_from_document_id": doc.id},
        )
    )
    await session.execute(stmt)
    return True

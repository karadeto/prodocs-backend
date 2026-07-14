"""Ingestion pipeline: parse -> extract -> route -> chunk & embed.

Runs inside a procrastinate task. Each stage is logged to ingestion_events
with its full detail (including the LLM's output) so every decision the
system makes is inspectable after the fact.
"""

import logging
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed_batch
from app.config import get_settings
from app.db import session_factory
from app.ingestion import routing
from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import DocumentRecord, count_valid_evidence, evidence_ok, extract_record
from app.ingestion.parser import ParseResult, parse_document
from app.models import Chunk, Document, DocumentFact, IngestionEvent, Party
from app.storage import get_storage

logger = logging.getLogger(__name__)


async def _log_event(
    session: AsyncSession, document_id: UUID, stage: str, status: str,
    detail: dict[str, Any] | None = None, error: str | None = None, started: float | None = None,
) -> None:
    session.add(IngestionEvent(
        document_id=document_id, stage=stage, status=status, detail=detail, error=error,
        duration_ms=int((time.monotonic() - started) * 1000) if started else None,
    ))
    await session.commit()


async def run_pipeline(document_id: UUID) -> None:
    async with session_factory()() as session:
        doc = (
            await session.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if doc is None:
            logger.warning("Document %s not found, skipping", document_id)
            return
        if doc.status == "ready":
            logger.info("Document %s already ready, skipping (idempotent re-run)", document_id)
            return

        stage = "parse"
        try:
            # ── Stage 1: parse (full document, not just page 1) ──
            t = time.monotonic()
            data = await get_storage().get(doc.blob_key)
            parsed = await parse_document(data, doc.mime_type)
            doc.parsed_markdown = parsed.full_markdown
            doc.page_count = len(parsed.pages)
            await _log_event(session, doc.id, stage, "ok",
                             {"pages": len(parsed.pages), "chars": len(parsed.full_markdown)}, started=t)

            # ── Stage 2: extract (one structured LLM pass) ──
            stage = "extract"
            t = time.monotonic()
            record = await extract_record(parsed.full_markdown)
            valid_quotes = count_valid_evidence(record, parsed.full_markdown)
            await _log_event(session, doc.id, stage, "ok",
                             {"record": record.model_dump(mode="json"),
                              "valid_evidence_quotes": valid_quotes}, started=t)

            # ── Stage 3: facts + party ──
            stage = "facts"
            t = time.monotonic()
            party_id = await _upsert_party(session, doc.user_id, record.vendor_name)
            await _upsert_fact(session, doc, record, party_id)
            await _log_event(session, doc.id, stage, "ok", {"party_id": str(party_id) if party_id else None},
                             started=t)

            # ── Stage 4: route to folder (rules -> history -> LLM -> fallback) ──
            stage = "route"
            t = time.monotonic()
            decision = await _route(session, doc, record, parsed, party_id)
            await _log_event(session, doc.id, stage, "ok",
                             {"source": decision.source, "needs_review": decision.needs_review,
                              "reason": decision.reason, "folder_id": str(doc.folder_id)}, started=t)

            # ── Stage 5: chunk & embed ──
            stage = "embed"
            t = time.monotonic()
            n_chunks = await _chunk_and_embed(session, doc, parsed, record)
            await _log_event(session, doc.id, stage, "ok", {"chunks": n_chunks}, started=t)

            doc.status = "ready"
            doc.error = None
            doc.failed_stage = None
            await session.commit()
            logger.info("Document %s ingested: folder=%s review=%s", doc.id, doc.folder_id, doc.needs_review)

        except Exception as e:
            # After rollback every loaded ORM instance is expired — touching `doc`
            # would trigger a (sync) lazy refresh and crash the handler itself.
            # Persist the failure via plain UPDATE on the function argument instead.
            await session.rollback()
            err = str(e)[:2000]
            await session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(status="failed", failed_stage=stage, error=err)
            )
            await _log_event(session, document_id, stage, "error", error=err)
            raise  # let procrastinate retry


async def _route(
    session: AsyncSession, doc: Document, record: DocumentRecord,
    parsed: ParseResult, party_id: UUID | None,
) -> routing.RoutingDecision:
    vendor_norm = routing.normalize_vendor(record.vendor_name)
    rule_folder = await routing.find_rule_folder(session, doc.user_id, vendor_norm)
    history_folder = await routing.find_history_folder(session, doc.user_id, party_id)

    decision = routing.decide(
        rule_folder_id=rule_folder,
        history_folder_id=history_folder,
        llm_code=record.subcategory_code.value if record.subcategory_code else None,
        llm_evidence_ok=evidence_ok(record, parsed.full_markdown),
    )

    if decision.folder_id is not None:
        doc.folder_id = decision.folder_id
    else:
        assert decision.subcategory_code is not None
        doc.folder_id = await routing.resolve_taxonomy_path(
            session, doc.user_id, decision.subcategory_code,
            record.vendor_name, record.doc_date.year if record.doc_date else None,
        )

    doc.needs_review = decision.needs_review
    doc.routing_source = decision.source
    doc.routing_reason = decision.reason
    if record.title.strip():
        doc.title = record.title.strip()[:300]
    return decision


async def _upsert_party(session: AsyncSession, user_id: UUID, vendor_name: str | None) -> UUID | None:
    norm = routing.normalize_vendor(vendor_name)
    if not norm:
        return None
    stmt = (
        pg_insert(Party)
        .values(user_id=user_id, name=vendor_name.strip(), normalized_name=norm)  # type: ignore[union-attr]
        .on_conflict_do_nothing(constraint="ux_parties_user_norm")
    )
    await session.execute(stmt)
    party = (
        await session.execute(
            select(Party).where(Party.user_id == user_id, Party.normalized_name == norm)
        )
    ).scalar_one()
    return party.id


async def _upsert_fact(
    session: AsyncSession, doc: Document, record: DocumentRecord, party_id: UUID | None
) -> None:
    await session.execute(delete(DocumentFact).where(DocumentFact.document_id == doc.id))
    session.add(DocumentFact(
        document_id=doc.id,
        user_id=doc.user_id,
        doc_type=record.doc_type,
        party_id=party_id,
        vendor_name=record.vendor_name,
        doc_date=record.doc_date,
        total_gross=Decimal(str(record.total_gross)) if record.total_gross is not None else None,
        total_net=Decimal(str(record.total_net)) if record.total_net is not None else None,
        currency=record.currency,
        identifiers=record.identifiers,
        summary=record.summary,
    ))


async def _chunk_and_embed(
    session: AsyncSession, doc: Document, parsed: ParseResult, record: DocumentRecord
) -> int:
    s = get_settings()
    pairs = chunk_pages(parsed.pages, s.chunk_target_chars, s.chunk_overlap_chars)
    # The summary is a high-signal retrieval target: embed it as a synthetic chunk.
    if record.summary.strip():
        pairs.insert(0, (1, f"{record.title}\n{record.summary}"))
    if not pairs:
        return 0

    vectors = await embed_batch([c for _, c in pairs])
    await session.execute(delete(Chunk).where(Chunk.document_id == doc.id))  # idempotent re-run
    for (page, content), vec in zip(pairs, vectors):
        session.add(Chunk(document_id=doc.id, user_id=doc.user_id, page=page,
                          content=content, embedding=vec))
    return len(pairs)

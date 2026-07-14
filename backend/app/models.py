import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dimensions


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Folder(Base):
    __tablename__ = "folders"
    # Uniqueness of (user_id, parent, lower(name)) is enforced by a functional
    # index created in scripts/init_db.py (NULL parent needs coalesce).

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)  # taxonomy code for system folders
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (Index("ix_folders_user_code", "user_id", "code"),)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(120))
    blob_key: Mapped[str] = mapped_column(String(500))
    # processing | ready | failed
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    failed_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Review inbox: document is filed to folder_id but awaits user confirmation.
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    routing_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # rule|history|llm|fallback
    routing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    parsed_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    page: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # 'simple' config: language-neutral tokenization (the product supports 7 languages;
    # semantic matching is the vector index's job, FTS covers exact terms/numbers/names).
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True))

    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )


class Party(Base):
    __tablename__ = "parties"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (UniqueConstraint("user_id", "normalized_name", name="ux_parties_user_norm"),)


class DocumentFact(Base):
    """One structured record per document, extracted in a single LLM pass."""

    __tablename__ = "document_facts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    doc_type: Mapped[str] = mapped_column(String(40), index=True)
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parties.id", ondelete="SET NULL"), nullable=True
    )
    vendor_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    total_gross: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_net: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    identifiers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class RoutingRule(Base):
    """Durable, deterministic routing learned from user corrections.

    Matches on normalized vendor name; rules always win over the LLM.
    """

    __tablename__ = "routing_rules"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    vendor_normalized: Mapped[str] = mapped_column(String(300))
    target_folder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"))
    created_from_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _created_at()

    __table_args__ = (UniqueConstraint("user_id", "vendor_normalized", name="ux_rules_user_vendor"),)


class IngestionEvent(Base):
    """Append-only audit log: every pipeline stage, every LLM decision, with detail."""

    __tablename__ = "ingestion_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # ok | error
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Full pydantic-ai message history (serialized ModelMessages) so multi-turn
    # context including tool calls survives across requests.
    model_messages: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()

"""Hybrid search: pgvector cosine + Postgres FTS, merged with Reciprocal Rank Fusion."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import embed_one
from app.models import Chunk, Document

RRF_K = 60
CANDIDATES = 50


@dataclass
class SearchHit:
    chunk_id: int
    document_id: UUID
    title: str
    page: int
    content: str
    score: float


async def hybrid_search(
    session: AsyncSession, user_id: UUID, query: str, top_k: int = 8
) -> list[SearchHit]:
    qvec = await embed_one(query)

    base_cols = (Chunk.id, Chunk.document_id, Chunk.page, Chunk.content, Document.title)
    base = (
        select(*base_cols)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.user_id == user_id, Document.status == "ready")
    )

    vec_rows = (
        await session.execute(
            base.where(Chunk.embedding.is_not(None))
            .order_by(Chunk.embedding.cosine_distance(qvec))
            .limit(CANDIDATES)
        )
    ).all()

    fts_rows = (
        await session.execute(
            base.where(text("chunks.tsv @@ websearch_to_tsquery('simple', :q)"))
            .order_by(text("ts_rank_cd(chunks.tsv, websearch_to_tsquery('simple', :q)) DESC"))
            .limit(CANDIDATES)
            .params(q=query)
        )
    ).all()

    # RRF merge
    scores: dict[int, float] = {}
    rows_by_id: dict[int, tuple] = {}
    for rank, row in enumerate(vec_rows):
        scores[row.id] = scores.get(row.id, 0.0) + 1.0 / (RRF_K + rank + 1)
        rows_by_id[row.id] = row
    for rank, row in enumerate(fts_rows):
        scores[row.id] = scores.get(row.id, 0.0) + 1.0 / (RRF_K + rank + 1)
        rows_by_id[row.id] = row

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [
        SearchHit(
            chunk_id=cid,
            document_id=rows_by_id[cid].document_id,
            title=rows_by_id[cid].title,
            page=rows_by_id[cid].page,
            content=rows_by_id[cid].content,
            score=score,
        )
        for cid, score in ranked
    ]

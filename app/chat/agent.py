"""Chat: one agentic tool loop instead of an intent-router tower.

The model decides per turn whether to hit hybrid search (unstructured
questions), the facts table (amounts, dates, aggregations), a full document,
or the folder tree. Ambiguity is handled by the model asking back — no
disambiguation state machine, no TTLs, no keyword heuristics.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic_ai import Agent, RunContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import build_model
from app.config import get_settings
from app.models import Document, DocumentFact, Folder, Party
from app.retrieval.hybrid import hybrid_search


@dataclass
class ChatDeps:
    user_id: UUID
    session: AsyncSession
    sources: list[dict[str, Any]] = field(default_factory=list)

    def add_source(self, document_id: UUID, title: str, page: int | None = None) -> None:
        entry = {"document_id": str(document_id), "title": title, "page": page}
        if entry not in self.sources:
            self.sources.append(entry)


SYSTEM_PROMPT = """You are the assistant inside ProDocs, a personal document management app. \
You answer questions strictly from the user's own documents, which you access through tools.

Rules:
- Always ground answers in tool results. If the tools return nothing relevant, say so \
plainly — never invent document contents, amounts, or dates.
- For questions about amounts, totals, counts, or date ranges, prefer query_facts \
(structured data) over text search.
- NEVER conclude "no records" from a single filtered query. If a filtered query_facts \
returns nothing, broaden step by step: drop the date range, then try a shorter vendor \
term, then search_documents. Report what you DID find — e.g. if the user asks about \
this year but the matching purchases are from last year, say exactly that with the \
amounts.
- For content questions ("what does my contract say about X"), use search_documents, \
then get_document if you need the full text.
- Cite documents you used by their title.
- If the question is ambiguous (e.g. several matching documents), ask one short \
clarifying question instead of guessing.
- Answer in the language the user's question was written in (not the documents' language).
"""


def build_chat_agent() -> Agent[ChatDeps, str]:
    agent: Agent[ChatDeps, str] = Agent(
        build_model(get_settings().chat_model),
        deps_type=ChatDeps,
        retries=2,
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.system_prompt
    def add_today(ctx: RunContext[ChatDeps]) -> str:  # evaluated per run, not at process start
        return f"Today's date: {date.today().isoformat()}."

    @agent.tool
    async def search_documents(ctx: RunContext[ChatDeps], query: str) -> list[dict[str, Any]]:
        """Hybrid semantic + keyword search over the user's documents.
        Returns matching text chunks with document id, title and page."""
        hits = await hybrid_search(ctx.deps.session, ctx.deps.user_id, query, top_k=8)
        for h in hits:
            ctx.deps.add_source(h.document_id, h.title, h.page)
        return [
            {"document_id": str(h.document_id), "title": h.title, "page": h.page,
             "excerpt": h.content[:1200]}
            for h in hits
        ]

    @agent.tool
    async def query_facts(
        ctx: RunContext[ChatDeps],
        doc_type: str | None = None,
        vendor: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        aggregate: Literal["list", "sum", "count"] = "list",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Query structured facts extracted from documents (type, vendor, date, amounts).
        Use for questions about totals, counts, spending, or listing documents by
        vendor/type/date range. doc_type examples: invoice, receipt, contract,
        insurance_policy, bank_statement, payslip, government_letter, medical, tax."""
        f, d = DocumentFact, Document
        conds = [f.user_id == ctx.deps.user_id, d.status == "ready"]
        if doc_type:
            conds.append(f.doc_type == doc_type)
        if vendor:
            pattern = f"%{vendor.strip()}%"
            conds.append(
                f.vendor_name.ilike(pattern)
                | f.party_id.in_(
                    select(Party.id).where(
                        Party.user_id == ctx.deps.user_id, Party.name.ilike(pattern)
                    )
                )
            )
        if date_from:
            conds.append(f.doc_date >= date_from)
        if date_to:
            conds.append(f.doc_date <= date_to)

        # Every branch must join documents explicitly — `conds` references
        # Document.status, and a bare .where() would cross-join (cartesian product).
        joined = select(f, d.title).join(d, d.id == f.document_id).where(*conds)

        if aggregate == "count":
            n = (await ctx.deps.session.execute(
                select(func.count()).select_from(joined.subquery())
            )).scalar_one()
            return {"count": n}

        if aggregate == "sum":
            totals = (await ctx.deps.session.execute(
                select(f.currency, func.sum(f.total_gross), func.count(f.total_gross))
                .select_from(f).join(d, d.id == f.document_id)
                .where(*conds, f.total_gross.is_not(None))
                .group_by(f.currency)
            )).all()
            contributing = (await ctx.deps.session.execute(
                joined.where(f.total_gross.is_not(None))
                .order_by(f.doc_date.desc().nulls_last()).limit(20)
            )).all()
            for fact, title in contributing:
                ctx.deps.add_source(fact.document_id, title)
            return {
                "totals": [
                    {"currency": cur or "unknown", "sum_gross": float(total), "documents": n}
                    for cur, total, n in totals
                ],
                "contributing_documents": [
                    {"document_id": str(fact.document_id), "title": title,
                     "date": fact.doc_date.isoformat() if fact.doc_date else None,
                     "gross": float(fact.total_gross)}
                    for fact, title in contributing
                ],
            }

        rows = (await ctx.deps.session.execute(
            joined.order_by(f.doc_date.desc().nulls_last()).limit(min(limit, 50))
        )).all()
        for fact, title in rows:
            ctx.deps.add_source(fact.document_id, title)
        return {"documents": [
            {"document_id": str(fact.document_id), "title": title, "doc_type": fact.doc_type,
             "vendor": fact.vendor_name, "date": fact.doc_date.isoformat() if fact.doc_date else None,
             "total_gross": float(fact.total_gross) if fact.total_gross is not None else None,
             "currency": fact.currency, "identifiers": fact.identifiers}
            for fact, title in rows
        ]}

    @agent.tool
    async def get_document(ctx: RunContext[ChatDeps], document_id: str) -> dict[str, Any]:
        """Fetch the full text of one document. Pass the document_id from a previous
        tool result; if you only have the title, pass the exact title instead."""
        q = select(Document).where(Document.user_id == ctx.deps.user_id)
        try:
            q = q.where(Document.id == UUID(document_id.strip()))
        except ValueError:
            # Model passed a title, not an id — resolve by title match.
            q = q.where(Document.title.ilike(f"%{document_id.strip()}%")).limit(1)
        doc = (await ctx.deps.session.execute(q)).scalars().first()
        if doc is None:
            return {"error": "No document found for that id or title. "
                             "Use search_documents or query_facts to locate it first."}
        ctx.deps.add_source(doc.id, doc.title)
        return {"title": doc.title, "pages": doc.page_count,
                "text": (doc.parsed_markdown or "")[:24_000]}

    @agent.tool
    async def list_folders(ctx: RunContext[ChatDeps]) -> list[dict[str, Any]]:
        """List the user's folder tree (id, name, parent_id)."""
        folders = (await ctx.deps.session.execute(
            select(Folder).where(Folder.user_id == ctx.deps.user_id)
        )).scalars().all()
        return [
            {"id": str(f.id), "name": f.name,
             "parent_id": str(f.parent_id) if f.parent_id else None}
            for f in folders
        ]

    return agent


_chat_agent: Agent[ChatDeps, str] | None = None


def get_chat_agent() -> Agent[ChatDeps, str]:
    global _chat_agent
    if _chat_agent is None:
        _chat_agent = build_chat_agent()
    return _chat_agent

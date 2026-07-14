"""Folder routing: deterministic-first cascade.

Priority:
  1. RoutingRule (learned from user corrections)   -> auto-file, no review
  2. Vendor history (where this vendor's docs live) -> auto-file, no review
  3. LLM taxonomy code, evidence-validated          -> file + review inbox
  4. Fallback to Sonstiges                          -> file + review inbox

The decide() function is pure and fully unit-testable; DB access lives in
the surrounding service functions.
"""

import difflib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentFact, Folder, RoutingRule
from app.taxonomy import FALLBACK_CODE, TAXONOMY, parent_category

VENDOR_FOLDER_MATCH_THRESHOLD = 0.85
NO_DATE_FOLDER_NAME = "Kein Datum"

_LEGAL_SUFFIXES = {
    "gmbh", "ag", "ug", "se", "kg", "ohg", "kgaa", "co", "gbr", "ev", "e", "v",
    "inc", "incorporated", "corp", "corporation", "llc",
    "ltd", "limited", "plc", "bv", "nv", "sa", "spa", "srl", "sarl", "sl",
}


def normalize_vendor(name: str | None) -> str:
    """Lowercase, fold umlauts, strip punctuation and legal suffixes."""
    if not name:
        return ""
    s = name.strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = "".join(ch if ch.isalnum() else " " for ch in s)
    tokens = [t for t in s.split() if t not in _LEGAL_SUFFIXES]
    return " ".join(tokens)


RoutingSource = Literal["rule", "history", "llm", "fallback"]


@dataclass(frozen=True)
class RoutingDecision:
    source: RoutingSource
    needs_review: bool
    # Direct target (rule / history) …
    folder_id: UUID | None = None
    # … or a taxonomy path to resolve deterministically (llm / fallback).
    subcategory_code: str | None = None
    reason: str = ""


def decide(
    *,
    rule_folder_id: UUID | None,
    history_folder_id: UUID | None,
    llm_code: str | None,
    llm_evidence_ok: bool,
) -> RoutingDecision:
    """Pure routing decision. Deterministic sources always beat the LLM."""
    if rule_folder_id is not None:
        return RoutingDecision("rule", needs_review=False, folder_id=rule_folder_id,
                               reason="Matched user routing rule for this vendor.")
    if history_folder_id is not None:
        return RoutingDecision("history", needs_review=False, folder_id=history_folder_id,
                               reason="Vendor's previous documents live in this folder.")
    if llm_code and llm_code != FALLBACK_CODE and llm_evidence_ok:
        return RoutingDecision("llm", needs_review=True, subcategory_code=llm_code,
                               reason=f"LLM classification ({llm_code}), evidence verified.")
    if llm_code and not llm_evidence_ok:
        return RoutingDecision("fallback", needs_review=True, subcategory_code=FALLBACK_CODE,
                               reason=f"LLM suggested {llm_code} but evidence quotes did not "
                                      "match the document text.")
    return RoutingDecision("fallback", needs_review=True, subcategory_code=FALLBACK_CODE,
                           reason="No rule, no history, no confident classification.")


# ────────────────────────────────────────────────────────────────
#  DB lookups feeding decide()
# ────────────────────────────────────────────────────────────────

async def find_rule_folder(session: AsyncSession, user_id: UUID, vendor_norm: str) -> UUID | None:
    if not vendor_norm:
        return None
    rule = (
        await session.execute(
            select(RoutingRule).where(
                RoutingRule.user_id == user_id,
                RoutingRule.vendor_normalized == vendor_norm,
            )
        )
    ).scalar_one_or_none()
    if rule is None:
        return None
    rule.hits += 1
    return rule.target_folder_id


async def find_history_folder(session: AsyncSession, user_id: UUID, party_id: UUID | None) -> UUID | None:
    """Majority folder of previously confirmed (not needs_review) docs of this party."""
    if party_id is None:
        return None
    row = (
        await session.execute(
            select(Document.folder_id, func.count().label("n"))
            .join(DocumentFact, DocumentFact.document_id == Document.id)
            .where(
                Document.user_id == user_id,
                DocumentFact.party_id == party_id,
                Document.status == "ready",
                Document.needs_review.is_(False),
                Document.folder_id.is_not(None),
            )
            .group_by(Document.folder_id)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()
    return row.folder_id if row else None


# ────────────────────────────────────────────────────────────────
#  Deterministic folder resolution (taxonomy code -> vendor -> year)
# ────────────────────────────────────────────────────────────────

async def get_or_create_folder(
    session: AsyncSession,
    user_id: UUID,
    parent_id: UUID | None,
    name: str,
    *,
    is_system: bool = False,
    code: str | None = None,
    icon: str | None = None,
) -> Folder:
    """Race-safe get-or-create backed by the unique (user, parent, lower(name)) index."""
    existing = await _find_child_by_name(session, user_id, parent_id, name)
    if existing is not None:
        return existing
    stmt = (
        pg_insert(Folder)
        .values(user_id=user_id, parent_id=parent_id, name=name,
                is_system=is_system, code=code, icon=icon)
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)
    created = await _find_child_by_name(session, user_id, parent_id, name)
    assert created is not None
    return created


async def _find_child_by_name(
    session: AsyncSession, user_id: UUID, parent_id: UUID | None, name: str
) -> Folder | None:
    q = select(Folder).where(
        Folder.user_id == user_id,
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id,
        func.lower(Folder.name) == name.lower(),
    )
    return (await session.execute(q)).scalars().first()


async def ensure_system_folders(session: AsyncSession, user_id: UUID) -> None:
    """Idempotent seed of the taxonomy folder tree for a user."""
    for cat in TAXONOMY:
        parent = await get_or_create_folder(
            session, user_id, None, cat.name_de, is_system=True, code=cat.code, icon=cat.icon
        )
        for sub in cat.subs:
            if sub.code == cat.code:  # single-sub categories (Sonstiges) collapse into the parent
                continue
            await get_or_create_folder(
                session, user_id, parent.id, sub.name_de, is_system=True, code=sub.code
            )


async def get_folder_by_code(session: AsyncSession, user_id: UUID, code: str) -> Folder | None:
    q = select(Folder).where(Folder.user_id == user_id, Folder.code == code, Folder.is_system.is_(True))
    folder = (await session.execute(q)).scalars().first()
    if folder is None:
        await ensure_system_folders(session, user_id)
        folder = (await session.execute(q)).scalars().first()
    return folder


def match_existing_vendor_folder(candidates: list[Folder], vendor_norm: str) -> Folder | None:
    """Fuzzy-match vendor against existing child folders; None means create new."""
    best: tuple[float, Folder] | None = None
    for f in candidates:
        if f.is_system:
            continue
        score = difflib.SequenceMatcher(None, vendor_norm, normalize_vendor(f.name)).ratio()
        if best is None or score > best[0]:
            best = (score, f)
    if best and best[0] >= VENDOR_FOLDER_MATCH_THRESHOLD:
        return best[1]
    return None


async def resolve_taxonomy_path(
    session: AsyncSession,
    user_id: UUID,
    subcategory_code: str,
    vendor_name: str | None,
    year: int | None,
) -> UUID:
    """subcategory folder -> vendor folder -> year folder, creating as needed."""
    sub_folder = await get_folder_by_code(session, user_id, subcategory_code)
    if sub_folder is None:  # taxonomy folder missing even after seed: file to category root
        cat = parent_category(subcategory_code)
        sub_folder = await get_or_create_folder(
            session, user_id, None, cat.name_de, is_system=True, code=cat.code, icon=cat.icon
        )

    if subcategory_code == FALLBACK_CODE or not vendor_name:
        return sub_folder.id

    children = list(
        (await session.execute(select(Folder).where(Folder.parent_id == sub_folder.id))).scalars()
    )
    vendor_folder = match_existing_vendor_folder(children, normalize_vendor(vendor_name))
    if vendor_folder is None:
        vendor_folder = await get_or_create_folder(session, user_id, sub_folder.id, vendor_name.strip())

    year_name = str(year) if year else NO_DATE_FOLDER_NAME
    year_folder = await get_or_create_folder(session, user_id, vendor_folder.id, year_name)
    return year_folder.id

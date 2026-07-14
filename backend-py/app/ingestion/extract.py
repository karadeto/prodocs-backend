"""Single-pass structured extraction.

One LLM call per document produces one validated pydantic object: document
type, vendor, date, amounts, identifiers, taxonomy code, title, and verbatim
evidence quotes. Strict schema enforcement replaces JSON-repair prompts;
evidence validation replaces trusting the model's self-reported confidence.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.ai.llm import build_model
from app.config import get_settings
from app.taxonomy import SubcategoryCode, render_for_prompt

MIN_EVIDENCE_QUOTE_LEN = 8
REQUIRED_VALID_QUOTES = 2

# Closed set — a free string here led to taxonomy codes leaking into doc_type.
DocType = Literal[
    "invoice", "receipt", "contract", "insurance_policy", "bank_statement",
    "payslip", "government_letter", "medical", "tax", "other",
]


class DocumentRecord(BaseModel):
    """Everything we extract from a document, in one pass."""

    doc_type: DocType = Field(description="The kind of document.")
    vendor_name: str | None = Field(
        None, description="The brand/organization the user would search for, without legal "
        "suffix like GmbH/AG. For marketplace purchases (Amazon, eBay, Otto...) this is the "
        "MARKETPLACE brand, with the third-party seller in identifiers.seller. "
        "null if the sender is a private person or unclear."
    )
    doc_date: date | None = Field(
        None, description="Primary document date (invoice date, letter date). null if absent."
    )
    total_gross: float | None = Field(None, description="Gross total amount if this is an invoice/receipt.")
    total_net: float | None = Field(None, description="Net total amount if stated.")
    currency: str | None = Field(None, description="ISO currency code, e.g. EUR.")
    identifiers: dict[str, str] = Field(
        default_factory=dict,
        description="Reference numbers found, keyed by type: invoice_number, customer_number, "
        "contract_number, iban, policy_number, case_number.",
    )
    subcategory_code: SubcategoryCode | None = Field(
        None, description="The single best-fitting taxonomy code, or null if none fits."
    )
    title: str = Field(description="Short human-readable title, e.g. 'Telekom Rechnung März 2026'. "
                       "In the document's language. No file extension.")
    summary: str = Field(description="1-2 sentence summary in the document's language.")
    evidence_quotes: list[str] = Field(
        description="2-4 short VERBATIM quotes from the document text that justify the "
        "subcategory choice. Copy exactly, character for character."
    )


_SYSTEM_PROMPT = f"""You extract structured data from personal/business documents \
(German market, but documents may be in any language).

Rules:
- Extract only what is actually in the document. Use null when unsure — never guess.
- vendor_name is the organization the user would recognize and search for — the sender/brand, \
not the recipient. On marketplace documents (Amazon, eBay, Otto...) use the marketplace brand \
(e.g. "Amazon") and put the third-party seller into identifiers.seller.
- Pick at most ONE subcategory_code; prefer the specific over the generic. \
If genuinely nothing fits, use null (NOT the SONST code).
- evidence_quotes must be copied verbatim from the document text.

Available subcategories:

{render_for_prompt()}
"""

_agent: Agent | None = None


def _get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            build_model(get_settings().extract_model),
            output_type=DocumentRecord,
            system_prompt=_SYSTEM_PROMPT,
            retries=2,
        )
    return _agent


async def extract_record(markdown: str) -> DocumentRecord:
    limit = get_settings().extract_max_chars
    text = markdown[:limit]
    result = await _get_agent().run(f"Document text:\n\n{text}")
    return result.output


def _normalize_for_match(s: str) -> str:
    """Whitespace- and case-insensitive form: PDF text extraction mangles spacing
    (glued/split words), so exact `in` matching rejects honest quotes. Stripping
    all whitespace keeps the anti-hallucination property — the characters must
    still exist in the document — without punishing extraction artifacts."""
    return "".join(s.split()).casefold()


def count_valid_evidence(record: DocumentRecord, source_text: str) -> int:
    """How many evidence quotes actually appear in the document."""
    haystack = _normalize_for_match(source_text)
    n = 0
    for quote in record.evidence_quotes:
        q = _normalize_for_match(quote)
        if len(q) >= MIN_EVIDENCE_QUOTE_LEN and q in haystack:
            n += 1
    return n


def evidence_ok(record: DocumentRecord, source_text: str) -> bool:
    return count_valid_evidence(record, source_text) >= REQUIRED_VALID_QUOTES

"""Folder taxonomy: a small, closed set of category codes.

The LLM's only classification job is to pick one of these codes (or none).
Everything after that — folder resolution, vendor folders, year folders — is
deterministic code. Keep this list short; every extra category costs accuracy.
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class Sub:
    code: str
    name_de: str
    name_en: str
    hint: str  # shown to the LLM: what belongs here / what does NOT


@dataclass(frozen=True)
class Category:
    code: str
    name_de: str
    name_en: str
    icon: str
    subs: tuple[Sub, ...]


TAXONOMY: tuple[Category, ...] = (
    Category("WOHN", "Wohnen", "Housing", "🏠", (
        Sub("WOHN-MIETE", "Mietvertrag & Miete", "Rent & lease",
            "Rental contracts, rent increases, landlord letters. NOT utility bills."),
        Sub("WOHN-NEBEN", "Nebenkosten", "Utility statements",
            "Nebenkostenabrechnung, water, waste, building service charges."),
        Sub("WOHN-ENERGIE", "Strom & Gas", "Electricity & gas",
            "Energy provider contracts, bills, meter readings, price changes."),
    )),
    Category("VERS", "Versicherungen", "Insurance", "🛡️", (
        Sub("VERS-KRANKEN", "Krankenversicherung", "Health insurance",
            "Health insurers (AOK, TK, Barmer, private), contribution notices, benefit letters."),
        Sub("VERS-HAFT", "Haftpflicht & Hausrat", "Liability & household",
            "Liability, household contents, legal protection policies and invoices."),
        Sub("VERS-KFZ", "Kfz-Versicherung", "Vehicle insurance",
            "Car/motorbike insurance. NOT repair invoices or vehicle purchase."),
        Sub("VERS-LEBEN", "Leben & Vorsorge", "Life & pension",
            "Life insurance, disability, private pension (Riester, Rürup), annual statements."),
    )),
    Category("FIN", "Finanzen", "Finance", "💶", (
        Sub("FIN-BANK", "Bank & Konto", "Banking",
            "Bank statements, account contracts, card letters, interest statements."),
        Sub("FIN-KREDIT", "Kredite & Darlehen", "Loans",
            "Loan contracts, repayment plans, payoff confirmations."),
        Sub("FIN-STEUER", "Steuern", "Taxes",
            "Tax returns, assessments (Steuerbescheid), tax office letters, receipts for tax."),
    )),
    Category("ARB", "Arbeit", "Work", "💼", (
        Sub("ARB-VERTRAG", "Arbeitsvertrag", "Employment contract",
            "Employment contracts, amendments, references (Zeugnis), termination letters."),
        Sub("ARB-GEHALT", "Gehaltsabrechnung", "Payslips",
            "Monthly payslips, bonus statements, Lohnsteuerbescheinigung."),
        Sub("ARB-SOZIAL", "Sozialleistungen", "Social benefits",
            "Arbeitsagentur, Jobcenter, Kindergeld, Elterngeld notices."),
    )),
    Category("GES", "Gesundheit", "Health", "🏥", (
        Sub("GES-ARZT", "Arzt & Befunde", "Doctors & reports",
            "Medical reports, lab results, referral letters, hospital documents."),
        Sub("GES-RECH", "Arztrechnungen", "Medical invoices",
            "Invoices from doctors, dentists, pharmacies, physiotherapy."),
    )),
    Category("KFZ", "Fahrzeug", "Vehicle", "🚗", (
        Sub("KFZ-KAUF", "Kauf & Papiere", "Purchase & papers",
            "Purchase contracts, registration (Zulassung), TÜV/HU reports."),
        Sub("KFZ-WERK", "Werkstatt & Wartung", "Repairs & service",
            "Repair and service invoices, tyre storage. NOT insurance."),
    )),
    Category("SHOP", "Einkäufe", "Purchases", "🛒", (
        Sub("SHOP-RECH", "Rechnungen & Quittungen", "Invoices & receipts",
            "Online/retail purchase invoices and receipts (Amazon, MediaMarkt...). "
            "NOT recurring subscriptions, NOT utility or medical invoices."),
        Sub("SHOP-GARANTIE", "Garantie & Gewährleistung", "Warranty",
            "Warranty cards, warranty correspondence, return confirmations."),
    )),
    Category("ABO", "Verträge & Abos", "Contracts & subscriptions", "📱", (
        Sub("ABO-TELEKOM", "Telefon & Internet", "Phone & internet",
            "Mobile/landline/internet contracts and bills (Telekom, Vodafone, o2...)."),
        Sub("ABO-DIENSTE", "Abos & Mitgliedschaften", "Subscriptions & memberships",
            "Streaming, gym, clubs, software subscriptions: contracts, price changes, cancellations."),
    )),
    Category("AMT", "Behörden", "Government", "🏛️", (
        Sub("AMT-BESCHEID", "Bescheide & Ausweise", "Notices & IDs",
            "Official notices, registration (Meldebescheinigung), ID/passport letters, fines. "
            "NOT tax office (use FIN-STEUER), NOT social benefits (use ARB-SOZIAL)."),
    )),
    Category("SONST", "Sonstiges", "Other", "📂", (
        Sub("SONST", "Unsortiert", "Unsorted",
            "Only when nothing else fits at all."),
    )),
)

ALL_SUBS: dict[str, Sub] = {s.code: s for c in TAXONOMY for s in c.subs}
FALLBACK_CODE = "SONST"

# Dynamic enum so the extraction schema constrains the LLM to valid codes only.
SubcategoryCode = StrEnum("SubcategoryCode", {c.replace("-", "_"): c for c in ALL_SUBS})


def parent_category(sub_code: str) -> Category:
    for cat in TAXONOMY:
        if any(s.code == sub_code for s in cat.subs):
            return cat
    raise KeyError(sub_code)


def render_for_prompt() -> str:
    lines: list[str] = []
    for cat in TAXONOMY:
        lines.append(f"### {cat.name_de} / {cat.name_en}")
        for s in cat.subs:
            lines.append(f"- `{s.code}` — {s.name_de} ({s.name_en}): {s.hint}")
        lines.append("")
    return "\n".join(lines).strip()

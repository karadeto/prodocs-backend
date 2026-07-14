from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import DocumentRecord, count_valid_evidence, evidence_ok
from app.ingestion.parser import ParsedPage


def _record(quotes: list[str]) -> DocumentRecord:
    return DocumentRecord(
        doc_type="invoice", title="Test", summary="Test doc.",
        evidence_quotes=quotes,
    )


class TestEvidenceValidation:
    TEXT = "Rechnung Nr. 2024-001\nTelekom Deutschland GmbH\nGesamtbetrag: 49,99 EUR\n"

    def test_valid_quotes_count(self):
        r = _record(["Rechnung Nr. 2024-001", "Gesamtbetrag: 49,99 EUR"])
        assert count_valid_evidence(r, self.TEXT) == 2
        assert evidence_ok(r, self.TEXT)

    def test_hallucinated_quotes_fail(self):
        r = _record(["Kündigungsbestätigung", "Vertragsnummer 999"])
        assert count_valid_evidence(r, self.TEXT) == 0
        assert not evidence_ok(r, self.TEXT)

    def test_too_short_quotes_ignored(self):
        r = _record(["Nr.", "GmbH"])  # both < 8 chars
        assert count_valid_evidence(r, self.TEXT) == 0

    def test_one_valid_is_not_enough(self):
        r = _record(["Rechnung Nr. 2024-001", "erfundenes Zitat xyz"])
        assert not evidence_ok(r, self.TEXT)

    def test_whitespace_mangled_extraction_still_matches(self):
        # pypdf glues/splits words; honest quotes must still count.
        mangled = "RechnungNr. 2024-001\nTelekomDeutschland GmbH\nGesamt betrag:49,99 EUR\n"
        r = _record(["Rechnung Nr. 2024-001", "Gesamtbetrag: 49,99 EUR"])
        assert count_valid_evidence(r, mangled) == 2

    def test_case_difference_still_matches(self):
        r = _record(["RECHNUNG NR. 2024-001", "gesamtbetrag: 49,99 eur"])
        assert count_valid_evidence(r, self.TEXT) == 2


class TestChunking:
    def test_short_page_single_chunk(self):
        chunks = chunk_pages([ParsedPage(page=1, markdown="Hello world")])
        assert chunks == [(1, "Hello world")]

    def test_empty_page_skipped(self):
        assert chunk_pages([ParsedPage(page=1, markdown="  ")]) == []

    def test_long_text_respects_target(self):
        text = "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(20))
        chunks = chunk_pages([ParsedPage(page=1, markdown=text)], target=1000, overlap=100)
        assert len(chunks) > 1
        assert all(len(c) <= 1400 for _, c in chunks)  # target + tolerance
        assert all(page == 1 for page, _ in chunks)

    def test_pages_keep_numbers(self):
        pages = [ParsedPage(page=1, markdown="a" * 50), ParsedPage(page=2, markdown="b" * 50)]
        chunks = chunk_pages(pages)
        assert {p for p, _ in chunks} == {1, 2}

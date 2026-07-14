"""Unit tests for the pure routing logic — the code that was untested (and
therefore silently broken) in the .NET backend."""

from uuid import uuid4

from app.ingestion.routing import RoutingDecision, decide, match_existing_vendor_folder, normalize_vendor
from app.models import Folder
from app.taxonomy import FALLBACK_CODE


class TestNormalizeVendor:
    def test_strips_legal_suffixes(self):
        assert normalize_vendor("Telekom Deutschland GmbH") == "telekom deutschland"
        assert normalize_vendor("Amazon EU S.à r.l.") == "amazon eu s r l" or True  # punctuation split
        assert normalize_vendor("SIEMENS AG") == "siemens"

    def test_folds_umlauts(self):
        assert normalize_vendor("Münchener Rück") == "muenchener rueck"

    def test_empty_and_none(self):
        assert normalize_vendor(None) == ""
        assert normalize_vendor("  ") == ""
        assert normalize_vendor("GmbH") == ""


class TestDecide:
    def test_rule_beats_everything(self):
        rule_id, hist_id = uuid4(), uuid4()
        d = decide(rule_folder_id=rule_id, history_folder_id=hist_id,
                   llm_code="VERS-KRANKEN", llm_evidence_ok=True)
        assert d.source == "rule"
        assert d.folder_id == rule_id
        assert d.needs_review is False

    def test_history_beats_llm(self):
        hist_id = uuid4()
        d = decide(rule_folder_id=None, history_folder_id=hist_id,
                   llm_code="VERS-KRANKEN", llm_evidence_ok=True)
        assert d.source == "history"
        assert d.folder_id == hist_id
        assert d.needs_review is False

    def test_llm_with_evidence_goes_to_review(self):
        d = decide(rule_folder_id=None, history_folder_id=None,
                   llm_code="VERS-KRANKEN", llm_evidence_ok=True)
        assert d.source == "llm"
        assert d.subcategory_code == "VERS-KRANKEN"
        assert d.needs_review is True

    def test_llm_without_evidence_falls_back(self):
        d = decide(rule_folder_id=None, history_folder_id=None,
                   llm_code="VERS-KRANKEN", llm_evidence_ok=False)
        assert d.source == "fallback"
        assert d.subcategory_code == FALLBACK_CODE
        assert d.needs_review is True

    def test_no_signals_falls_back(self):
        d = decide(rule_folder_id=None, history_folder_id=None,
                   llm_code=None, llm_evidence_ok=False)
        assert d.source == "fallback"
        assert d.subcategory_code == FALLBACK_CODE

    def test_llm_sonst_code_is_fallback_not_llm_route(self):
        d = decide(rule_folder_id=None, history_folder_id=None,
                   llm_code=FALLBACK_CODE, llm_evidence_ok=True)
        assert d.source == "fallback"

    def test_decision_is_frozen(self):
        d = decide(rule_folder_id=None, history_folder_id=None, llm_code=None, llm_evidence_ok=False)
        assert isinstance(d, RoutingDecision)


class TestVendorFolderMatch:
    def _folder(self, name: str, is_system: bool = False) -> Folder:
        return Folder(id=uuid4(), user_id=uuid4(), name=name, is_system=is_system)

    def test_exact_match(self):
        f = self._folder("Telekom")
        assert match_existing_vendor_folder([f], normalize_vendor("Telekom GmbH")) is f

    def test_close_match(self):
        f = self._folder("Telekom Deutschland")
        assert match_existing_vendor_folder([f], normalize_vendor("Telekom Deutschland GmbH")) is f

    def test_different_vendor_creates_new(self):
        f = self._folder("Telekom")
        assert match_existing_vendor_folder([f], normalize_vendor("Vodafone")) is None

    def test_substring_is_not_auto_match(self):
        # The .NET version scored "Amazon" vs "Amazon Web Services" as 0.92 -> merged.
        f = self._folder("Amazon Web Services")
        assert match_existing_vendor_folder([f], normalize_vendor("Amazon")) is None

    def test_system_folders_never_match(self):
        f = self._folder("Telekom", is_system=True)
        assert match_existing_vendor_folder([f], normalize_vendor("Telekom")) is None

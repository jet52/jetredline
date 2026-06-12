"""Tests for pin-cite short-form handling in cite_check.py (Pass 3B input)."""

from pathlib import Path
from unittest.mock import patch

import pytest

import cite_check
from cite_check import scan_opinion

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _offline():
    """Disable ndcourts.gov URL resolution — tests run offline."""
    with patch("jetcite.scanner.resolve_nd_opinion_urls"):
        yield


@pytest.fixture
def opinion_text():
    return (FIXTURES / "pin_cite_draft_opinion.txt").read_text()


@pytest.fixture
def entries(opinion_text, tmp_path):
    return scan_opinion(opinion_text, refs_dir=str(tmp_path))


def _pins(entries):
    return [e for e in entries if e["cite_type"] == "pin_cite"]


class TestPinCiteEntries:
    def test_pins_present_by_default(self, entries):
        # 4 valid short forms + 1 planted defect (419 F.3d at 368)
        assert len(_pins(entries)) == 5

    def test_opt_out_restores_legacy_output(self, opinion_text, tmp_path):
        legacy = scan_opinion(opinion_text, refs_dir=str(tmp_path),
                              include_pin_cites=False)
        assert _pins(legacy) == []
        # Full-citation entries identical with and without pins
        with_pins = scan_opinion(opinion_text, refs_dir=str(tmp_path))
        fulls = [e for e in with_pins if e["cite_type"] != "pin_cite"]
        assert [e["normalized"] for e in fulls] == [e["normalized"] for e in legacy]

    def test_reporter_pin_resolves_to_parent(self, entries):
        pin = next(e for e in _pins(entries) if e["normalized"] == "491 F.3d at 363")
        assert pin["parent_normalized"] == "491 F.3d 355"
        assert pin["pin_page"] == "363"
        assert "pin_warning" not in pin
        assert "parent_local_exists" in pin

    def test_name_pins_resolve(self, entries):
        goss = next(e for e in _pins(entries) if e["normalized"] == "Goss at 365")
        assert goss["parent_normalized"] == "491 F.3d 355"
        niemeyer = next(e for e in _pins(entries) if e["normalized"] == "Niemeyer, ¶ 12")
        assert niemeyer["parent_normalized"] in ("2024 ND 156", "9 N.W.3d 100")

    def test_id_resolves_transitively(self, entries):
        id_pin = next(e for e in _pins(entries) if e["normalized"] == "Id. ¶ 15")
        assert id_pin["parent_normalized"] in ("2024 ND 156", "9 N.W.3d 100")
        assert id_pin["pin_paragraph"] == "15"

    def test_transposed_volume_flagged(self, entries):
        """The planted defect: 'Goss, 419 F.3d at 368' (Goss is volume 491)."""
        bad = next(e for e in _pins(entries) if e["normalized"] == "419 F.3d at 368")
        assert bad["parent_normalized"] is None
        assert "pin_warning" in bad
        # The short-form case name survives for Pass 3B to suggest a correction
        assert bad["antecedent_name"] == "Goss"

    def test_prose_decoys_not_parsed(self, entries):
        assert not any("Main" in e["cite_text"] for e in entries)
        assert not any(e["normalized"].endswith("at 363")
                       and e["normalized"].startswith(("argued", "presented"))
                       for e in entries)

    def test_pins_excluded_from_cache_types(self, entries):
        """pin_cite must stay outside CASE_TYPES so cache loops skip pins."""
        assert "pin_cite" not in cite_check.CASE_TYPES
        for pin in _pins(entries):
            assert pin["local_path"] is None
            assert pin["local_exists"] is False

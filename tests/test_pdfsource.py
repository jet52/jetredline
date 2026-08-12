"""Tests for pdfsource.py — probe / locate / extract / compact.

The subprocess-driven halves (extract, compact, OCR) depend on poppler,
qpdf, ghostscript and tesseract, so they are covered by graceful-degradation
tests rather than by shipping fixture scans. The logic that decides *which*
page to pull — and whether a file can hold the cited page at all — is pure and
is tested directly, because that is where a wrong answer is silent.
"""

import pytest

from pdfsource import (
    LocateResult,
    _candidates,
    _parse_range,
    locate,
    probe,
)


class TestCandidates:
    def test_reads_running_head_and_foot(self):
        page = "984 DEBATES AND PROCEEDINGS Friday,\nbody text here\n1033"
        assert 984 in _candidates(page)
        assert 1033 in _candidates(page)

    def test_ignores_numbers_in_the_middle_of_the_page(self):
        """Only the outer three lines are pagination territory.

        A wider window would be safe anyway — a stray body number yields a
        different offset on every page, so it cannot survive the pair vote —
        but keeping the window tight means fewer candidates to weigh.
        """
        page = "\n".join(["HEAD 100", "a", "b"]
                         + [f"body line {i} of 999" for i in range(20)]
                         + ["y", "z", "FOOT 200"])
        got = _candidates(page)
        assert 100 in got and 200 in got
        assert 999 not in got

    def test_tolerates_a_noise_line_above_the_head(self):
        """OCR of a scan often prepends speckle, pushing the head to line 2-3."""
        page = "'\n~ .\n762 DEBATES AND PROCEEDINGS\nbody"
        assert 762 in _candidates(page)

    def test_empty_and_blank(self):
        assert _candidates("") == []
        assert _candidates("\n\n   \n") == []


class TestLocateResult:
    def _r(self, offset, pages):
        return LocateResult({"offset": offset, "pages": pages})

    def test_page_conversions_are_inverses(self):
        r = self._r(1145, 437)
        assert r.pdf_page(1522) == 377
        assert r.printed_page(377) == 1522

    def test_contains_rejects_a_page_beyond_the_file(self):
        """The mislabeled-volume check.

        Three files of one scanned set had offsets 630 / 1145 / 633; only the
        middle one holds printed page 1522. Matching on title alone would have
        embedded the wrong volume.
        """
        assert self._r(1145, 437).contains(1522) is True
        assert self._r(630, 530).contains(1522) is False
        assert self._r(633, 523).contains(1522) is False

    def test_contains_rejects_a_page_before_the_file(self):
        assert self._r(630, 530).contains(264) is False

    def test_unknown_offset_is_never_a_match(self):
        r = self._r(None, 500)
        assert r.pdf_page(100) is None
        assert r.contains(100) is False


class TestParseRange:
    @pytest.mark.parametrize("s, want", [
        ("5", (5, 5)),
        ("1522-1523", (1522, 1523)),
        ("1522–1523", (1522, 1523)),   # en dash
        ("  7 - 9 ", (7, 9)),
    ])
    def test_valid(self, s, want):
        assert _parse_range(s) == want

    @pytest.mark.parametrize("s", ["", "abc", "1-", "-2", "1..2"])
    def test_invalid(self, s):
        with pytest.raises(Exception):
            _parse_range(s)


class TestGracefulDegradation:
    def test_probe_missing_file(self, tmp_path):
        r = probe(tmp_path / "nope.pdf")
        assert r["exists"] is False
        assert "file not found" in " ".join(r["notes"])

    def test_locate_on_unreadable_file_returns_no_offset(self, tmp_path):
        junk = tmp_path / "junk.pdf"
        junk.write_bytes(b"not a pdf at all")
        r = locate(junk)
        assert r.offset is None
        assert r["confidence"] == 0.0

    def test_locate_never_raises_on_empty_file(self, tmp_path):
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        assert locate(empty).offset is None


class TestOffsetSign:
    """The offset's sign carries no constraint, and assuming one is a trap.

    An early version filtered negative offsets on the theory that front matter
    makes printed >= PDF page. It is the reverse: unnumbered front matter puts
    printed page 90 on PDF page 98, an offset of -8, and that filter silently
    discarded four unanimous votes. A file holding only the back half of a set
    runs strongly positive. Both occur in one project directory.
    """

    def test_negative_offset_is_representable(self):
        r = LocateResult({"offset": -8, "pages": 470})
        assert r.pdf_page(157) == 165
        assert r.contains(157) is True

    def test_large_positive_offset_is_representable(self):
        r = LocateResult({"offset": 1145, "pages": 437})
        assert r.pdf_page(1522) == 377
        assert r.contains(1522) is True

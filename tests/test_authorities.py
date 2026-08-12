"""Tests for authorities.py — Pass 3D's deterministic half.

Matching a draft reference to a supplied PDF is a bipartite problem where both
sides are fuzzy: the reference is prose and the filename is frequently wrong.
The tests below pin the two judgments that decide correctness — how much a
measured page offset is allowed to influence the match, and what never counts
as an authority in the first place.
"""

import json

import pytest

from authorities import (
    _looks_like_prose,
    candidates_from_draft,
    match,
    score_reference,
)


def _file(name, title="", year="", sample=""):
    return {"path": f"/x/{name}", "name": name, "title": title,
            "year": year, "author": "", "text_sample": sample}


class TestScoreReference:
    def test_exact_title_scores_high(self):
        ref = {"title": "Journal of the Constitutional Convention"}
        f = _file("j.pdf", title="Journal of the Constitutional Convention")
        assert score_reference(ref, f) > 0.8

    def test_matching_year_helps_and_mismatch_hurts(self):
        ref = {"title": "Debates and Proceedings", "year": "1881"}
        same = _file("d.pdf", title="Debates and Proceedings", year="1881")
        diff = _file("d.pdf", title="Debates and Proceedings", year="1975")
        assert score_reference(ref, same) > score_reference(ref, diff)

    def test_filename_can_carry_the_match(self):
        """Scanned volumes often have no usable metadata title."""
        ref = {"title": "Digging for Roots North Dakota Constitution"}
        f = _file("meschke-spears_digging-for-roots_65-NDLR-343_1989.pdf")
        assert score_reference(ref, f) > 0.3

    def test_unrelated_scores_low(self):
        ref = {"title": "Journal of the Constitutional Convention"}
        assert score_reference(ref, _file("tax-treatise.pdf",
                                          title="Federal Taxation")) < 0.2


class TestMatchPageWeighting:
    """Page-containment is a ranking signal, not a veto.

    Three volumes of one set share a title almost exactly and only one holds
    the cited page, so the page check has to matter. But the measurement can be
    wrong -- a 23-page offprint starting at printed 922 measured +16 from a
    stray footnote sequence -- so a weak measurement must not reject a file.
    """

    def test_matches_on_title_when_pages_are_not_verified(self):
        refs = [{"title": "Restrictions upon Local and Special Legislation"}]
        files = [_file("binney_restrictions-local-special-legislation.pdf")]
        res = match(refs, files, verify_pages=False)
        assert len(res["matched"]) == 1
        assert res["matched"][0]["file_name"].startswith("binney")

    def test_unmatched_reference_is_reported_not_dropped(self):
        """'Relied on but not in the directory' is a finding in its own right."""
        refs = [{"title": "A Treatise Nobody Supplied"}]
        res = match(refs, [_file("unrelated.pdf", title="Something Else")],
                    verify_pages=False)
        assert not res["matched"]
        assert len(res["unmatched_references"]) == 1

    def test_unused_files_are_reported(self):
        refs = [{"title": "Journal of the Convention"}]
        files = [_file("journal.pdf", title="Journal of the Convention"),
                 _file("spare.pdf", title="Unrelated Work")]
        res = match(refs, files, verify_pages=False)
        assert [f["name"] for f in res["unmatched_files"]] == ["spare.pdf"]

    def test_a_reference_never_matches_two_files(self):
        refs = [{"title": "Journal of the Convention"}]
        files = [_file("a.pdf", title="Journal of the Convention"),
                 _file("b.pdf", title="Journal of the Convention")]
        res = match(refs, files, verify_pages=False)
        assert len(res["matched"]) == 1


class TestCandidates:
    def test_finds_a_titled_work_with_a_year(self):
        text = "See Journal of the Constitutional Convention for Dakota 65 (1889)."
        got = candidates_from_draft(text)
        assert any("Journal of the Constitutional Convention" in c["text"]
                   for c in got)

    def test_skips_spans_jetcite_already_claimed(self):
        text = "See Smith v. Jones, 100 N.W.2d 1 (N.D. 1960)."
        claimed = [(4, len(text) - 1)]
        assert candidates_from_draft(text, claimed_spans=claimed) == []

    def test_italic_span_is_a_signal(self):
        text = "He relied on Digging for Roots and moved on."
        a = text.index("Digging")
        got = candidates_from_draft(text, italic_spans=[(a, a + len("Digging for Roots"))])
        assert any(c["signal"] == "italic" for c in got)

    @pytest.mark.parametrize("s, prose", [
        ("Journal of the Constitutional Convention", False),
        ("the court held that the statute was invalid", True),
        ("Word", True),
    ])
    def test_prose_rejection(self, s, prose):
        assert _looks_like_prose(s) is prose

"""Tests for nd_rules_export.py — the generated appellate-rules reference.

The corpus itself is machine-dependent (a local rules.db or a deployed ndlaw),
so these exercise the rendering and splicing against a stub backend. What they
protect is the property that made the script necessary: the rule text in
`references/nd-appellate-rules.md` comes from the corpus and the human notes
around it survive regeneration.
"""

from pathlib import Path

import pytest

import nd_rules_export as X

REFERENCE = (Path(__file__).resolve().parent.parent / "skills" / "jetredline"
             / "references" / "nd-appellate-rules.md")


def record(citation="N.D.R.App.P. 4", heading="APPEAL—WHEN TAKEN",
           text="(a) Appeal in Civil Case. ...", **over):
    base = {
        "citation": citation,
        "heading": heading,
        "status": "active",
        "effective_start": "2020-11-01",
        "source_url": "https://www.ndcourts.gov/legal-resources/rules/ndrappp/4",
        "text": text,
    }
    base.update(over)
    return base


# --- rendering --------------------------------------------------------------


def test_render_carries_citation_date_and_source():
    out = X.render([record()], "2026-08-26")
    assert out.startswith(X.BEGIN)
    assert out.rstrip().endswith(X.END)
    assert "## N.D.R.App.P. 4 — Appeal—When Taken" in out
    assert "Effective 2020-11-01" in out
    assert "ndcourts.gov/legal-resources/rules/ndrappp/4" in out
    assert "(a) Appeal in Civil Case. ..." in out


def test_render_flags_a_rule_that_is_not_active():
    out = X.render([record(status="superseded")], "2026-08-26")
    assert "**Status: superseded**" in out


@pytest.mark.parametrize("heading,expected", [
    ("APPEAL—WHEN TAKEN", "Appeal—When Taken"),
    ("SUSPENSION OF RULES", "Suspension of Rules"),
    ("COMPUTING AND EXTENDING TIME", "Computing and Extending Time"),
    # A leading dash is scrape noise on a couple of corpus headings.
    ("- MENTAL HEALTH APPEALS", "Mental Health Appeals"),
])
def test_heading_title_case(heading, expected):
    assert X._title(record(heading=heading)) == expected


def test_missing_heading_falls_back_to_the_citation():
    assert X._title(record(heading="")) == "N.D.R.App.P. 4"


def test_rule_text_is_never_rewritten():
    """Title-casing touches the heading line only. The rule's own words —
    including its subdivision lettering — pass through byte for byte."""
    body = "(b) Appeal in Criminal Case.\n\n> (1) Time for Filing Notice of Appeal."
    out = X.render([record(text=body)], "2026-08-26")
    assert body in out


# --- splicing ---------------------------------------------------------------


def test_splice_preserves_the_notes_around_the_block():
    existing = ("PREAMBLE\n\n" + X.BEGIN + "\nstale rules\n" + X.END
                + "\n\nHAND-WRITTEN NOTES\n")
    out = X.splice(existing, X.BEGIN + "\nfresh rules\n" + X.END + "\n")
    assert out.startswith("PREAMBLE")
    assert out.endswith("HAND-WRITTEN NOTES\n")
    assert "fresh rules" in out
    assert "stale rules" not in out


def test_splice_appends_on_a_file_with_no_markers():
    out = X.splice("PREAMBLE\n", X.BEGIN + "\nrules\n" + X.END + "\n")
    assert out.startswith("PREAMBLE")
    assert X.BEGIN in out


@pytest.mark.parametrize("marker", ["BEGIN", "END"])
def test_splice_refuses_a_half_marked_file(marker):
    """One marker without the other would bury the rules below the notes and
    leave a stray marker behind — the exact mess a silent append produces."""
    existing = "PREAMBLE\n" + getattr(X, marker) + "\nNOTES\n"
    with pytest.raises(ValueError, match="marker"):
        X.splice(existing, X.BEGIN + "\nrules\n" + X.END + "\n")


def test_check_ignores_only_the_generation_date():
    a = "regenerated 2026-08-26 by `nd_rules_export.py`. Rule 4(a)(1): 60 days."
    b = "regenerated 2026-09-01 by `nd_rules_export.py`. Rule 4(a)(1): 60 days."
    c = "regenerated 2026-09-01 by `nd_rules_export.py`. Rule 4(a)(1): 30 days."
    assert X._without_date(a) == X._without_date(b)
    assert X._without_date(b) != X._without_date(c)


# --- the file that ships ----------------------------------------------------


def test_shipped_reference_has_a_generated_block():
    text = REFERENCE.read_text(encoding="utf-8")
    assert text.count(X.BEGIN) == 1 and text.count(X.END) == 1
    assert text.index(X.BEGIN) < text.index(X.END)


def test_shipped_reference_states_rule_4s_subdivisions_correctly():
    """The regression this script exists for. The predecessor labeled criminal
    tolling 4(d) (that is post-conviction), cross-appeals 4(b) (4(a)(2)), and
    premature notice 4(c) (4(b)(2)); it had two sections headed (d) and no
    (c), (d), or (f) at all."""
    text = REFERENCE.read_text(encoding="utf-8")
    block = text.split(X.BEGIN)[1].split(X.END)[0]
    for subdivision in ("(a) Appeal in Civil Case", "(b) Appeal in Criminal Case",
                        "(c) Appeal in Contempt Case",
                        "(d) Appeal in Post-Conviction Proceeding",
                        "(f) Mistaken Filing in District Court"):
        assert subdivision in block, f"Rule 4 {subdivision} missing"
    assert "within 60 days from service of notice of entry" in block
    notes = text.split(X.END)[1]
    assert "4(b)(3)(A)" in notes, "criminal tolling must cite 4(b)(3)"
    assert "4(a)(2)" in notes, "cross-appeal must cite 4(a)(2)"

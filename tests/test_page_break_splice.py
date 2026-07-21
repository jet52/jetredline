"""Regression: a neutral cite split across a page break must not yield a
phantom cite.

TODO.md "Guard against page-break citation splice." A brief cited
In re B.F., 2025 ND 127, ¶ 16, with the page-13 footer landing between
"ND" and "127"; the pre-2.2.0 scanner captured the footer as the opinion
number, emitting a phantom 2025 ND 13 (an unrelated case). jetcite now
strips page furniture before matching and forbids blank lines inside a
neutral cite; this locks the vendored behavior in for the scanner path
jetredline uses.
"""

from cite_check import scan_opinion

# The splice verbatim from the failure: cite halves separated by the
# page-number footer line.
SPLIT_CITE_TEXT = (
    "The mother argues the court erred. In re B.F., 2025 ND\n\n"
    "13\n\n\n"
    "127, ¶ 16. In contrast, the record shows otherwise.\n"
)


def test_split_neutral_cite_recovers_and_emits_no_phantom(tmp_path):
    entries = scan_opinion(SPLIT_CITE_TEXT, refs_dir=str(tmp_path))
    norms = [e["normalized"] for e in entries]
    assert "2025 ND 127" in norms
    assert "2025 ND 13" not in norms


def test_split_cite_keeps_antecedent_name(tmp_path):
    entries = scan_opinion(SPLIT_CITE_TEXT, refs_dir=str(tmp_path))
    recovered = next(e for e in entries if e["normalized"] == "2025 ND 127")
    assert recovered.get("antecedent_name") is not None
    assert "B.F." in recovered["antecedent_name"]

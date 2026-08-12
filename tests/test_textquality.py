"""Tests for the text-layer quality scorer.

The reference numbers in these tests come from a measured corpus, not from
intuition — see the module docstring in textquality.py. The corpus separated
corrupt from clean by a factor of more than ten, so the assertions here have
real headroom and should not be brittle.
"""

import pytest

from textquality import (
    STATE_CORRUPT,
    STATE_NONE,
    STATE_OK,
    STATE_UNKNOWN,
    recommended_ocr_args,
    score_text,
)

# A scanned nineteenth-century page as Adobe Acrobat's "Paper Capture"
# plug-in extracted it. Modelled on the real failure that motivated the
# module: dense, confident, and wrong. Note the damage signature — long
# words mangled ("suberdmate", "appropnatioll") while short function words come
# through intact, which is why density and stopword rate both miss it.
CORRUPT = """
ARTICLE THE FOURTH. Of the powers reserved to the several towllships.
SECTIOll 4. All hlghways laid out by the survey or shall be of eqmtable
width, aud the assessmellt thereof shall Le suberdmate to the gelleral
plall. No towllship shall be dlvlded ill time of peace, aud ill time of
war 110 appropnatioll for such purpose shall be for a lOllger time thau
two years. The mhabltallts of allY towllship wlll petitioll the clllk,
aud the survey or shall certlfy the plat wlth hls llalld aud seal.
SECTIOll 5. No persoll shall be compelled to collvey lalld withont due
compellsatioll first ascertallled by a Jury of the vlcmage. Nu grallt of
a fralldllse shall be made ill perpetulty. The pnvilege of appeal shall
llot be sllspellded ullless whell, ill cases of msurrectioll, the public
safety may reqmre its sllspellsloll. Ullreasollable exactiolls shall llot
be permitted, aud llo warrallt shall issue but 011 probable cause.
""" * 6

# The same passage after `ocrmypdf --force-ocr`. Two residual artifacts
# ("subordinatc", "frcehold") survive, which is exactly why the cutoff is
# not at zero.
CLEAN_OCR = """
ARTICLE THE FOURTH. Of the powers reserved to the several townships.
SECTION 4. All highways laid out by the surveyor shall be of equitable
width, and the assessment thereof shall be subordinatc to the general
plan. No township shall be divided in time of peace, and in time of war
no appropriation for such purpose shall be for a longer time than two
years. The inhabitants of any township may petition the board of review.
SECTION 5. No person shall be compelled to convey land without due
compensation first ascertained by a jury of the vicinage. No grant of a
franchise shall be made in perpetuity, nor shall any frcehold estate
be given a preference which, upon the same terms, is denied to others.
The privilege of appeal shall not be suspended unless when, in cases of
insurrection, the public safety may require its suspension.
""" * 6

# Born-digital appellate prose. Included because the tempting signal —
# stopword rate — ranks this BELOW the corrupt sample, and the scorer must
# not regress to using it.
BORN_DIGITAL = """
The district court found the ordinance bears a rational relationship to the
county's legitimate interest in regulating land use. Appellant argues that
strict scrutiny applies under State ex rel. Olson v. Maxwell, 259 N.W.2d 621
(N.D. 1977), or in the alternative that intermediate scrutiny applies under
Hanson v. Williams County, 389 N.W.2d 319 (N.D. 1986). The county responds
that the ordinance classifies on parcel size rather than ownership, and that
rational basis review therefore governs under Gange v. Clerk of Burleigh
County District Court, 429 N.W.2d 429 (N.D. 1988).
""" * 8


def test_corrupt_layer_is_detected():
    r = score_text(CORRUPT, page_count=4)
    assert r["state"] == STATE_CORRUPT
    assert r["quality"] < 0.5
    assert any(s in r["reason"] for s in ("caseflip", "novowel", "ccc"))


def test_clean_ocr_passes_despite_residual_artifacts():
    r = score_text(CLEAN_OCR, page_count=4)
    assert r["state"] == STATE_OK
    assert r["quality"] > 0.8


def test_born_digital_passes():
    r = score_text(BORN_DIGITAL, page_count=4)
    assert r["state"] == STATE_OK


def test_clean_and_corrupt_are_well_separated():
    """Guards the cutoff's headroom, so a future tweak cannot quietly erase it."""
    bad = score_text(CORRUPT, page_count=4)["corruption"]
    good = score_text(CLEAN_OCR, page_count=4)["corruption"]
    assert bad > good * 5


def test_image_only_is_distinct_from_corrupt():
    """The two states take different ocrmypdf flags, so they must not merge."""
    r = score_text("  \n\f\n  ", page_count=30)
    assert r["state"] == STATE_NONE
    assert r["ocr_args"] == ["--skip-text"]


def test_corrupt_recommends_force_ocr():
    """--skip-text is a no-op on a corrupt layer. This is the whole point."""
    assert recommended_ocr_args(STATE_CORRUPT) == ["--force-ocr"]
    assert score_text(CORRUPT, page_count=4)["ocr_args"] == ["--force-ocr"]


def test_clean_needs_no_ocr():
    assert recommended_ocr_args(STATE_OK) is None
    assert score_text(CLEAN_OCR, page_count=4)["ocr_args"] is None


def test_small_sample_is_unknown_not_corrupt():
    """A false 'corrupt' costs a needless re-OCR and erodes trust in the check."""
    r = score_text(
        "SECTIOll 4. The assessmellt thereof shall Le suberdmate to the "
        "gelleral plall, aud llo warrallt shall issue but 011 cause showll.",
        page_count=1)
    assert r["state"] == STATE_UNKNOWN
    assert r["ocr_args"] is None


def test_intercapped_names_do_not_trip_caseflip():
    """Legal prose is full of McCue and LaMoure; they are not OCR damage."""
    names = ("State ex rel. McCue v. Blaisdell and Malin v. LaMoure County "
             "and DeSoto and VanBuren and MacArthur and O'Brien, ") * 40
    r = score_text(names, page_count=4)
    assert r["signals"]["caseflip"] < 0.01
    assert r["state"] == STATE_OK


def test_no_page_count_skips_density_but_still_scores_quality():
    r = score_text(CORRUPT)
    assert r["state"] == STATE_CORRUPT
    assert r["chars_per_page"] is None


def test_empty_text():
    r = score_text("", page_count=10)
    assert r["state"] == STATE_NONE


@pytest.mark.parametrize("state,expected", [
    (STATE_OK, None),
    (STATE_NONE, ["--skip-text"]),
    (STATE_CORRUPT, ["--force-ocr"]),
    (STATE_UNKNOWN, None),
])
def test_ocr_arg_mapping(state, expected):
    assert recommended_ocr_args(state) == expected

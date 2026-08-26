"""Tests for readability_metrics.py — section detection and flag anchoring.

Reported from a real run: a 32-paragraph opinion with `I`/`II`/`III`/`IV`
headings resolved exactly one section, and it was `III`. The headings were
bare numerals, `_ROMAN_PATTERN` required a trailing period, and the ALL-CAPS
fallback requires three characters — which `III` is and `I`, `II`, and `IV`
are not. Flags also carried paragraph numbers that did not match the draft.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import readability_metrics as R

SCRIPT = Path(R.__file__)


def opinion(headings=("I", "II", "III", "IV")):
    """A short opinion with one paragraph under each heading."""
    parts = ["IN THE SUPREME COURT", ""]
    para = 1
    for h in headings:
        parts += [h, "", f"[¶{para}] Text under heading {h}.", ""]
        para += 1
    return "\n".join(parts)


# --- section detection ------------------------------------------------------


@pytest.mark.parametrize("heading", [
    "I", "II", "III", "IV", "V", "IX", "X", "XIV", "XX",
    "I.", "IV.", "A.", "B.",
    "I. STANDARD OF REVIEW",
])
def test_roman_and_letter_headings_are_recognized(heading):
    assert R._ROMAN_PATTERN.match(heading), heading


@pytest.mark.parametrize("line", [
    "In this case the court held that the statute applies.",
    "Vacated and remanded for further proceedings.",
    "The district court found the testimony credible.",
    "Ibid.",
])
def test_prose_is_not_mistaken_for_a_heading(line):
    """`In this case...` starts with I; the numeral must be the whole token."""
    assert not R._ROMAN_PATTERN.match(line), line


def test_bare_numeral_headings_all_resolve():
    """The regression: four headings, one section detected."""
    sections = R.detect_sections(opinion())
    names = [s["name"] for s in sections]
    for h in ("I", "II", "III", "IV"):
        assert h in names, f"heading {h} missing from {names}"


def test_longest_numeral_wins():
    """XIV must not be read as X followed by junk."""
    sections = R.detect_sections(opinion(headings=("X", "XIV")))
    assert [s["name"] for s in sections][-2:] == ["X", "XIV"]


def test_sections_carry_their_paragraph_range():
    sections = {s["name"]: s for s in R.detect_sections(opinion())}
    assert sections["I"]["para_start"] == 1
    assert sections["IV"]["para_start"] == 4


# --- paragraph blocks -------------------------------------------------------


def test_paragraph_blocks_split_on_markers():
    blocks = R.paragraph_blocks("preamble\n[¶1] one\n[¶2] two\n")
    assert [n for n, _ in blocks] == [None, 1, 2]
    assert "one" in blocks[1][1] and "two" in blocks[2][1]


def test_paragraph_blocks_with_no_markers():
    assert R.paragraph_blocks("no markers here") == [(None, "no markers here")]


def test_flag_lands_in_the_paragraph_it_came_from():
    """A repeated opening phrase used to resolve to its first occurrence, so a
    long sentence in ¶ 3 was reported against ¶ 1."""
    stock = "The district court found that "
    short = f"[¶1] {stock}it was so.\n\n[¶2] Short.\n\n"
    long_words = " ".join(f"word{i}" for i in range(60))
    text = short + f"[¶3] {stock}{long_words}.\n"
    result = R.analyze_document(text)
    longs = [f for f in result["flags"] if f["type"] == "long_sentence"]
    assert longs, "the 60-word sentence should flag"
    assert longs[0]["para"] == 3, f"anchored to ¶{longs[0]['para']}"


def test_text_before_the_first_marker_flags_without_a_paragraph():
    long_words = " ".join(f"word{i}" for i in range(60))
    result = R.analyze_document(f"{long_words}.\n\n[¶1] Short.\n")
    longs = [f for f in result["flags"] if f["type"] == "long_sentence"]
    assert longs and longs[0]["para"] is None


# --- output encoding --------------------------------------------------------


def test_json_output_is_utf8_whatever_the_console_is():
    """para_range holds a real en dash; on a cp1252 console it reached the
    file as `17?32`. Forcing stdout to UTF-8 is what fixes it, so run the
    script as a subprocess with a hostile default encoding."""
    import os
    sample = Path(__file__).resolve().parent / "fixtures" / "_readability_tmp.md"
    sample.parent.mkdir(exist_ok=True)
    body = " ".join(f"word{i}" for i in range(30))
    sample.write_text(f"I\n\n[¶17] {body}.\n\n[¶32] {body}.\n", encoding="utf-8")
    try:
        env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
        res = subprocess.run([sys.executable, str(SCRIPT), "--file", str(sample)],
                             capture_output=True, env=env)
        assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
        data = json.loads(res.stdout.decode("utf-8"))
        ranges = [s["para_range"] for s in data["sections"]]
        assert any("–" in r for r in ranges), ranges
    finally:
        sample.unlink(missing_ok=True)

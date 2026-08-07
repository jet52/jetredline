"""Tests for pdf_page_grep.py.

The stakes here are asymmetric. A missed hit reads to a fact-checking pass as
"the record does not say this" — a finding the pass reports and a judge acts
on. So the wrap-tolerance and exit-status tests below are the load-bearing
ones, not the formatting niceties.
"""

import subprocess
import sys
from pathlib import Path

import pytest

import pdf_page_grep

SCRIPT = Path(pdf_page_grep.__file__)


# `pdftotext -layout` pads with spaces and wraps mid-sentence; page 2 is
# separated by a form feed, which is how page numbers are counted.
WRAPPED = (
    "IN THE DISTRICT COURT\n"
    "\n"
    "The court granted summary\n"
    "judgment on the record before it.\n"
    "\f"
    "The parties later filed a written\n"
    "stipulation    for   a  continuance.\n"
)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "order.txt"
    path.write_text(WRAPPED, encoding="utf-8")
    return path


def run(*args):
    """Invoke the CLI the way a pass would, returning (status, stdout, stderr)."""
    proc = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


# --- the reason this script exists -----------------------------------------

def test_phrase_split_across_a_line_break_still_matches(doc):
    """The bug the throwaway scripts shared: a literal search misses this."""
    status, out, _ = run("summary judgment", doc)
    assert status == 0
    assert "order.txt:1:" in out


def test_raw_mode_reproduces_the_old_miss(doc):
    status, out, _ = run("--raw", "summary judgment", doc)
    assert status == 1
    assert out == ""


def test_runs_of_whitespace_collapse(doc):
    """`-layout` column padding must not defeat a multi-word phrase."""
    status, out, _ = run("stipulation for a continuance", doc)
    assert status == 0
    assert "order.txt:2:" in out


def test_pages_are_counted_by_form_feed(doc):
    _, out, _ = run("continuance", doc)
    assert out.startswith("order.txt:2:")
    _, out, _ = run("DISTRICT COURT", doc)
    assert out.startswith("order.txt:1:")


# --- exit status: a mistyped path must never read as "not in the record" ----

def test_missing_file_is_a_read_error_not_a_miss(tmp_path):
    status, _, err = run("anything", tmp_path / "typo.pdf")
    assert status == 2
    assert "could not extract text" in err


def test_unreadable_file_reports_two_even_alongside_hits(doc, tmp_path):
    status, out, err = run("summary judgment", doc, tmp_path / "typo.pdf")
    assert status == 2                       # coverage was incomplete
    assert "order.txt:1:" in out             # and the hit is still reported
    assert "typo.pdf" in err


def test_clean_miss_is_status_one(doc):
    status, out, _ = run("mandamus", doc)
    assert status == 1
    assert out == ""


def test_bad_regex_is_status_two(doc):
    status, _, err = run("-e", "[", doc)
    assert status == 2
    assert "bad pattern" in err


# --- matching options ------------------------------------------------------

def test_search_is_case_insensitive_by_default(doc):
    assert run("SUMMARY JUDGMENT", doc)[0] == 0


def test_case_sensitive_flag(doc):
    assert run("-s", "SUMMARY JUDGMENT", doc)[0] == 1
    assert run("-s", "summary judgment", doc)[0] == 0


def test_pattern_is_literal_unless_regex_requested(doc):
    """A citation like 'R31.' must not be read as a regex by accident."""
    assert run("court.granted", doc)[0] == 1
    assert run("-e", "court.granted", doc)[0] == 0


def test_whole_word(doc):
    assert run("-w", "court", doc)[0] == 0
    assert run("-w", "cour", doc)[0] == 1
    assert run("cour", doc)[0] == 0


def test_json_output_carries_page_and_path(doc):
    import json
    status, out, _ = run("--json", "continuance", doc)
    assert status == 0
    payload = json.loads(out)
    assert payload["unreadable"] == []
    assert payload["hits"][0]["page"] == 2
    assert payload["hits"][0]["file"] == "order.txt"
    assert payload["hits"][0]["path"] == str(doc)


def test_json_lists_unreadable_files(doc, tmp_path):
    import json
    _, out, _ = run("--json", "continuance", doc, tmp_path / "typo.pdf")
    assert json.loads(out)["unreadable"] == [str(tmp_path / "typo.pdf")]


def test_max_per_file_caps_output(tmp_path):
    path = tmp_path / "many.txt"
    path.write_text("hit " * 50, encoding="utf-8")
    _, out, _ = run("--max-per-file", "3", "hit", path)
    assert len(out.strip().splitlines()) == 3


# --- text sourcing ---------------------------------------------------------

def test_sidecar_text_is_preferred_over_extraction(tmp_path):
    """Passes extract once and reuse; a .pdf with no bytes must still search."""
    pdf = tmp_path / "brief.pdf"
    pdf.write_bytes(b"not a real pdf")
    pdf.with_suffix(".txt").write_text("The stipulation appears here.", encoding="utf-8")
    status, out, _ = run("stipulation", pdf)
    assert status == 0
    assert "brief.pdf:1:" in out


def test_ocr_sidecar_is_used_when_no_plain_sidecar(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"not a real pdf")
    pdf.with_suffix(".ocr.txt").write_text("Recovered by OCR.", encoding="utf-8")
    assert run("recovered", pdf)[0] == 0


def test_empty_page_yields_a_miss_not_an_error(tmp_path):
    """A text layer that extracts to nothing is 'no hits' — OCR is the recovery."""
    path = tmp_path / "blank.txt"
    path.write_text("", encoding="utf-8")
    assert run("anything", path)[0] == 1


# --- snippets --------------------------------------------------------------

def test_snippet_context_is_adjustable(doc):
    _, narrow, _ = run("--context", "5", "continuance", doc)
    _, wide, _ = run("--context", "80", "continuance", doc)
    assert len(narrow) < len(wide)


def test_snippet_is_one_line(doc):
    _, out, _ = run("summary judgment", doc)
    assert len(out.strip().splitlines()) == 1


def test_snippet_marks_truncation(doc):
    _, out, _ = run("--context", "5", "judgment", doc)
    assert "..." in out

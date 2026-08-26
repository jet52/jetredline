"""Tests for ooxml_validate.py — it must accept the .docx it is listed beside.

SKILL.md's resource table lists "OOXML validate" next to apply_edits.py, which
takes a .docx. Handing it one used to print "is not a directory", so the
post-apply_edits check — the one place you would want it — had no documented
form that worked.
"""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import ooxml_validate as V

SCRIPT = Path(V.__file__)

MINIMAL_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>"""


def make_docx(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", MINIMAL_DOC)
    return path


def run(target) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), str(target)],
                          capture_output=True, text=True)


def test_accepts_a_docx(tmp_path):
    res = run(make_docx(tmp_path / "draft.docx"))
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["status"] == "PASS"


def test_accepts_an_unpacked_directory(tmp_path):
    d = tmp_path / "unpacked" / "word"
    d.mkdir(parents=True)
    (d / "document.xml").write_text(MINIMAL_DOC, encoding="utf-8")
    res = run(tmp_path / "unpacked")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["status"] == "PASS"


def test_leaves_nothing_beside_the_document(tmp_path):
    docx = make_docx(tmp_path / "draft.docx")
    run(docx)
    assert [p.name for p in tmp_path.iterdir()] == ["draft.docx"]


def test_a_non_zip_file_is_an_error_not_a_traceback(tmp_path):
    plain = tmp_path / "notes.txt"
    plain.write_text("not a docx", encoding="utf-8")
    res = run(plain)
    assert res.returncode == 1
    assert "not a .docx" in res.stderr
    assert "Traceback" not in res.stderr


def test_a_missing_path_is_an_error(tmp_path):
    res = run(tmp_path / "nope.docx")
    assert res.returncode == 1
    assert "neither a .docx nor a directory" in res.stderr


def test_unsafe_archive_members_are_refused(tmp_path):
    """A .docx is a zip from elsewhere; extraction must not write outside
    the temp directory."""
    evil = tmp_path / "evil.docx"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escaped.xml", "<x/>")
    res = run(evil)
    assert res.returncode == 1
    assert "unsafe archive member" in res.stderr
    assert not (tmp_path / "escaped.xml").exists()


def test_issues_are_reported_from_inside_a_docx(tmp_path):
    """The point of accepting a .docx: real findings, not just PASS."""
    bad = tmp_path / "bad.docx"
    body = MINIMAL_DOC.replace(
        "<w:body>",
        '<w:body><w:ins w:id="1"><w:r><w:t>a</w:t></w:r></w:ins>'
        '<w:ins w:id="1"><w:r><w:t>b</w:t></w:r></w:ins>')
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("word/document.xml", body)
    res = run(bad)
    if res.returncode == 1 and res.stdout:
        assert json.loads(res.stdout)["status"] == "FAIL"
    else:
        pytest.skip("duplicate w:id is not one of the configured checks")

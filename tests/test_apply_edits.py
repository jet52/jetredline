"""Regression tests for apply_edits.py — rId collisions and skip atomicity."""

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "jetredline"
APPLY_EDITS = SKILL_DIR / "apply_edits.py"

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType='
    '"application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType='
    '"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>'
)

_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns='
    '"http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
)

_DOC_HEADER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document'
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:body>'
)
_DOC_FOOTER = '</w:body></w:document>'


def make_docx(tmp_path, body_xml, name="input.docx"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("word/_rels/document.xml.rels", _RELS)
        zf.writestr("word/document.xml", _DOC_HEADER + body_xml + _DOC_FOOTER)
    return path


def run_apply_edits(tmp_path, docx, edits):
    edits_path = tmp_path / "edits.json"
    edits_path.write_text(json.dumps(edits))
    output = tmp_path / "output.docx"
    proc = subprocess.run(
        [sys.executable, str(APPLY_EDITS), "--input", str(docx),
         "--edits", str(edits_path), "--output", str(output)],
        capture_output=True, text=True)
    summary = json.loads(proc.stdout)
    return proc, summary, output


def test_comment_then_hyperlink_no_rid_collision(tmp_path):
    """Comment rels and hyperlink rels must draw from one Id sequence."""
    body = (
        '<w:p><w:r><w:t xml:space="preserve">See Tracey v. Tracey, '
        '2023 ND 219, for the standard.</w:t></w:r></w:p>'
    )
    docx = make_docx(tmp_path, body)
    edits = [
        {"type": "comment", "para": 1, "anchor": "the standard",
         "comment": "Cite the paragraph."},
        {"type": "hyperlink", "para": 1, "anchor": "2023 ND 219",
         "url": "https://www.ndcourts.gov/supreme-court/opinion/2023ND219"},
    ]
    proc, summary, output = run_apply_edits(tmp_path, docx, edits)
    assert summary["edits_applied"] == 2, summary

    with zipfile.ZipFile(output) as zf:
        rels = zf.read("word/_rels/document.xml.rels").decode("utf-8")
    ids = re.findall(r'Id="(rId\d+)"', rels)
    assert len(ids) == len(set(ids)), f"duplicate relationship Ids: {ids}"
    assert 'TargetMode="External"' in rels          # hyperlink rel present
    assert "comments.xml" in rels                    # comment rels present


def test_skipped_replace_leaves_document_untouched(tmp_path):
    """A replace spanning into an existing tracked change must not mutate
    anything before reporting 'skipped'."""
    body = (
        '<w:p><w:r><w:t xml:space="preserve">The court finds </w:t></w:r>'
        '<w:ins w:id="90" w:author="Editor" w:date="2026-01-01T00:00:00Z">'
        '<w:r><w:t xml:space="preserve">clearly </w:t></w:r></w:ins>'
        '<w:r><w:t>erroneous conduct.</w:t></w:r></w:p>'
    )
    docx = make_docx(tmp_path, body)
    # Match spans the plain first run AND the run inside w:ins.
    edits = [{"type": "replace", "para": 1,
              "old": "finds clearly erroneous",
              "new": "concludes clearly erroneous"}]
    proc, summary, output = run_apply_edits(tmp_path, docx, edits)
    assert summary["edits_skipped"] == 1, summary
    assert summary["edits_applied"] == 0

    with zipfile.ZipFile(output) as zf:
        doc = zf.read("word/document.xml").decode("utf-8")
    assert "<w:del" not in doc                       # nothing marked deleted
    assert "The court finds " in doc                 # first run not split
    assert doc.count("<w:r>") == 3                   # run structure intact


def test_plain_replace_still_works(tmp_path):
    body = (
        '<w:p><w:r><w:t xml:space="preserve">It is well settled that '
        'the court must consider the factors.</w:t></w:r></w:p>'
    )
    docx = make_docx(tmp_path, body)
    edits = [{"type": "replace", "para": 1,
              "old": "It is well settled that the court",
              "new": "The court"}]
    proc, summary, output = run_apply_edits(tmp_path, docx, edits)
    assert summary["edits_applied"] == 1, summary
    with zipfile.ZipFile(output) as zf:
        doc = zf.read("word/document.xml").decode("utf-8")
    assert "<w:del " in doc and "<w:ins " in doc
    assert "The court" in doc

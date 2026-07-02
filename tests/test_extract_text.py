"""Tests for extract_text.py — .docx -> markdown extraction."""

import zipfile

import pytest

from extract_text import extract

_DOC_HEADER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document'
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
    '<w:body>'
)
_DOC_FOOTER = '</w:body></w:document>'

_NUMBERING_PILCROW = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:numbering'
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:abstractNum w:abstractNumId="0">'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
    '<w:lvlText w:val="[¶%1]"/></w:lvl>'
    '</w:abstractNum>'
    '<w:num w:numId="5"><w:abstractNumId w:val="0"/></w:num>'
    '</w:numbering>'
)

_FOOTNOTES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:footnotes'
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    '<w:footnote w:id="2"><w:p><w:r><w:t>See 2024 ND 156, ¶ 12.</w:t></w:r></w:p></w:footnote>'
    '</w:footnotes>'
)


def _p(text):
    return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def _numbered_p(text, num_id="5", ilvl="0"):
    return (f'<w:p><w:pPr><w:numPr><w:ilvl w:val="{ilvl}"/>'
            f'<w:numId w:val="{num_id}"/></w:numPr></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')


def make_docx(tmp_path, body_xml, numbering=None, footnotes=None,
              name="draft.docx"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", _DOC_HEADER + body_xml + _DOC_FOOTER)
        if numbering:
            zf.writestr("word/numbering.xml", numbering)
        if footnotes:
            zf.writestr("word/footnotes.xml", footnotes)
    return path


def test_basic_paragraphs(tmp_path):
    docx = make_docx(tmp_path, _p("First paragraph.") + _p("Second paragraph."))
    text, summary = extract(docx)
    assert text == "First paragraph.\n\nSecond paragraph.\n"
    assert summary["paragraphs"] == 2


def test_literal_para_markers_pass_through(tmp_path):
    body = "".join(_p(f"[¶{n}] Text of paragraph {n}.") for n in range(1, 5))
    docx = make_docx(tmp_path, body, numbering=_NUMBERING_PILCROW)
    text, summary = extract(docx)
    assert "[¶2] Text of paragraph 2." in text
    assert summary["literal_para_markers"] == 4
    assert summary["synthesized_numbering"] == 0


def test_auto_numbering_synthesized(tmp_path):
    body = "".join(_numbered_p(f"Text of paragraph {n}.") for n in range(1, 4))
    docx = make_docx(tmp_path, body, numbering=_NUMBERING_PILCROW)
    text, summary = extract(docx)
    assert "[¶1] Text of paragraph 1." in text
    assert "[¶3] Text of paragraph 3." in text
    assert summary["synthesized_numbering"] == 3


def test_start_override_respected(tmp_path):
    numbering = _NUMBERING_PILCROW.replace(
        '<w:num w:numId="5"><w:abstractNumId w:val="0"/></w:num>',
        '<w:num w:numId="5"><w:abstractNumId w:val="0"/>'
        '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="7"/></w:lvlOverride>'
        '</w:num>')
    body = _numbered_p("First.") + _numbered_p("Second.")
    docx = make_docx(tmp_path, body, numbering=numbering)
    text, _ = extract(docx)
    assert "[¶7] First." in text
    assert "[¶8] Second." in text


def test_tracked_changes_as_accepted(tmp_path):
    body = (
        '<w:p><w:r><w:t xml:space="preserve">The court </w:t></w:r>'
        '<w:del w:id="1" w:author="Claude">'
        '<w:r><w:delText xml:space="preserve">finds </w:delText></w:r></w:del>'
        '<w:ins w:id="2" w:author="Claude">'
        '<w:r><w:t xml:space="preserve">concludes </w:t></w:r></w:ins>'
        '<w:r><w:t>otherwise.</w:t></w:r></w:p>'
    )
    docx = make_docx(tmp_path, body)
    text, summary = extract(docx)
    assert text == "The court concludes otherwise.\n"
    assert summary["tracked_insertions"] == 1
    assert summary["tracked_deletions"] == 1


def test_footnotes_extracted(tmp_path):
    body = (
        '<w:p><w:r><w:t>A claim.</w:t></w:r>'
        '<w:r><w:footnoteReference w:id="2"/></w:r>'
        '<w:r><w:t xml:space="preserve"> More text.</w:t></w:r></w:p>'
    )
    docx = make_docx(tmp_path, body, footnotes=_FOOTNOTES)
    text, summary = extract(docx)
    assert "A claim.[^2] More text." in text
    assert "[^2]: See 2024 ND 156, ¶ 12." in text
    assert summary["footnotes"] == 1


def test_textbox_and_field_instructions_excluded(tmp_path):
    body = (
        '<w:p><w:r><w:t>Visible text.</w:t></w:r>'
        '<w:r><w:instrText xml:space="preserve"> HYPERLINK "http://x" </w:instrText></w:r>'
        '<w:r><w:pict><w:txbxContent>'
        '<w:p><w:r><w:t>Text box content.</w:t></w:r></w:p>'
        '</w:txbxContent></w:pict></w:r></w:p>'
    )
    docx = make_docx(tmp_path, body)
    text, summary = extract(docx)
    assert text == "Visible text.\n"
    assert summary["paragraphs"] == 1


def test_tabs_breaks_and_nbsp_preserved(tmp_path):
    body = (
        '<w:p><w:r><w:t xml:space="preserve">¶ 12 line one</w:t>'
        '<w:br/><w:t>line two</w:t><w:tab/><w:t>after tab</w:t></w:r></w:p>'
    )
    docx = make_docx(tmp_path, body)
    text, _ = extract(docx)
    assert "¶ 12 line one\nline two\tafter tab" in text


def test_table_paragraphs_included(tmp_path):
    body = (
        '<w:tbl><w:tr><w:tc>' + _p("Cell text.") + '</w:tc></w:tr></w:tbl>'
        + _p("Body text.")
    )
    docx = make_docx(tmp_path, body)
    text, _ = extract(docx)
    assert "Cell text." in text
    assert "Body text." in text


def test_empty_paragraphs_skipped(tmp_path):
    docx = make_docx(tmp_path, _p("One.") + "<w:p/>" + _p("Two."))
    text, summary = extract(docx)
    assert text == "One.\n\nTwo.\n"
    assert summary["paragraphs"] == 2


def test_not_a_docx_raises(tmp_path):
    path = tmp_path / "bad.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("unrelated.txt", "nope")
    with pytest.raises(ValueError):
        extract(path)


_STYLES_MAINBODY = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles'
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:style w:type="paragraph" w:styleId="MainBody">'
    '<w:basedOn w:val="Normal"/>'
    '<w:pPr><w:numPr><w:numId w:val="5"/></w:numPr></w:pPr>'
    '</w:style>'
    '<w:style w:type="paragraph" w:styleId="BlockQuote">'
    '<w:basedOn w:val="MainBody"/>'
    '<w:pPr><w:numPr><w:numId w:val="0"/></w:numPr></w:pPr>'
    '</w:style>'
    '</w:styles>'
)


def _styled_p(text, style):
    return (f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')


def test_style_chain_numbering_and_numid_zero_suppression(tmp_path):
    body = (
        _styled_p("First numbered.", "MainBody")
        + _styled_p("A quoted passage.", "BlockQuote")
        + _styled_p("Second numbered.", "MainBody")
    )
    path = tmp_path / "styled.docx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", _DOC_HEADER + body + _DOC_FOOTER)
        zf.writestr("word/numbering.xml", _NUMBERING_PILCROW)
        zf.writestr("word/styles.xml", _STYLES_MAINBODY)
    text, summary = extract(path)
    lines = text.split("\n\n")
    assert lines[0] == "[¶1] First numbered."
    assert lines[1] == "A quoted passage."   # numId=0 → no marker
    assert lines[2].rstrip() == "[¶2] Second numbered."
    assert summary["synthesized_numbering"] == 2

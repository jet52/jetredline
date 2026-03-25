"""Tests for cite_review.py — citation review HTML generator."""

import json
import re

import pytest

from cite_review import (
    _IFRAME_OK_DOMAINS,
    _build_html,
    _find_paragraph,
    _opinion_to_html,
    _split_paragraphs,
)


# ---------------------------------------------------------------------------
# _split_paragraphs
# ---------------------------------------------------------------------------

class TestSplitParagraphs:
    def test_standard_markers(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        nums = [p["num"] for p in paras]
        assert nums == [1, 2, 3, 4]

    def test_bracketed_markers(self):
        text = "[¶1] First.\n\n[¶2] Second.\n\n[¶3] Third."
        paras = _split_paragraphs(text)
        assert len(paras) == 3
        assert paras[0]["num"] == 1
        assert "First." in paras[0]["text"]

    def test_no_markers(self):
        text = "This is a plain paragraph with no markers."
        paras = _split_paragraphs(text)
        assert len(paras) == 1
        assert paras[0]["num"] is None
        assert "plain paragraph" in paras[0]["text"]

    def test_single_paragraph(self):
        text = "[¶1] Only one paragraph here."
        paras = _split_paragraphs(text)
        assert len(paras) == 1
        assert paras[0]["num"] == 1

    def test_no_space_after_pilcrow(self):
        text = "[¶1]First.\n\n[¶2]Second."
        paras = _split_paragraphs(text)
        assert len(paras) == 2
        assert "First." in paras[0]["text"]

    def test_high_paragraph_numbers(self):
        text = "[¶99] Ninety-nine.\n\n[¶100] One hundred."
        paras = _split_paragraphs(text)
        assert paras[0]["num"] == 99
        assert paras[1]["num"] == 100

    def test_paragraph_text_boundaries(self, sample_opinion):
        """Each paragraph's text should not bleed into the next."""
        paras = _split_paragraphs(sample_opinion)
        # ¶1 should contain Tracey but not Henderson
        assert "Tracey" in paras[0]["text"]
        assert "Henderson" not in paras[0]["text"]
        # ¶3 should contain Henderson
        assert "Henderson" in paras[2]["text"]


# ---------------------------------------------------------------------------
# _find_paragraph
# ---------------------------------------------------------------------------

class TestFindParagraph:
    def test_exact_match(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _find_paragraph(paras, "2023 ND 219")
        assert result is not None
        assert result["num"] == 1

    def test_different_paragraph(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _find_paragraph(paras, "2024 ND 42")
        assert result is not None
        assert result["num"] == 3

    def test_not_found(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _find_paragraph(paras, "2099 ND 999")
        assert result is None

    def test_whitespace_normalized_match(self):
        paras = [{"num": 1, "text": "See  State  v.  Henderson,  2024 ND 42."}]
        result = _find_paragraph(paras, "State v. Henderson, 2024 ND 42")
        assert result is not None

    def test_statute_citation(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _find_paragraph(paras, "N.D.C.C. § 14-05-24")
        assert result is not None
        assert result["num"] == 2


# ---------------------------------------------------------------------------
# _opinion_to_html
# ---------------------------------------------------------------------------

class TestOpinionToHtml:
    def test_paragraphs_have_anchors(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        html = _opinion_to_html(sample_opinion, paras)
        assert 'id="para-1"' in html
        assert 'id="para-2"' in html
        assert 'id="para-3"' in html
        assert 'id="para-4"' in html

    def test_paragraph_markers(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        html = _opinion_to_html(sample_opinion, paras)
        assert "[¶1]" in html
        assert "[¶4]" in html

    def test_text_is_escaped(self):
        text = '[¶1] The statute says "X < Y" and A & B.'
        paras = _split_paragraphs(text)
        html = _opinion_to_html(text, paras)
        assert "&lt;" in html
        assert "&amp;" in html
        assert "<script>" not in html

    def test_no_markers_fallback(self):
        text = "Plain text with no markers."
        paras = _split_paragraphs(text)
        html = _opinion_to_html(text, paras)
        assert "opinion-text" in html
        assert "Plain text" in html

    def test_header_before_first_paragraph(self):
        text = "Case Caption\nJudge Name\n\n[¶1] First paragraph."
        paras = _split_paragraphs(text)
        html = _opinion_to_html(text, paras)
        assert "opinion-header" in html
        assert "Case Caption" in html

    def test_no_header_when_starts_with_para(self):
        text = "[¶1] Starts immediately."
        paras = _split_paragraphs(text)
        html = _opinion_to_html(text, paras)
        assert "opinion-header" not in html

    def test_opinion_para_class(self, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        html = _opinion_to_html(sample_opinion, paras)
        assert html.count('class="opinion-para"') == 4


# ---------------------------------------------------------------------------
# _build_html
# ---------------------------------------------------------------------------

class TestBuildHtml:
    @pytest.fixture
    def citations_basic(self):
        """Citation data mimicking nd_cite_check.py output."""
        return [
            {
                "cite_text": "2023 ND 219",
                "cite_type": "nd_case",
                "normalized": "2023 ND 219",
                "url": "https://www.ndcourts.gov/supreme-court/opinions/12345",
            },
            {
                "cite_text": "N.D.C.C. § 14-05-24",
                "cite_type": "ndcc",
                "normalized": "N.D.C.C. § 14-05-24",
                "url": "https://ndlegis.gov/cencode/t14c05.pdf",
            },
            {
                "cite_text": "2024 ND 42",
                "cite_type": "nd_case",
                "normalized": "2024 ND 42",
                "url": "https://www.ndcourts.gov/supreme-court/opinions/67890",
            },
            {
                "cite_text": "445 U.S. 684",
                "cite_type": "us_supreme_court",
                "normalized": "445 U.S. 684",
                "url": "https://supreme.justia.com/cases/federal/us/445/684/",
            },
            {
                "cite_text": "938 N.W.2d 897",
                "cite_type": "state_reporter",
                "normalized": "938 N.W.2d 897",
                "url": "https://www.courtlistener.com/c/N.W.%202d/938/897/",
            },
        ]

    def test_produces_valid_html(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test Case", citations_basic, paras, "test", sample_opinion)
        assert result.startswith("<!DOCTYPE html>")
        assert "</html>" in result

    def test_embedded_data_is_valid_json(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test Case", citations_basic, paras, "test", sample_opinion)
        m = re.search(r"const DATA = (\[.*?\]);\s*\n", result, re.DOTALL)
        assert m is not None, "DATA array not found in HTML"
        data = json.loads(m.group(1))
        assert len(data) == 5

    def test_iframe_ok_for_nd_sources(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test Case", citations_basic, paras, "test", sample_opinion)
        m = re.search(r"const DATA = (\[.*?\]);\s*\n", result, re.DOTALL)
        data = json.loads(m.group(1))
        # ndcourts.gov → iframe OK
        assert data[0]["iframe_ok"] is True
        # ndlegis.gov → iframe OK
        assert data[1]["iframe_ok"] is True
        # Second ndcourts.gov → iframe OK
        assert data[2]["iframe_ok"] is True
        # justia → blocked
        assert data[3]["iframe_ok"] is False
        # courtlistener → blocked
        assert data[4]["iframe_ok"] is False

    def test_opinion_html_embedded(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test Case", citations_basic, paras, "test", sample_opinion)
        assert 'id="opinion-body"' in result
        assert 'id="para-1"' in result
        assert 'class="opinion-para"' in result

    def test_no_para_text_in_data(self, citations_basic, sample_opinion):
        """para_text is no longer in the JSON data — opinion is embedded as HTML."""
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test Case", citations_basic, paras, "test", sample_opinion)
        m = re.search(r"const DATA = (\[.*?\]);\s*\n", result, re.DOTALL)
        data = json.loads(m.group(1))
        for d in data:
            assert "para_text" not in d

    def test_paragraph_num_attached(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test Case", citations_basic, paras, "test", sample_opinion)
        m = re.search(r"const DATA = (\[.*?\]);\s*\n", result, re.DOTALL)
        data = json.loads(m.group(1))
        # 2023 ND 219 is in ¶1
        assert data[0]["para_num"] == 1

    def test_title_escaped_in_html(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html(
            'Test <script>alert("xss")</script>',
            citations_basic, paras, "test", sample_opinion
        )
        assert "<script>alert" not in result.split("<script>")[0]  # not in body
        assert "&lt;script&gt;" in result

    def test_has_iframe_css(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test", citations_basic, paras, "test", sample_opinion)
        assert ".pane-src iframe" in result

    def test_has_open_tab_button_css(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test", citations_basic, paras, "test", sample_opinion)
        assert ".open-tab-btn" in result

    def test_citation_count_in_header(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test", citations_basic, paras, "test", sample_opinion)
        assert "Citations (5)" in result

    def test_notes_input_in_action_bar(self, citations_basic, sample_opinion):
        paras = _split_paragraphs(sample_opinion)
        result = _build_html("Test", citations_basic, paras, "test", sample_opinion)
        assert 'id="notes-input"' in result
        # No textarea — notes is now an input
        assert "<textarea" not in result


# ---------------------------------------------------------------------------
# JS content checks
# ---------------------------------------------------------------------------

class TestJsContent:
    def test_iframe_ok_branch_in_js(self):
        import cite_review
        js = cite_review._JS
        assert "d.iframe_ok" in js

    def test_scrollIntoView_in_js(self):
        import cite_review
        js = cite_review._JS
        assert "scrollIntoView" in js

    def test_active_para_class_in_js(self):
        import cite_review
        js = cite_review._JS
        assert "active-para" in js

    def test_open_tab_btn_in_js(self):
        import cite_review
        js = cite_review._JS
        assert "open-tab-btn" in js

    def test_no_local_content_in_js(self):
        """local_content logic should be completely removed."""
        import cite_review
        js = cite_review._JS
        assert "local_content" not in js

    def test_notes_input_not_textarea(self):
        import cite_review
        js = cite_review._JS
        assert "notes-input" in js
        assert "notes-ta" not in js


# ---------------------------------------------------------------------------
# iframe domain list
# ---------------------------------------------------------------------------

class TestIframeOkDomains:
    def test_ndcourts_allowed(self):
        assert "www.ndcourts.gov" in _IFRAME_OK_DOMAINS
        assert "ndcourts.gov" in _IFRAME_OK_DOMAINS

    def test_ndlegis_allowed(self):
        assert "ndlegis.gov" in _IFRAME_OK_DOMAINS

    def test_courtlistener_blocked(self):
        assert "www.courtlistener.com" not in _IFRAME_OK_DOMAINS

    def test_justia_blocked(self):
        assert "supreme.justia.com" not in _IFRAME_OK_DOMAINS

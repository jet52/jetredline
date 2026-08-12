"""Tests for the factual-assertion review layer of cite_review.py —
Pass 4 facts ledger loading, record/brief PDF resolution, viewer
generation (sidecar and --link-pdfs), and page integration."""

import json
import re
import shutil
import subprocess

import pytest
from pypdf import PdfWriter

from cite_review import (
    _build_html,
    _candidate_manifests,
    _fact_source_hash,
    _find_quote_position,
    _generate_local_pdf_viewers,
    _load_facts,
    _load_manifest,
    _normalize_result,
    _resolve_fact_source,
    _split_paragraphs,
    _viewer_name,
)


def _write_pdf(path, pages=1):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    with open(path, "wb") as fh:
        w.write(fh)


# ---------------------------------------------------------------------------
# Ledger loading and normalization
# ---------------------------------------------------------------------------

class TestFactsLedger:
    @pytest.mark.parametrize("raw,want", [
        ("Verified", "verified"),
        ("Verified but incomplete", "verified"),
        ("Verified (tightened)", "verified"),
        ("Discrepancy", "discrepancy"),
        ("**Discrepancy** (omission)", "discrepancy"),
        ("Unverified", "unverified"),
        ("", "unverified"),
        (None, "unverified"),
    ])
    def test_normalize_result(self, raw, want):
        assert _normalize_result(raw) == want

    def test_load_bare_array_and_claims_wrapper(self, tmp_path):
        claims = [{"para": "5", "claim": "X happened",
                   "result": "Discrepancy (attribution)",
                   "sources": [{"raw": "R243, p. 6"}]}]
        for payload in (claims, {"claims": claims}):
            p = tmp_path / "facts.json"
            p.write_text(json.dumps(payload))
            got = _load_facts(p)
            assert len(got) == 1
            assert got[0]["result"] == "discrepancy"
            assert got[0]["result_label"] == "Discrepancy (attribution)"
            assert got[0]["sources"][0]["raw"] == "R243, p. 6"

    def test_load_skips_malformed_entries(self, tmp_path):
        p = tmp_path / "facts.json"
        p.write_text(json.dumps([{"claim": "ok"}, {"para": "3"}, "junk"]))
        assert [f["claim"] for f in _load_facts(p)] == ["ok"]


class TestQuotePosition:
    def test_exact_match(self):
        assert _find_quote_position("abc the court held xyz", "court held") == 8

    def test_curly_quote_folding_both_directions(self):
        text = "the court denied Osman’s motion"
        assert _find_quote_position(text, "Osman's motion") == 17
        assert _find_quote_position("Osman's motion", "Osman’s motion") == 0

    def test_absent_returns_none(self):
        assert _find_quote_position("abc", "zzz") is None
        assert _find_quote_position("abc", "") is None


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

class TestSourceResolution:
    @pytest.fixture
    def record_dir(self, tmp_path):
        d = tmp_path / "record"
        d.mkdir()
        for name in ("R24 - Order Something.pdf",
                     "R243 - Order Denying Motion.pdf"):
            _write_pdf(d / name)
        return d

    def test_record_item_boundary(self, record_dir, tmp_path):
        got = _resolve_fact_source({"item": "R243"}, record_dir, [], tmp_path)
        assert got.name == "R243 - Order Denying Motion.pdf"
        got = _resolve_fact_source({"item": "R24"}, record_dir, [], tmp_path)
        assert got.name == "R24 - Order Something.pdf"

    def test_record_item_from_raw_with_pin(self, record_dir, tmp_path):
        got = _resolve_fact_source({"raw": "R243, p. 6"}, record_dir, [],
                                   tmp_path)
        assert got.name == "R243 - Order Denying Motion.pdf"

    def test_docket_number_via_manifest(self, tmp_path):
        _write_pdf(tmp_path / "20260029_017_Apt-Br.pdf")
        manifest = [{"docketId": 17, "filename": "20260029_017_Apt-Br.pdf"}]
        got = _resolve_fact_source({"item": "017"}, None, manifest, tmp_path)
        assert got.name == "20260029_017_Apt-Br.pdf"

    def test_brief_name_fragment(self, tmp_path):
        _write_pdf(tmp_path / "20260029_017_Apt-Br.pdf")
        got = _resolve_fact_source({"item": "Apt-Br"}, None, [], tmp_path)
        assert got.name == "20260029_017_Apt-Br.pdf"

    def test_explicit_file_hint_wins(self, tmp_path):
        _write_pdf(tmp_path / "custom.pdf")
        got = _resolve_fact_source({"file": "custom.pdf", "item": "R999"},
                                   None, [], tmp_path)
        assert got.name == "custom.pdf"

    def test_unresolvable_returns_none(self, tmp_path):
        assert _resolve_fact_source({"item": "R999"}, None, [], tmp_path) is None

    def test_bare_digit_item_with_r_prefixed_raw(self, record_dir, tmp_path):
        """Pass 4 ledgers store item='785' with the R only in raw.

        Every record reference in one production run failed to resolve this
        way — 27 of 27 — because the regex required the prefix on `item`.
        """
        got = _resolve_fact_source({"item": "243", "raw": "R243, p. 6, para 12"},
                                   record_dir, [], tmp_path)
        assert got.name == "R243 - Order Denying Motion.pdf"

    def test_bare_digit_item_needs_corroborating_raw(self, record_dir, tmp_path):
        """A bare number alone is ambiguous with a docket id, so it must not
        be treated as a record item on its own."""
        assert _resolve_fact_source({"item": "243"}, record_dir, [],
                                    tmp_path) is None

    def test_bare_digit_item_ignores_mismatched_raw(self, record_dir, tmp_path):
        """raw naming a different item must not resolve the bare number."""
        assert _resolve_fact_source({"item": "243", "raw": "R24, p. 6"},
                                    record_dir, [], tmp_path) is None

    def test_bare_digit_still_reaches_manifest(self, tmp_path):
        """The docket-number path must survive the record-item change."""
        _write_pdf(tmp_path / "20260029_017_Apt-Br.pdf")
        manifest = [{"docketId": 17, "filename": "20260029_017_Apt-Br.pdf"}]
        got = _resolve_fact_source({"item": "017", "raw": "Appellee Br., p. 3"},
                                   None, manifest, tmp_path)
        assert got.name == "20260029_017_Apt-Br.pdf"


class TestManifestDiscovery:
    def test_prefers_case_dir(self, tmp_path):
        (tmp_path / "manifest.json").write_text("[]")
        (tmp_path / "briefs").mkdir()
        (tmp_path / "briefs" / "manifest.json").write_text("[]")
        got = _candidate_manifests(tmp_path)
        assert got[0] == tmp_path / "manifest.json"

    def test_finds_manifest_in_briefs_subdir(self, tmp_path):
        """jetmemo's downloader writes manifest.json beside the PDFs."""
        (tmp_path / "briefs").mkdir()
        (tmp_path / "briefs" / "manifest.json").write_text("[]")
        got = _candidate_manifests(tmp_path)
        assert got == [tmp_path / "briefs" / "manifest.json"]

    def test_conventional_names_sort_first(self, tmp_path):
        for sub in ("aaa_other", "briefs"):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "manifest.json").write_text("[]")
        got = _candidate_manifests(tmp_path)
        assert got[0].parent.name == "briefs"

    def test_skips_dot_and_dunder_dirs(self, tmp_path):
        for sub in (".tmp-abc", "__pycache__"):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "manifest.json").write_text("[]")
        assert _candidate_manifests(tmp_path) == []

    def test_no_manifest_anywhere(self, tmp_path):
        assert _candidate_manifests(tmp_path) == []

    def test_does_not_recurse_below_one_level(self, tmp_path):
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        (deep / "manifest.json").write_text("[]")
        assert _candidate_manifests(tmp_path) == []

    def test_manifest_loader_tolerates_garbage(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text('{"not": "a list"}')
        assert _load_manifest(p) == []
        assert _load_manifest(tmp_path / "absent.json") == []


# ---------------------------------------------------------------------------
# Viewer URL generation
# ---------------------------------------------------------------------------

class TestViewerGeneration:
    def test_hash_prefers_quote_then_para_pin(self):
        assert _fact_source_hash({"page": 6, "quote": "Dated this"}) == \
            "#page=6&hl=Dated%20this"
        h = _fact_source_hash({"para_pin": "¶ 9"})
        assert h.startswith("#search=")
        assert "%C2%B6%209" in h        # "¶ 9" candidate
        assert "9." in re.sub("%..", lambda m: bytes.fromhex(
            m.group(0)[1:]).decode("latin1"), h)
        assert _fact_source_hash({}) == ""

    def test_viewer_name_sanitizes_and_dedupes(self, tmp_path):
        taken = set()
        a = _viewer_name(tmp_path / "R243 - Order (Denying).pdf", taken)
        b = _viewer_name(tmp_path / "R243 - Order (Denying).pdf", taken)
        assert a != b
        assert " " not in a and "(" not in a

    def test_link_pdfs_mode_is_zero_copy(self, tmp_path):
        pdf = tmp_path / "case" / "R1 - Thing.pdf"
        pdf.parent.mkdir()
        _write_pdf(pdf)
        out = tmp_path / "case" / "review.html"
        got = _generate_local_pdf_viewers([pdf], out, link_pdfs=True)
        assert got[str(pdf.resolve())] == "R1 - Thing.pdf"
        assert not (tmp_path / "case" / "review_pdfs").exists()

    def test_sidecar_mode_embeds_base64(self, tmp_path):
        pdf = tmp_path / "R1 - Thing.pdf"
        _write_pdf(pdf)
        out = tmp_path / "review.html"
        got = _generate_local_pdf_viewers([pdf, pdf], out)
        assert len(got) == 1
        rel = got[str(pdf.resolve())]
        viewer = (tmp_path / rel).read_text()
        assert "PDF_DATA" in viewer and "JVBERi" in viewer  # %PDF b64
        assert "normWithMap" in viewer                      # v2 template


# ---------------------------------------------------------------------------
# Page integration
# ---------------------------------------------------------------------------

OPINION = """[¶5] In October 2024, the court denied Osman’s motion.

[¶6] The court awarded support of $10,000 to Ali.
"""

CITES = [{"cite_text": "2023 ND 219", "cite_type": "neutral_cite",
          "normalized": "2023 ND 219", "jurisdiction": "nd",
          "url": "https://www.ndcourts.gov/supreme-court/opinions/1",
          "position": 6}]


def _facts():
    return [{
        "para": "5",
        "claim": "The court denied the motion in October 2024",
        "draft_quote": "the court denied Osman's motion",
        "result": "discrepancy",
        "result_label": "Discrepancy",
        "note": "Order dated January 27, 2025.",
        "sources": [
            {"raw": "R243, p. 6", "item": "R243", "page": 6,
             "quote": "Dated this 27th day of January, 2025",
             "_resolved_path": "/abs/R243.pdf"},
            {"raw": "R999", "item": "R999"},   # unresolved
        ],
    }]


class TestBuildHtmlFacts:
    def _page(self, link_pdfs=False):
        paras = _split_paragraphs(OPINION)
        return _build_html(
            "t", CITES, paras, "k", OPINION,
            facts=_facts(),
            fact_viewers={"/abs/R243.pdf": "review_pdfs/R243.html"},
            link_pdfs=link_pdfs)

    def _data(self, html_str):
        m = re.search(r"const DATA = (\[.*?\]);\n", html_str, re.DOTALL)
        return json.loads(m.group(1))

    def test_fact_entry_appended_with_anchor(self):
        data = self._data(self._page())
        facts = [d for d in data if d.get("kind") == "fact"]
        assert len(facts) == 1
        f = facts[0]
        assert f["para_num"] == 5
        assert f["position"] is not None       # curly-quote fold found it
        assert f["result"] == "discrepancy"
        assert f["sources"][0]["href"] == \
            "review_pdfs/R243.html#page=6&hl=Dated%20this%2027th%20day%20of%20January%2C%202025"
        assert f["sources"][1]["href"] is None  # unresolved ref degrades

    def test_link_pdfs_uses_page_only_hash(self):
        data = self._data(self._page(link_pdfs=True))
        f = [d for d in data if d.get("kind") == "fact"][0]
        assert f["sources"][0]["href"] == "review_pdfs/R243.html#page=6"

    def test_sidebar_section_and_state_prefix_present(self):
        html_str = self._page()
        assert "Factual assertions" in html_str
        assert "'fact'" in html_str            # kind branch in JS
        # fact state-key prefix keeps fact statuses separate from citations
        assert "d.kind === 'fact') ? 'f' : ''" in html_str
        assert "fact-banner" in html_str

    def test_citation_count_excludes_facts_in_sidebar_header(self):
        html_str = self._page()
        assert f"Citations ({len(CITES)})" in html_str

    def test_export_carries_machine_result(self):
        html_str = self._page()
        assert "machine_result" in html_str

    def test_authority_pdf_mode_renders_for_meta_pdf(self):
        paras = _split_paragraphs(OPINION)
        meta = {"2023 nd 219": {"pdf_viewer": {
            "href": "review_pdfs/treatise.html#page=3",
            "external": "review_pdfs/treatise.html",
            "label": "treatise.pdf"}}}
        html_str = _build_html("t", CITES, paras, "k", OPINION,
                               sources_meta=meta)
        data = self._data(html_str)
        assert data[0]["authority_pdf"]["href"].endswith("#page=3")
        assert "Local PDF" in html_str


class TestFactsPageJavaScriptParses:
    def test_page_with_facts_parses(self, tmp_path):
        node = shutil.which("node")
        if not node:
            pytest.skip("node not on PATH")
        paras = _split_paragraphs(OPINION)
        html_str = _build_html(
            "t", CITES, paras, "k", OPINION, facts=_facts(),
            fact_viewers={"/abs/R243.pdf": "review_pdfs/R243.html"})
        scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                             html_str, re.DOTALL)
        assert scripts
        for n, js in enumerate(scripts):
            f = tmp_path / f"facts_{n}.js"
            f.write_text(js, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)],
                               capture_output=True, text=True)
            assert r.returncode == 0, r.stderr

    def test_viewer_template_module_parses(self, tmp_path):
        node = shutil.which("node")
        if not node:
            pytest.skip("node not on PATH")
        from cite_review import _PDFJS_VIEWER_TEMPLATE
        js = re.findall(r"<script[^>]*type=.module.[^>]*>(.*?)</script>",
                        _PDFJS_VIEWER_TEMPLATE, re.DOTALL)[0]
        js = re.sub(r"^import .*$", "", js, flags=re.M).replace("await ", "")
        f = tmp_path / "viewer.mjs"
        f.write_text(js.replace("__PDF_BASE64__", ""), encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

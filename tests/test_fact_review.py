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
        text = "the court denied Gion’s motion"
        assert _find_quote_position(text, "Gion's motion") == 17
        assert _find_quote_position("Gion's motion", "Gion’s motion") == 0

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
        _write_pdf(tmp_path / "20990001_017_Apt-Br.pdf")
        manifest = [{"docketId": 17, "filename": "20990001_017_Apt-Br.pdf"}]
        got = _resolve_fact_source({"item": "017"}, None, manifest, tmp_path)
        assert got.name == "20990001_017_Apt-Br.pdf"

    def test_brief_name_fragment(self, tmp_path):
        _write_pdf(tmp_path / "20990001_017_Apt-Br.pdf")
        got = _resolve_fact_source({"item": "Apt-Br"}, None, [], tmp_path)
        assert got.name == "20990001_017_Apt-Br.pdf"

    def test_three_character_label_resolves_as_a_whole_token(self, tmp_path):
        """`ROA` (Register of Actions) is three characters. The old flat
        four-character floor skipped the name-fragment fallback entirely, so
        it could not resolve at all and needed a hand-injected `file` hint."""
        _write_pdf(tmp_path / "R12 - ROA.pdf")
        got = _resolve_fact_source({"item": "ROA"}, None, [], tmp_path)
        assert got.name == "R12 - ROA.pdf"

    def test_three_character_label_does_not_match_inside_a_word(self, tmp_path):
        """Which is why three characters match a whole token and not a
        substring: `roa` must not claim `Broad-Order`."""
        _write_pdf(tmp_path / "Broad-Order.pdf")
        assert _resolve_fact_source({"item": "ROA"}, None, [], tmp_path) is None

    def test_two_character_label_never_matches(self, tmp_path):
        """A two-character token collides with too much to be evidence."""
        _write_pdf(tmp_path / "R12 - Ex.pdf")
        assert _resolve_fact_source({"item": "Ex"}, None, [], tmp_path) is None

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
        _write_pdf(tmp_path / "20990001_017_Apt-Br.pdf")
        manifest = [{"docketId": 17, "filename": "20990001_017_Apt-Br.pdf"}]
        got = _resolve_fact_source({"item": "017", "raw": "Appellee Br., p. 3"},
                                   None, manifest, tmp_path)
        assert got.name == "20990001_017_Apt-Br.pdf"


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

    def test_identical_content_shares_one_sidecar(self, tmp_path):
        """A re-run's extract beside a hand-made copy must not embed twice."""
        a = tmp_path / "authorities" / "journal_p65-70.pdf"
        b = tmp_path / "hand" / "Journal-excerpt.pdf"
        a.parent.mkdir()
        b.parent.mkdir()
        a.write_bytes(b"%PDF-1.4 identical body")
        b.write_bytes(b"%PDF-1.4 identical body")
        out = tmp_path / "review.html"
        got = _generate_local_pdf_viewers([a, b], out)
        assert got[str(a.resolve())] == got[str(b.resolve())]
        assert len(list((tmp_path / "review_pdfs").glob("*.html"))) == 1

    def test_asset_budget_links_the_overflow_and_reports(self, tmp_path, capsys):
        small = tmp_path / "small.pdf"
        big = tmp_path / "big.pdf"
        small.write_bytes(b"%PDF tiny")
        big.write_bytes(b"%PDF " + b"x" * 5000)
        out = tmp_path / "review.html"
        got = _generate_local_pdf_viewers([big, small], out, asset_budget=1000)
        # Smallest-first: the small file embeds, the big one degrades to a link.
        assert got[str(small.resolve())].startswith("review_pdfs/")
        assert got[str(big.resolve())] == "big.pdf"
        err = capsys.readouterr().err
        assert "1 embedded" in err and "1 linked" in err and "big.pdf" in err

    def test_asset_budget_zero_embeds_nothing(self, tmp_path):
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF x")
        out = tmp_path / "review.html"
        got = _generate_local_pdf_viewers([pdf], out, asset_budget=0)
        assert got[str(pdf.resolve())] == "a.pdf"
        assert not (tmp_path / "review_pdfs").exists()


# ---------------------------------------------------------------------------
# Page integration
# ---------------------------------------------------------------------------

OPINION = """[¶5] In October 2019, the court denied Gion’s motion.

[¶6] The court awarded support of $1,234 to Marek.
"""

CITES = [{"cite_text": "2023 ND 219", "cite_type": "neutral_cite",
          "normalized": "2023 ND 219", "jurisdiction": "nd",
          "url": "https://www.ndcourts.gov/supreme-court/opinions/1",
          "position": 6}]


def _facts():
    return [{
        "para": "5",
        "claim": "The court denied the motion in October 2019",
        "draft_quote": "the court denied Gion's motion",
        "result": "discrepancy",
        "result_label": "Discrepancy",
        "note": "Order dated March 3, 2020.",
        "sources": [
            {"raw": "R243, p. 6", "item": "R243", "page": 6,
             "quote": "Dated this 3rd day of March, 2020",
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
            "review_pdfs/R243.html#page=6&hl=Dated%20this%203rd%20day%20of%20March%2C%202020"
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
        from cite_review import _pdfjs_viewer_template
        template = _pdfjs_viewer_template()
        js = re.findall(r"<script[^>]*type=.module.[^>]*>(.*?)</script>",
                        template, re.DOTALL)[0]
        js = re.sub(r"^import .*$", "", js, flags=re.M).replace("await ", "")
        f = tmp_path / "viewer.mjs"
        f.write_text(js.replace("__PDF_BASE64__", ""), encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def test_viewer_load_timeout_script_parses(self, tmp_path):
        """The classic script that notices a blocked CDN. It cannot live in
        the module script it guards: a failed ES-module import never runs the
        module body, which is the whole reason the timer exists."""
        node = shutil.which("node")
        if not node:
            pytest.skip("node not on PATH")
        from cite_review import _pdfjs_viewer_template
        template = _pdfjs_viewer_template()
        classic = [b for b in re.findall(
            r"<script(?![^>]*type=.module.)[^>]*>(.*?)</script>",
            template, re.DOTALL) if "__pdfjsLoaded" in b]
        assert classic, "no load-timeout script in the viewer template"
        f = tmp_path / "timeout.js"
        f.write_text(classic[0], encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def test_viewer_names_the_blocked_host(self):
        """The message has to name the host, or it tells the reader nothing
        they can act on."""
        from cite_review import _pdfjs_viewer_template
        assert "cdnjs.cloudflare.com</b>" in _pdfjs_viewer_template()
        mirror = _pdfjs_viewer_template("https://mirror.example.org/pdfjs/4.10.38/")
        assert "mirror.example.org</b>" in mirror
        assert "mirror.example.org/pdfjs/4.10.38/pdf.min.mjs" in mirror


# ---------------------------------------------------------------------------
# Name-fragment matching (bug report 2026-08-19, defect 2)
# ---------------------------------------------------------------------------

class TestFragmentMatching:
    @pytest.mark.parametrize("item,filename", [
        ("Brief - Appellee", "Brief - Appellee.pdf"),
        ("Brief of Appellants Burleigh County & Morton County",
         "Brief of Appellants Burleigh County & Morton County.pdf"),
    ])
    def test_space_hyphen_and_ampersand_names_match(self, tmp_path, item,
                                                    filename):
        _write_pdf(tmp_path / filename)
        got = _resolve_fact_source({"item": item}, None, [], tmp_path)
        assert got is not None and got.name == filename

    def test_whole_filename_matches_via_stem(self, tmp_path):
        # The old haystack kept the ".pdf" suffix glued on, so a needle
        # ending at the true end of the filename could never match.
        _write_pdf(tmp_path / "Reply Brief.pdf")
        got = _resolve_fact_source({"item": "Reply Brief"}, None, [], tmp_path)
        assert got.name == "Reply Brief.pdf"

    def test_unrelated_fragment_does_not_match(self, tmp_path):
        _write_pdf(tmp_path / "Brief - Reply.pdf")
        assert _resolve_fact_source({"item": "Reply Br."}, None, [],
                                    tmp_path) is None

    def test_manifest_fragment_uses_same_normalizer(self, tmp_path):
        _write_pdf(tmp_path / "Brief - Appellee.pdf")
        manifest = [{"docketId": 9, "filename": "Brief - Appellee.pdf"}]
        got = _resolve_fact_source({"item": "Brief - Appellee"}, None,
                                   manifest, tmp_path)
        assert got.name == "Brief - Appellee.pdf"

    def test_record_prefix_boundary_still_holds(self, tmp_path):
        d = tmp_path / "record"
        d.mkdir()
        _write_pdf(d / "R197-Order-Granting.pdf")
        assert _resolve_fact_source({"item": "R197"}, d, [], tmp_path) is not None
        assert _resolve_fact_source({"item": "R19"}, d, [], tmp_path) is None


# ---------------------------------------------------------------------------
# CLI preconditions, resolution rate, sidecar report, --bundle
# (bug report 2026-08-19, defects 1 and 3)
# ---------------------------------------------------------------------------

SCRIPT = __import__("pathlib").Path(__file__).resolve().parent.parent \
    / "skills" / "jetredline" / "cite_review.py"


def _run_cli(tmp_path, facts, *extra):
    import sys
    op = tmp_path / "opinion.md"
    op.write_text("[¶1] The court found the road was public. "
                  "Doe v. Roe, 2023 ND 219, ¶ 5.\n")
    fj = tmp_path / "facts.json"
    fj.write_text(json.dumps(facts))
    cites = tmp_path / "cites.json"
    cites.write_text(json.dumps([{
        "cite_text": "2023 ND 219, ¶ 5", "cite_type": "neutral_cite",
        "normalized": "2023 ND 219", "pinpoint": "¶ 5", "url": None,
        "local_path": str(tmp_path / "missing.md"), "local_exists": False,
    }]))
    out = tmp_path / "out" / "review.html"
    out.parent.mkdir(exist_ok=True)
    cmd = [sys.executable, str(SCRIPT), "--opinion", str(op),
           "--cite-json", str(cites),
           "--refs-dir", str(tmp_path / "refs"),
           "--facts-json", str(fj), "--output", str(out),
           "--case-dir", str(tmp_path), *extra]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r, out


def _fact(item, raw=None, quote="the road was public"):
    return {"claim": "the road was public", "para": 1, "result": "verified",
            "draft_quote": "the road was public",
            "sources": [{"raw": raw or f"{item}, p. 1", "item": item,
                         "page": 1, "quote": quote}]}


class TestCliGuards:
    def test_record_refs_without_record_dir_is_an_error(self, tmp_path):
        r, out = _run_cli(tmp_path, [_fact("R197"), _fact("R2")])
        assert r.returncode == 1, r.stderr
        assert "record-item source ref" in r.stderr
        assert "R197" in r.stderr and "--record-dir" in r.stderr
        assert not out.exists()

    def test_no_fact_sources_opts_out(self, tmp_path):
        r, out = _run_cli(tmp_path, [_fact("R197")], "--no-fact-sources")
        assert r.returncode == 0, r.stderr
        assert "text-only by request" in r.stderr
        html = out.read_text()
        assert "No PDF supplied for" in html
        assert "not re-verified" in html

    def test_low_resolution_rate_is_an_error(self, tmp_path):
        d = tmp_path / "record"
        d.mkdir()
        _write_pdf(d / "R1 - Complaint.pdf")
        facts = [_fact("R1")] + [_fact(f"R{n}") for n in range(50, 59)]
        r, out = _run_cli(tmp_path, facts, "--record-dir", str(d))
        assert r.returncode == 1
        assert "Fact sources: 1 of 10 resolved (10%)" in r.stderr

    def test_partial_resolution_warns_and_reports_rate(self, tmp_path):
        d = tmp_path / "record"
        d.mkdir()
        _write_pdf(d / "R1 - Complaint.pdf")
        facts = [_fact("R1")] * 3 + [_fact("R50")]
        r, out = _run_cli(tmp_path, facts, "--record-dir", str(d))
        assert r.returncode == 0, r.stderr
        assert "Warning: Fact sources: 3 of 4 resolved (75%)" in r.stderr

    def test_sidecar_reported_and_bundled(self, tmp_path):
        d = tmp_path / "record"
        d.mkdir()
        _write_pdf(d / "R1 - Complaint.pdf")
        bundle = tmp_path / "review.zip"
        r, out = _run_cli(tmp_path, [_fact("R1")], "--record-dir", str(d),
                          "--bundle", str(bundle))
        assert r.returncode == 0, r.stderr
        assert "Sidecar:" in r.stdout and "must accompany the HTML" in r.stdout
        assert "Bundle:" in r.stdout
        import zipfile
        names = zipfile.ZipFile(bundle).namelist()
        assert "review.html" in names
        assert any(n.startswith("review_pdfs/") and n.endswith(".html")
                   for n in names)

    def test_link_pdfs_has_no_sidecar_line(self, tmp_path):
        d = tmp_path / "record"
        d.mkdir()
        _write_pdf(d / "R1 - Complaint.pdf")
        r, out = _run_cli(tmp_path, [_fact("R1")], "--record-dir", str(d),
                          "--link-pdfs")
        assert r.returncode == 0, r.stderr
        assert "Sidecar:" not in r.stdout

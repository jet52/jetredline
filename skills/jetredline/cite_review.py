#!/usr/bin/env python3
"""
Citation Review Generator — produces a self-contained HTML file for
human review of citations in a judicial opinion or bench memo.

Left sidebar lists all citations with status indicators.
Main pane is split horizontally: full draft opinion on top (with paragraph
anchors and scrolling), cited authority on bottom (iframe for ND sources,
"open in new tab" for others).  Keyboard navigation: j/k to move between
citations, v/f/s to mark verified/flagged/skipped, n to focus notes field.

Usage:
    python3 cite_review.py --opinion opinion.md --refs-dir ~/refs \\
        --output cite-review.html --title "2026 ND 42, State v. Henderson"

    # Or pipe cite_check.py JSON directly:
    python3 cite_review.py --opinion opinion.md --cite-json cites.json \\
        --output cite-review.html
"""

import argparse
import base64
import html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

# ---------------------------------------------------------------------------
# Paragraph splitting
# ---------------------------------------------------------------------------

_PARA_RE = re.compile(
    r"(?:^|\n)"           # start of text or newline
    r"\s*"
    r"\[?¶\s*(\d+)\]?"    # ¶ marker with optional brackets, capture number
)

# Fallback: numbered paragraph markers like "1.  " (markdown ordered-list style)
_PARA_NUM_RE = re.compile(
    r"(?:^|\n)"           # start of text or newline
    r"\s*"
    r"(\d+)\.\s+"          # number, dot, whitespace
)


def _split_paragraphs(text: str) -> list[dict]:
    """Split opinion text into paragraphs keyed by ¶ number.

    Returns list of {"num": int|None, "text": str, "start": int, "end": int},
    where start/end span the paragraph (marker included) in ``text`` so
    character positions can be mapped to paragraphs.
    Supports both [¶ N] markers and numbered-list style (N.  text).
    """
    para_matches = list(_PARA_RE.finditer(text))
    num_matches = list(_PARA_NUM_RE.finditer(text))

    # Prefer numbered-list markers when they yield more paragraphs,
    # since ¶ may also appear in citation pinpoints (e.g., "2020 ND 30, ¶ 6")
    if num_matches and len(num_matches) > len(para_matches):
        matches = num_matches
    elif para_matches:
        matches = para_matches
    else:
        # No markers at all — treat entire text as one block
        return [{"num": None, "text": text.strip(), "start": 0, "end": len(text)}]

    paragraphs = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        paragraphs.append({"num": num, "text": text[start:end].strip(),
                           "start": m.start(), "end": end})
    return paragraphs


def _preprocess_like_scanner(text: str) -> str:
    """Apply jetcite's document preprocessing, or identity if unavailable.

    Citation positions in cite_check JSON index into
    preprocess_document_text(text); paragraph spans must be computed on the
    same text or position→paragraph mapping drifts.
    """
    try:
        from jetcite.cleanup import preprocess_document_text
    except ImportError:
        lib = Path(__file__).parent / "lib"
        if str(lib) not in sys.path:
            sys.path.insert(0, str(lib))
        try:
            from jetcite.cleanup import preprocess_document_text
        except ImportError:
            return text
    return preprocess_document_text(text)


def _locate_occurrence(pp_paragraphs: list[dict], pp_text: str,
                       position: int, cite_text: str) -> tuple[int | None, int]:
    """Map a citation's character position to (paragraph num, occurrence index).

    The occurrence index counts earlier appearances of cite_text within the
    same paragraph, so the UI can highlight the exact instance even when the
    identical string ("Id.", a repeated short cite) appears more than once.
    """
    for p in pp_paragraphs:
        if p["start"] <= position < p["end"]:
            segment = pp_text[p["start"]:position]
            return p["num"], segment.count(cite_text) if cite_text else 0
    return None, 0


def _find_paragraph(paragraphs: list[dict], cite_text: str) -> dict | None:
    """Find the paragraph containing a citation string."""
    for p in paragraphs:
        if cite_text in p["text"]:
            return p
    # Fallback: try normalized whitespace matching
    normalized = " ".join(cite_text.split())
    for p in paragraphs:
        if normalized in " ".join(p["text"].split()):
            return p
    return None


# ---------------------------------------------------------------------------
# Opinion to HTML
# ---------------------------------------------------------------------------

# Convert markdown links [text](url) to HTML after escaping.
# Matches the escaped form: [text](url) where brackets/parens are literal
# (not escaped by html.escape).
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def _escape_with_links(text: str) -> str:
    """HTML-escape text but render markdown links as clickable <a> tags."""
    # First convert links to placeholders, then escape the rest
    parts = []
    last = 0
    for m in _MD_LINK_RE.finditer(text):
        # Escape text before this link
        parts.append(html.escape(text[last:m.start()]))
        # Render link as HTML
        label = html.escape(m.group(1))
        url = html.escape(m.group(2))
        parts.append(
            f'<a class="draft-link" href="{url}" target="_blank" title="{url}">{label}</a>'
        )
        last = m.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def _format_spans_from_docx(
        docx_path, opinion_text: str,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Recover formatting spans from the original .docx.

    The extracted opinion markdown is plain text; italics (case names, Id.,
    signals, added emphasis) and block-quote indentation live only in the
    .docx. Walk the document's paragraphs, locate each paragraph's text
    inside ``opinion_text``, and return two absolute (start, end) span
    lists: (italic_spans, quote_spans). Quote paragraphs are detected by a
    quote-ish paragraph style (BlockQuote, Quote, IntenseQuote, BlockText)
    or a direct left indent ≥ 430 twips. Purely presentational — the
    citation scanner and position mapping never see these spans. Failures
    degrade to plain rendering, never an error.
    """
    import zipfile
    from defusedxml.minidom import parseString
    try:
        with zipfile.ZipFile(docx_path) as z:
            dom = parseString(z.read("word/document.xml").decode("utf-8"))
    except Exception as e:  # zip/XML/read errors — render without formatting
        print(f"Warning: could not read --docx for formatting ({e}); "
              "rendering plain.", file=sys.stderr)
        return [], []
    body = dom.getElementsByTagName("w:body")
    if not body:
        return [], []
    spans: list[list[int]] = []
    quote_spans: list[tuple[int, int]] = []
    cursor = 0
    for p in body[0].getElementsByTagName("w:p"):
        style_val, indent_left = "", 0
        ppr = next((c for c in p.childNodes if c.nodeName == "w:pPr"), None)
        if ppr is not None:
            ps = ppr.getElementsByTagName("w:pStyle")
            if ps:
                style_val = ps[0].getAttribute("w:val") or ""
            ind = ppr.getElementsByTagName("w:ind")
            if ind:
                for attr in ("w:left", "w:start"):
                    v = ind[0].getAttribute(attr)
                    if v:
                        try:
                            indent_left = max(indent_left, int(v))
                        except ValueError:
                            pass
        sv = style_val.lower()
        is_quote = ("quote" in sv or "blocktext" in sv or indent_left >= 430)
        parts: list[str] = []
        italic_runs: list[tuple[int, int]] = []
        pos = 0
        for r in p.getElementsByTagName("w:r"):
            anc, deleted = r.parentNode, False
            while anc is not None and anc is not p:
                if anc.nodeName == "w:del":
                    deleted = True
                    break
                anc = anc.parentNode
            if deleted:
                continue
            rtext = ""
            for child in r.childNodes:
                if child.nodeName == "w:t":
                    rtext += child.firstChild.nodeValue if child.firstChild else ""
                elif child.nodeName == "w:tab":
                    rtext += "\t"
            if not rtext:
                continue
            italic = False
            rpr = [c for c in r.childNodes if c.nodeName == "w:rPr"]
            if rpr:
                for i_el in rpr[0].getElementsByTagName("w:i"):
                    italic = i_el.getAttribute("w:val") not in ("0", "false", "none")
                    break
            if italic:
                italic_runs.append((pos, pos + len(rtext)))
            parts.append(rtext)
            pos += len(rtext)
        para_text = "".join(parts)
        stripped = para_text.strip()
        if not stripped:
            continue
        idx = opinion_text.find(stripped, cursor)
        if idx < 0:
            idx = opinion_text.find(stripped)
        if idx < 0:
            continue
        if is_quote:
            quote_spans.append((idx, idx + len(stripped)))
        if italic_runs:
            base = idx - (len(para_text) - len(para_text.lstrip()))
            for s, e in italic_runs:
                a = max(base + s, idx)
                b = min(base + e, idx + len(stripped))
                if b <= a:
                    continue
                if spans and spans[-1][1] == a:
                    spans[-1][1] = b
                else:
                    spans.append([a, b])
        cursor = idx + len(stripped)
    return [(s, e) for s, e in spans], quote_spans


def _render_with_italics(segment: str, abs_start: int,
                         italic_spans: list[tuple[int, int]] | None) -> str:
    """Escape a text segment, wrapping the italic spans it overlaps in <em>.

    ``abs_start`` is the segment's offset in the full opinion text, the
    coordinate system of ``italic_spans``.
    """
    if not italic_spans:
        return _escape_with_links(segment)
    end_abs = abs_start + len(segment)
    rel = sorted((max(s, abs_start) - abs_start, min(e, end_abs) - abs_start)
                 for s, e in italic_spans if s < end_abs and e > abs_start)
    if not rel:
        return _escape_with_links(segment)
    parts: list[str] = []
    cur = 0
    for s, e in rel:
        s = max(s, cur)
        if e <= s:
            continue
        parts.append(_escape_with_links(segment[cur:s]))
        parts.append("<em>" + _escape_with_links(segment[s:e]) + "</em>")
        cur = e
    parts.append(_escape_with_links(segment[cur:]))
    return "".join(parts)


def _render_body(body: str, body_start: int,
                 italic_spans: list[tuple[int, int]] | None,
                 quote_spans: list[tuple[int, int]] | None) -> str:
    """Render a paragraph body, wrapping quote spans in <blockquote>.

    Block-quote paragraphs sit between two ¶ markers, so _split_paragraphs
    absorbs them into the preceding paragraph's body; without the spans they
    render as one flowing paragraph. Everything stays inside the caller's
    .opinion-para div so anchors and highlighting are unaffected.
    """
    end_abs = body_start + len(body)
    q = sorted((max(s, body_start), min(e, end_abs))
               for s, e in (quote_spans or []) if s < end_abs and e > body_start)
    if not q:
        return _render_with_italics(body, body_start, italic_spans)
    parts: list[str] = []
    cur = body_start
    for s, e in q:
        s = max(s, cur)
        if e <= s:
            continue
        seg = body[cur - body_start:s - body_start]
        if seg.strip():
            parts.append(_render_with_italics(seg, cur, italic_spans))
        parts.append(
            '<blockquote class="opinion-quote">'
            + _render_with_italics(body[s - body_start:e - body_start],
                                   s, italic_spans)
            + '</blockquote>')
        cur = e
    tail = body[cur - body_start:]
    if tail.strip():
        parts.append(_render_with_italics(tail, cur, italic_spans))
    return "".join(parts)


# A section heading ("I", "II", ...) sits between two ¶ markers, so
# _split_paragraphs absorbs it into the tail of the preceding paragraph.
# Detected at render time and emitted as its own heading div instead.
_ROMAN_HEADING_RE = re.compile(r"\n\s*([IVXLCDM]{1,7})\s*$")


def _opinion_to_html(text: str, paragraphs: list[dict],
                     italic_spans: list[tuple[int, int]] | None = None,
                     quote_spans: list[tuple[int, int]] | None = None) -> str:
    """Convert opinion text to HTML fragment with paragraph anchors."""
    if not paragraphs or paragraphs[0]["num"] is None:
        return (f'<div class="opinion-text">'
                f'{_render_body(text, 0, italic_spans, quote_spans)}</div>')

    parts = []
    # Header text before the first paragraph marker.  _split_paragraphs
    # already chose the marker style and recorded the first marker's start.
    first_start = paragraphs[0]["start"]
    if first_start > 0:
        header = text[:first_start].strip()
        if header:
            hdr_start = text.find(header)
            parts.append(
                f'<div class="opinion-header">'
                f'{_render_with_italics(header, hdr_start, italic_spans)}</div>'
            )

    for p in paragraphs:
        pid = f'para-{p["num"]}' if p["num"] is not None else "para-0"
        body = p["text"]
        headings = []
        while True:
            m = _ROMAN_HEADING_RE.search(body)
            if not m:
                break
            headings.insert(0, m.group(1))
            body = body[:m.start()].rstrip()
        # Absolute offset of the (stripped) body within ``text`` — the
        # coordinate system the formatting spans are expressed in.
        body_start = text.find(body, p["start"]) if body else p["start"]
        escaped = _render_body(body, body_start, italic_spans, quote_spans)
        parts.append(
            f'<div class="opinion-para" id="{pid}">'
            f'<span class="para-marker">[¶{p["num"]}]</span> '
            f'{escaped}</div>'
        )
        for h in headings:
            parts.append(f'<div class="opinion-heading">{html.escape(h)}</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Citation data
# ---------------------------------------------------------------------------

def _disable_url_resolution():
    """Monkey-patch jetcite to skip all HTTP URL resolution."""
    saved = {}
    import jetcite.scanner as _scanner
    saved["scanner"] = _scanner.resolve_nd_opinion_urls
    _scanner.resolve_nd_opinion_urls = lambda cites: None
    from jetcite.sources import ndcourts as _ndcourts
    saved["ndcourts"] = _ndcourts.resolve_nd_opinion_url
    _ndcourts.resolve_nd_opinion_url = lambda year, number: None
    from jetcite.patterns import neutral as _neutral
    if hasattr(_neutral, "resolve_nd_opinion_url"):
        saved["neutral"] = _neutral.resolve_nd_opinion_url
        _neutral.resolve_nd_opinion_url = lambda year, number: None
    return saved


def _restore_url_resolution(saved: dict):
    """Undo _disable_url_resolution."""
    import jetcite.scanner as _scanner
    _scanner.resolve_nd_opinion_urls = saved["scanner"]
    from jetcite.sources import ndcourts as _ndcourts
    _ndcourts.resolve_nd_opinion_url = saved["ndcourts"]
    if "neutral" in saved:
        from jetcite.patterns import neutral as _neutral
        _neutral.resolve_nd_opinion_url = saved["neutral"]


def _load_citations(opinion_path: Path, cite_json_path: Path | None,
                    refs_dir: str, local_only: bool = False) -> list[dict]:
    """Load citation JSON — from file or by running cite_check.

    Default mode runs with cache_missing=True so citations are fetched
    and cached in refs_dir for future offline use.  --local-only skips
    all HTTP calls and uses whatever is already cached.
    """
    if cite_json_path and cite_json_path.exists():
        return json.loads(cite_json_path.read_text(encoding="utf-8"))

    # Import and run cite_check directly.
    # Always disable per-citation URL resolution during scanning — it's
    # slow and we derive direct URLs from local paths instead.  Only the
    # explicit caching step below needs web access.
    skill_dir = Path(__file__).parent
    sys.path.insert(0, str(skill_dir))
    # The vendored jetcite must be importable before _disable_url_resolution
    # touches jetcite modules (cite_check's own bootstrap runs too late).
    lib_dir = skill_dir / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(1, str(lib_dir))
    try:
        saved = _disable_url_resolution()

        from cite_check import scan_opinion
        text = opinion_path.read_text(encoding="utf-8")
        result = scan_opinion(text, refs_dir=refs_dir, cache_missing=False)

        _restore_url_resolution(saved)

        # Cache missing citations (unless local_only)
        if not local_only:
            from jetcite.cache import fetch_and_cache
            from jetcite import Citation

            _CACHEABLE = {
                "neutral_cite", "us_supreme_court",
                "federal_reporter", "regional_reporter",
            }
            to_cache = [
                e for e in result
                if not e.get("local_exists") and e.get("url")
                and e.get("cite_type") in _CACHEABLE
                and not e.get("is_repeat")
            ]
            if to_cache:
                # Build Citation objects for fetch_and_cache by re-scanning
                # with resolution disabled.  Only needed when something is
                # actually missing — on a warm refs dir this scan is skipped.
                saved2 = _disable_url_resolution()
                from jetcite import scan_text as _st
                cite_objs = {
                    c.normalized: c
                    for c in _st(text, refs_dir=Path(refs_dir).expanduser())
                }
                _restore_url_resolution(saved2)

                total = len(to_cache)
                print(f"  Caching {total} citation(s) to {refs_dir} ...",
                      file=sys.stderr)
                for i, entry in enumerate(to_cache, 1):
                    cite = cite_objs.get(entry["normalized"])
                    if cite is None:
                        continue
                    norm = entry["normalized"]
                    print(f"  [{i}/{total}] {norm} ...",
                          file=sys.stderr, end="", flush=True)
                    try:
                        cached = fetch_and_cache(
                            cite, refs_dir=Path(refs_dir).expanduser(),
                            timeout=15.0,
                        )
                        if cached is not None:
                            entry["local_path"] = str(cached)
                            entry["local_exists"] = True
                            print(" cached", file=sys.stderr)
                        else:
                            print(" not available", file=sys.stderr)
                    except Exception as exc:
                        print(f" error: {exc}", file=sys.stderr)

        return result
    finally:
        sys.path.pop(0)


# Pattern to extract neutral citation from opinion local paths
# e.g., ~/refs/opin/ND/2008/2008ND228.md → 2008ND228
_ND_LOCAL_PATH_RE = re.compile(r"/(\d{4}ND\d+)\.md$")


# Domains whose pages can be loaded in an iframe (no X-Frame-Options block).
# Used only when no embedded text is available for the citation.
_IFRAME_OK_DOMAINS = frozenset({
    "ndlegis.gov",          # N.D.C.C. chapter PDFs (#nameddest jumps to §),
                            # N.D.A.C. article PDFs
    "www.ndcourts.gov",     # opinion PDFs; court rules as HTML
    "ndcourts.gov",
    "ndconst.org",          # ND Constitution, article/section HTML
    "www.ndconst.org",
})

# Web-source provenance, keyed by host (leading "www." stripped). "official"
# is reserved for the government entity that issued or publishes the cited
# text; everything else is an unofficial copy and the badge says so. Unknown
# hosts default to unofficial.
#   host → (pane label, badge text, badge class, tooltip)
_URL_SOURCE_INFO = {
    "ndcourts.gov": ("ndcourts.gov", "official", "is-official",
                     "The court's own published text."),
    "ndlegis.gov": ("ndlegis.gov", "official", "is-official",
                    "The Legislative Branch's published text."),
    "supremecourt.gov": ("supremecourt.gov", "official", "is-official",
                         "The Supreme Court's own publication."),
    "govinfo.gov": ("govinfo.gov", "official", "is-official",
                    "U.S. Government Publishing Office text."),
    "ecfr.gov": ("eCFR", "official", "is-official",
                 "The Office of the Federal Register's eCFR."),
    "azleg.gov": ("azleg.gov", "official", "is-official",
                  "The Arizona Legislature's published text."),
    "apps.azsos.gov": ("azsos.gov", "official", "is-official",
                       "The Arizona Secretary of State's published text."),
    "azcourts.gov": ("azcourts.gov", "official", "is-official",
                     "The Arizona courts' published text."),
    "legis.iowa.gov": ("legis.iowa.gov", "official", "is-official",
                       "The Iowa Legislature's published text."),
    "tile.loc.gov": ("U.S. Reports (LOC)", "official scan", "is-official",
                     "Scan of the official U.S. Reports print, hosted by "
                     "the Library of Congress."),
    "constitution.congress.gov": ("congress.gov", "official", "is-official",
                                  "Constitution Annotated — the official "
                                  "U.S. Constitution text published by the "
                                  "Library of Congress for Congress."),
    "ndconst.org": ("ndconst.org", "unofficial", "",
                    "Compiled copy, not an official source. Verify against "
                    "the official text before relying on it."),
    "courtlistener.com": ("CourtListener", "unofficial", "",
                          "Free Law Project copy, not the official text."),
    "supreme.justia.com": ("Justia", "unofficial", "",
                           "Commercial republication, not the official text."),
    "law.cornell.edu": ("Cornell LII", "unofficial", "",
                        "Legal Information Institute copy, not the official "
                        "text."),
    "constitutioncenter.org": ("Constitution Center", "unofficial", "",
                               "National Constitution Center copy, not the "
                               "official text."),
}


def _url_source_info(url: str) -> tuple[str, str, str, str]:
    """(label, badge, badge_class, tooltip) for a web source URL's host."""
    host = (urlparse(url).netloc or "").lower()
    bare = host[4:] if host.startswith("www.") else host
    info = _URL_SOURCE_INFO.get(bare) or _URL_SOURCE_INFO.get(host)
    if info:
        return info
    return (bare or "Web source", "unofficial", "",
            "Unrecognized source — not verified as official.")


# PDF.js CDN version
_PDFJS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38"

# Self-contained PDF.js viewer HTML template.
# The search term is read from the URL hash (#search=...) so one viewer file
# can serve multiple pinpoints for the same opinion.
# Placeholder: __PDF_BASE64__
_PDFJS_VIEWER_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PDF Viewer</title>
<style>
html, body { margin:0; padding:0; background:#444; height:100%%; overflow:auto; }
#pages { display:flex; flex-direction:column; align-items:center; gap:4px; padding:4px; }
.pgwrap { position:relative; background:#fff; box-shadow:0 1px 4px rgba(0,0,0,.4); }
.pgwrap canvas { display:block; }
.pgnum { position:absolute; top:2px; left:4px; font:10px/1 system-ui,sans-serif;
  color:#999; z-index:2; }
.hl-box { position:absolute; background:rgba(253,230,138,.55);
  outline:2px solid #d4a017; border-radius:2px; z-index:1; pointer-events:none; }
.target-page { outline:3px solid #5b8def; outline-offset:2px; }
#loading { color:#ccc; font:14px/1.4 system-ui,sans-serif; text-align:center; padding:40px; }
#search-bar { position:fixed; top:0; right:0; background:rgba(0,0,0,.75);
  color:#eee; font:12px/1.4 system-ui,sans-serif; padding:6px 12px;
  border-radius:0 0 0 6px; z-index:10; }
</style>
</head>
<body>
<div id="search-bar"></div>
<div id="loading">Loading PDF\u2026</div>
<div id="pages"></div>
<script type="module">
import * as pdfjsLib from '%(cdn)s/pdf.min.mjs';
pdfjsLib.GlobalWorkerOptions.workerSrc = '%(cdn)s/pdf.worker.min.mjs';

const PDF_DATA = '__PDF_BASE64__';
// Hash params: #page=N (1-based landing page), #search=term (find the page
// containing the term), #hl=quote (highlight the quote; defaults to search).
const hashParams = new URLSearchParams(location.hash.slice(1));
const PAGE = parseInt(hashParams.get('page') || '0', 10) || 0;
const SEARCH = decodeURIComponent(hashParams.get('search') || '');
const HL = decodeURIComponent(hashParams.get('hl') || '') || SEARCH;

// Normalize for matching: straight/curly quotes, dash variants, collapsed
// whitespace \u2014 PDF extraction and record quotes rarely agree byte-for-byte.
function norm(s) {
  return s
    .replace(/[\\u2018\\u2019]/g, "'")
    .replace(/[\\u201C\\u201D]/g, '"')
    .replace(/[\\u2013\\u2014]/g, '-')
    .replace(/\\u00a0/g, ' ')
    .replace(/\\s+/g, ' ');
}

// norm() with a map from each normalized index back to the original index \u2014
// whitespace collapsing changes lengths, so a match found in normalized
// space must be translated before highlighting original-offset spans.
function normWithMap(s) {
  const fold = { '\\u2018': "'", '\\u2019': "'", '\\u201C': '"',
                 '\\u201D': '"', '\\u2013': '-', '\\u2014': '-' };
  let out = '', map = [], prevSpace = false;
  for (let i = 0; i < s.length; i++) {
    let c = fold[s[i]] || s[i];
    if (/\\s/.test(c)) {
      if (prevSpace) continue;
      c = ' ';
      prevSpace = true;
    } else {
      prevSpace = false;
    }
    out += c;
    map.push(i);
  }
  return { out, map };
}

// Find a candidate in normalized text. Bare paragraph-number candidates
// ("9.") only match at a word boundary so "19." and "2019." don't hit.
function findCand(hayNorm, cand) {
  const c = norm(cand);
  if (/^\\d+\\.$/.test(c)) {
    const m = new RegExp('(^|[\\\\s(\\\\[])' + c.replace('.', '\\\\.') + '\\\\s')
      .exec(hayNorm);
    return m ? m.index + m[1].length : -1;
  }
  return hayNorm.indexOf(c);
}

const raw = atob(PDF_DATA);
const bytes = new Uint8Array(raw.length);
for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

const bar = document.getElementById('search-bar');
window.addEventListener('unhandledrejection',
  e => { bar.textContent = 'Error: ' + (e.reason && e.reason.message || e.reason); });

try {
  const pdf = await pdfjsLib.getDocument({ data: bytes }).promise;
  document.getElementById('loading').remove();

  const container = document.getElementById('pages');
  const scale = 1.5;
  const wraps = [];        // page number -> wrapper div
  const rendered = new Set();

  // First page sizes the placeholders so scroll geometry is stable before
  // anything renders; per-page sizes correct themselves at render time.
  const first = await pdf.getPage(1);
  const firstVp = first.getViewport({ scale });

  for (let i = 1; i <= pdf.numPages; i++) {
    const wrap = document.createElement('div');
    wrap.className = 'pgwrap';
    wrap.id = 'page-' + i;
    wrap.style.width = firstVp.width + 'px';
    wrap.style.height = firstVp.height + 'px';
    wrap.innerHTML = '<span class="pgnum">' + i + '</span>';
    container.appendChild(wrap);
    wraps[i] = wrap;
  }

  async function renderPage(i, hlTerm) {
    if (rendered.has(i)) return wraps[i];
    rendered.add(i);
    const page = await pdf.getPage(i);
    const viewport = page.getViewport({ scale });
    const wrap = wraps[i];
    wrap.style.width = viewport.width + 'px';
    wrap.style.height = viewport.height + 'px';
    const canvas = document.createElement('canvas');
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    wrap.appendChild(canvas);
    await page.render({ canvasContext: canvas.getContext('2d'),
                        viewport }).promise;
    if (hlTerm) {
      // Overlay highlight boxes on every text item overlapping the match.
      // hlTerm may hold ||-separated candidates; first hit wins.
      const tc = await page.getTextContent();
      let joined = '', spans = [];
      tc.items.forEach(item => {
        spans.push({ start: joined.length, end: joined.length + item.str.length,
                     item });
        joined += item.str + ' ';
      });
      const nm = normWithMap(joined);
      let at = -1, matched = '';
      for (const cand of hlTerm.split('||')) {
        at = findCand(nm.out, cand);
        if (at > -1) { matched = cand; break; }
      }
      if (at > -1) {
        // Translate the normalized-space match back to original offsets.
        const nEnd = Math.min(at + norm(matched).length, nm.map.length) - 1;
        const end = nm.map[nEnd] + 1;
        at = nm.map[at];
        spans.forEach(sp => {
          if (sp.end <= at || sp.start >= end || !sp.item.str.trim()) return;
          const tx = pdfjsLib.Util.transform(viewport.transform,
                                             sp.item.transform);
          const h = Math.hypot(tx[2], tx[3]);
          const box = document.createElement('div');
          box.className = 'hl-box';
          box.style.left = tx[4] + 'px';
          box.style.top = (tx[5] - h) + 'px';
          box.style.width = (sp.item.width * scale) + 'px';
          box.style.height = (h * 1.15) + 'px';
          wrap.appendChild(box);
        });
        return wrap;
      }
    }
    return wrap;
  }

  // Lazy render pages as they scroll into view.
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) renderPage(Number(e.target.id.slice(5)), HL);
    });
  }, { rootMargin: '600px 0px' });
  wraps.forEach(w => { if (w) io.observe(w); });

  // Locate the target page: explicit #page wins; otherwise scan text (no
  // canvas render needed) for the search/highlight term.
  let targetPage = (PAGE >= 1 && PAGE <= pdf.numPages) ? PAGE : 0;
  const term = SEARCH || HL;
  if (!targetPage && term) {
    bar.textContent = 'Searching\\u2026';
    const cands = term.split('||');
    outer:
    for (let i = 1; i <= pdf.numPages; i++) {
      const tc = await (await pdf.getPage(i)).getTextContent();
      const text = norm(tc.items.map(item => item.str).join(' '));
      for (const cand of cands) {
        if (findCand(text, cand) > -1) { targetPage = i; break outer; }
      }
    }
    if (!targetPage) bar.textContent = 'Not found: ' + cands[0];
  }

  if (targetPage) {
    const wrap = await renderPage(targetPage, HL);
    wrap.classList.add('target-page');
    wrap.scrollIntoView({ block: 'start' });
    bar.textContent = 'Page ' + targetPage + ' of ' + pdf.numPages +
      (term ? ' \\u2014 ' + term.split('||')[0] : '');
    setTimeout(() => wrap.classList.remove('target-page'), 3000);
  } else {
    renderPage(1, HL);
  }
} catch (err) {
  const l = document.getElementById('loading');
  if (l) l.textContent = 'Error loading PDF: ' + err.message;
  else bar.textContent = 'Error: ' + err.message;
}
</script>
</body>
</html>
""" % {"cdn": _PDFJS_CDN}


def _nd_direct_url(local_path: str | None) -> str | None:
    """Derive an ndcourts.gov search URL from a local markdown path.

    If local_path matches the ND opinion pattern (e.g. 2017ND196.md),
    returns the search URL that reliably finds the opinion on ndcourts.gov.
    """
    if not local_path:
        return None
    m = _ND_LOCAL_PATH_RE.search(local_path)
    if not m:
        return None
    tag = m.group(1)  # e.g. "2017ND196"
    year_m = re.match(r"(\d{4})ND(\d+)", tag)
    if not year_m:
        return None
    return (
        f"https://www.ndcourts.gov/supreme-court/opinions"
        f"?cit1={year_m.group(1)}&citType=ND&cit2={year_m.group(2)}"
        f"&pageSize=10&sortOrder=1"
    )


# ---------------------------------------------------------------------------
# ndlaw.org — one reading surface for every ND authority
# ---------------------------------------------------------------------------

# ndlaw.org resolves any ND citation — opinions, N.D.C.C., the Constitution,
# court rules, the administrative code — from free text at /cite/<citation>.
# We hand it the citation rather than building canonical paths here: the server
# runs jetcite itself, and the canonical form is era-dependent for opinions
# (a post-1997 case answers to its neutral cite, not its N.W.2d parallel), so
# a URL grammar duplicated on this side would drift out of sync.
_NDLAW_DEFAULT_BASE = "https://ndlaw.org"


def _ndlaw_url(citation: str | None, pin_anchor: str | None,
               base: str = _NDLAW_DEFAULT_BASE,
               page_anchor: str | None = None) -> str | None:
    """Resolver URL for an ND citation, with the pinpoint as a fragment.

    The fragment survives the resolver's 301: a browser reattaches the
    original fragment when the redirect target carries none (RFC 7231
    §7.1.2), so ``/cite/2020%20ND%2030#p14`` lands on ¶ 14 of ``/2020ND30``.
    Verified in Chrome against a local instance (2026-07-31): final URL
    ``/2020ND30#p14``, scrolled to the ``[¶14]`` marker.

    Only opinions get a fragment — ``#p{n}`` matches the ¶ anchors ndlaw
    renders in opinion bodies, and ``#star{n}`` matches the star-page anchors
    it renders for pre-neutral-cite opinions (page pins like "at 776").
    Provision pages have no subsection anchors, and the resolver drops the
    subdivision, so a fragment there would scroll nowhere.
    """
    if not citation:
        return None
    url = f"{base.rstrip('/')}/cite/{quote(citation, safe='')}"
    if pin_anchor:
        url += f"#p{pin_anchor}"
    elif page_anchor:
        url += f"#star{page_anchor}"
    return url


def _ndlaw_eligible(cite: dict, meta: dict) -> bool:
    """Whether ndlaw.org can serve this citation.

    Two signals, both positive proof — never a guess. An ineligible citation
    simply keeps the old panes; a wrong guess would iframe ndlaw's 404 page in
    place of the authority, which is worse than not offering the copy.

    1. ``jurisdiction == "nd"`` — ND neutral cites and all four provision
       corpora (N.D.C.C., N.D.A.C., Constitution, court rules).
    2. An ``ndlaw_export`` metadata entry, which exists only for citations
       resolved against the ND corpus.

    Signal 2 is what covers pre-1997 ND cases: they are cited to N.W. or
    N.W.2d, which jetcite classifies as a regional reporter with jurisdiction
    ``us`` — correct, the reporter is regional. The reporter alone cannot
    stand in, because N.W.2d also carries six other states. A refs path cannot
    stand in either: ``~/refs/opin/`` holds every reporter, federal and state
    alike (``opin/US/``, ``opin/F3d/``, ``opin/Cal2d/``), so it says nothing
    about jurisdiction until the three-tier restructure lands.
    """
    return cite.get("jurisdiction") == "nd" or bool(meta)


_ND_OPINION_PDF_RE = re.compile(r"/supreme-court/opinions/\d+$")


def _needs_pdfjs_viewer(url: str, pinpoint: str | None) -> bool:
    """Check if a citation URL should use the PDF.js viewer with search."""
    if not url or not pinpoint:
        return False
    # Already has a named destination — browser handles it
    if "#nameddest=" in url:
        return False
    # Only direct ndcourts.gov opinion PDFs — a search URL (?cit1=...) serves
    # HTML, which would break the PDF.js viewer
    parsed = urlparse(url)
    return (parsed.netloc in ("www.ndcourts.gov", "ndcourts.gov")
            and bool(_ND_OPINION_PDF_RE.search(parsed.path)))


def _pinpoint_search_term(pinpoint: str | None) -> str:
    """Convert a pinpoint like '¶ 15' to a PDF search term like '[¶15]'.

    Page pins ("at 627") return no term: the ndcourts PDFs this searches are
    ¶-numbered opinions, and searching a bare page number would land on
    arbitrary digits.
    """
    if not pinpoint or "¶" not in pinpoint:
        return ""
    m = re.search(r"\d+", pinpoint)
    if not m:
        return ""
    return f"[¶{m.group(0)}]"


def _download_pdf(url: str, dest: Path, timeout: int = 15) -> bool:
    """Download a PDF to dest. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jetredline-cite-review/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"  Warning: could not download {url}: {e}", file=sys.stderr)
        return False


def _read_local_markdown(local_path: str | None) -> str | None:
    """Read the full markdown file for a citation. Returns None if unavailable."""
    if not local_path:
        return None
    p = Path(local_path).expanduser()
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text if text.strip() else None


# Lightweight markdown → HTML for legal texts
_MD_HEADING = re.compile(r"^(#{1,4})\s+(.*)", re.MULTILINE)
_MD_PARA_MARKER = re.compile(r"\[¶\s*(\d+)\]")
# West star pagination in cached opinion markdown: [*774] marks where
# reporter page 774 begins.
_MD_STAR_PAGE = re.compile(r"\[\*(\d+)\]")
_MD_SECTION = re.compile(r"§\s*([\d\w.-]+)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_BLOCKQUOTE_LINE = re.compile(r"^>\s?(.*)", re.MULTILINE)


_FM_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")


def _split_frontmatter(md: str) -> tuple[dict, str]:
    """Split a leading YAML frontmatter block off corpus-exported markdown.

    Parses only the simple subset the ndlaw corpus emits: top-level
    ``key: value`` scalars (optionally double-quoted) and one-level lists
    of scalars. Returns ({}, md) untouched when no block is present or a
    line doesn't parse — never guesses.
    """
    lines = md.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, md
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, md
    meta: dict = {}
    key = None
    for raw in lines[1:end]:
        item = raw.strip()
        if not item:
            continue
        if item.startswith("- ") and key is not None and isinstance(meta.get(key), list):
            meta[key].append(item[2:].strip().strip('"'))
            continue
        m = _FM_KEY_RE.match(item)
        if not m:
            return {}, md
        key = m.group(1)
        val = m.group(2).strip().strip('"')
        # A bare "key:" introduces a list; a valued line is a scalar.
        meta[key] = val if val else []
    return meta, "\n".join(lines[end + 1:])


def _frontmatter_card(meta: dict) -> str:
    """Render parsed frontmatter as a metadata header card for the source pane."""
    title = meta.get("title") or meta.get("title_full")
    if not title:
        return ""
    parts = ['<div class="src-meta-card">',
             f'<div class="src-meta-title">{html.escape(str(title))}</div>']
    full = meta.get("title_full")
    if full and full != title:
        parts.append(f'<div class="src-meta-line">{html.escape(str(full))}</div>')
    court_line = " · ".join(
        str(v) for v in (meta.get("court"), meta.get("date_filed"),
                         meta.get("docket_number")) if v)
    if court_line:
        parts.append(f'<div class="src-meta-line">{html.escape(court_line)}</div>')
    cites = meta.get("citations")
    if isinstance(cites, str):
        cites = [cites] if cites else []
    if cites:
        parts.append('<div class="src-meta-line">'
                     + html.escape(" · ".join(str(c) for c in cites)) + '</div>')
    judges = meta.get("judges")
    if judges:
        parts.append('<div class="src-meta-line">Judges: '
                     + html.escape(str(judges)) + '</div>')
    parts.append('</div>')
    return "\n".join(parts)


def _md_to_html(md: str) -> str:
    """Convert legal markdown to HTML with anchors for pinpoint navigation.

    A leading YAML frontmatter block (ndlaw corpus court-archive exports)
    renders as a metadata header card instead of literal text.
    """
    frontmatter, md = _split_frontmatter(md)
    lines = md.split("\n")
    out: list[str] = []
    in_blockquote = False
    in_para = False

    def _inline(text: str) -> str:
        text = html.escape(text)
        # Star-page markers first, with the asterisk written as &#42; so the
        # bold/italic passes can't pair asterisks across two markers.
        text = _MD_STAR_PAGE.sub(
            r'<span class="star-anchor" id="pg-\1">[&#42;\1]</span>', text
        )
        text = _MD_BOLD.sub(r"<strong>\1</strong>", text)
        text = _MD_ITALIC.sub(r"<em>\1</em>", text)
        # Add anchors for ¶ markers
        text = _MD_PARA_MARKER.sub(
            r'<span class="para-anchor" id="pin-\1">[¶\1]</span>', text
        )
        # Add anchors for § section numbers
        text = _MD_SECTION.sub(
            lambda m: (
                f'<span class="sec-anchor" id="sec-{m.group(1).rstrip(".")}">'
                f'§\u00a0{m.group(1)}</span>'
            ),
            text,
        )
        return text

    for line in lines:
        stripped = line.strip()

        # Headings
        hm = _MD_HEADING.match(stripped)
        if hm:
            if in_para:
                out.append("</p>")
                in_para = False
            if in_blockquote:
                out.append("</blockquote>")
                in_blockquote = False
            level = min(len(hm.group(1)), 4)
            out.append(f"<h{level}>{_inline(hm.group(2))}</h{level}>")
            continue

        # Blockquote lines
        bqm = _MD_BLOCKQUOTE_LINE.match(line)
        if bqm:
            if in_para:
                out.append("</p>")
                in_para = False
            if not in_blockquote:
                out.append("<blockquote>")
                in_blockquote = True
            out.append(_inline(bqm.group(1)) + "<br>")
            continue

        # End blockquote on non-quote line
        if in_blockquote and not bqm:
            out.append("</blockquote>")
            in_blockquote = False

        # Blank line → end paragraph
        if not stripped:
            if in_para:
                out.append("</p>")
                in_para = False
            continue

        # Regular text → paragraph
        if not in_para:
            out.append("<p>")
            in_para = True
        else:
            out.append(" ")
        out.append(_inline(stripped))

    if in_para:
        out.append("</p>")
    if in_blockquote:
        out.append("</blockquote>")

    card = _frontmatter_card(frontmatter)
    return (card + "\n" if card else "") + "\n".join(out)


def _generate_pdfjs_viewers(enriched: list[dict], output_path: Path,
                            local_only: bool = False) -> dict[str, str]:
    """Download opinion PDFs and generate self-contained PDF.js viewer HTML files.

    Returns a mapping of original URL → relative path to viewer HTML file.
    When local_only is True, skips all web downloads.
    """
    viewers: dict[str, str] = {}
    if local_only:
        return viewers

    urls_seen: set[str] = set()

    # Collect unique URLs needing viewers
    needs_viewer = []
    for c in enriched:
        url = c.get("url") or ""
        if url in urls_seen:
            continue
        # Skip if we already have local text for this citation
        if c.get("local_exists"):
            continue
        if _needs_pdfjs_viewer(url, c.get("pinpoint")):
            urls_seen.add(url)
            needs_viewer.append(c)

    if not needs_viewer:
        return viewers

    pdf_dir = output_path.parent / (output_path.stem + "_pdfs")
    pdf_dir.mkdir(exist_ok=True)

    for c in needs_viewer:
        url = c["url"]
        normalized = c.get("normalized", "opinion").replace(" ", "")
        pdf_file = pdf_dir / f"{normalized}.pdf"

        print(f"  Downloading {url} ...", file=sys.stderr)
        if not _download_pdf(url, pdf_file):
            continue

        pdf_b64 = base64.b64encode(pdf_file.read_bytes()).decode("ascii")

        viewer_html = _PDFJS_VIEWER_TEMPLATE.replace("__PDF_BASE64__", pdf_b64)

        viewer_file = pdf_dir / f"{normalized}.html"
        viewer_file.write_text(viewer_html, encoding="utf-8")

        # Clean up the intermediate PDF file
        pdf_file.unlink(missing_ok=True)

        # Relative path from output HTML to viewer
        viewers[url] = str(viewer_file.relative_to(output_path.parent))

    return viewers


# ---------------------------------------------------------------------------
# Factual-assertion review (Pass 4 facts ledger) and local-PDF sources
# ---------------------------------------------------------------------------

def _normalize_result(raw: str | None) -> str:
    """Collapse Pass 4 result phrasings to verified/discrepancy/unverified."""
    s = (raw or "").strip().lower()
    if "discrep" in s:
        return "discrepancy"
    if s.startswith("verif"):
        return "verified"
    return "unverified"


def _load_facts(path: Path) -> list[dict]:
    """Load and normalize the Pass 4 facts ledger.

    Tolerates either a bare array or {"claims": [...]}. Each claim keeps its
    raw result phrasing in result_label; result is the normalized enum.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    claims = raw.get("claims") if isinstance(raw, dict) else raw
    facts = []
    for c in claims or []:
        if not isinstance(c, dict) or not c.get("claim"):
            continue
        sources = [s for s in c.get("sources") or [] if isinstance(s, dict)]
        facts.append({
            "para": str(c.get("para") or "").strip(),
            "claim": str(c["claim"]).strip(),
            "draft_quote": (c.get("draft_quote") or "").strip(),
            "result": _normalize_result(c.get("result")),
            "result_label": (c.get("result") or "").strip() or "unverified",
            "note": (c.get("note") or "").strip(),
            "sources": sources,
        })
    return facts


def _load_manifest(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []
    except (OSError, ValueError):
        return []


_RECORD_ITEM_RE = re.compile(r"^R\.?\s*(\d+)$", re.IGNORECASE)


def _resolve_fact_source(src: dict, record_dir: Path | None,
                         manifest: list[dict], base_dir: Path,
                         manifest_dir: Path | None = None) -> Path | None:
    """Resolve one facts-ledger source ref to a PDF on disk.

    Order: explicit file hint -> record item (R243 -> 'R243 - *.pdf' in the
    record dir) -> docket number via the manifest -> name fragment matched
    against manifest filenames, then against PDFs in the project dir.
    Manifest filenames resolve against the manifest's own directory.
    """
    manifest_dir = manifest_dir or base_dir
    hint = src.get("file")
    if hint:
        p = Path(hint)
        if not p.is_absolute():
            p = base_dir / p
        if p.exists():
            return p

    item = (src.get("item") or src.get("raw") or "").strip()
    m = _RECORD_ITEM_RE.match(item.split(",")[0].strip())
    if m and record_dir and record_dir.is_dir():
        # 'R243 - ' prefix: the space-dash boundary keeps R24 from matching R243
        matches = sorted(record_dir.glob(f"R{m.group(1)} - *.pdf"))
        if matches:
            return matches[0]

    token = item.split(",")[0].split("¶")[0].strip().rstrip(".")
    if token.isdigit() and manifest:
        want = int(token)
        for e in manifest:
            if e.get("docketId") == want and e.get("filename"):
                p = manifest_dir / e["filename"]
                if p.exists():
                    return p

    frag = re.sub(r"[^A-Za-z0-9-]", "", token.replace(" ", "-"))
    if len(frag) >= 4:
        for e in manifest:
            fn = e.get("filename") or ""
            if frag.lower() in re.sub(r"[^A-Za-z0-9-]", "", fn).lower():
                p = manifest_dir / fn
                if p.exists():
                    return p
        for p in sorted(base_dir.glob("*.pdf")):
            if frag.lower() in re.sub(r"[^A-Za-z0-9-]", "", p.name).lower():
                return p
    return None


def _viewer_name(pdf_path: Path, taken: set[str]) -> str:
    """Stable, filesystem-safe sidecar name for a source PDF's viewer."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf_path.stem).strip("_") or "doc"
    name = stem[:60]
    n = 1
    while name in taken:
        n += 1
        name = f"{stem[:56]}~{n}"
    taken.add(name)
    return name


def _generate_local_pdf_viewers(pdf_paths: list[Path], output_path: Path,
                                link_pdfs: bool = False) -> dict[str, str]:
    """Map each unique source PDF to an embeddable URL.

    Default: a base64 PDF.js sidecar viewer (quote highlighting, exact-page
    landing, any browser). --link-pdfs: a relative file URL for a native
    iframe — zero-copy, but no quote highlight and #page support varies.
    Keys are absolute path strings.
    """
    out: dict[str, str] = {}
    uniq: list[Path] = []
    for p in pdf_paths:
        rp = p.resolve()
        if str(rp) not in out and rp not in uniq:
            uniq.append(rp)

    if link_pdfs:
        for p in uniq:
            try:
                rel = os.path.relpath(p, output_path.parent.resolve())
            except ValueError:  # different drive (Windows)
                rel = p.as_uri()
            out[str(p)] = rel.replace(os.sep, "/")
        return out

    pdf_dir = output_path.parent / (output_path.stem + "_pdfs")
    taken: set[str] = set()
    for p in uniq:
        try:
            pdf_b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        except OSError as e:
            print(f"  Warning: could not read {p}: {e}", file=sys.stderr)
            continue
        pdf_dir.mkdir(exist_ok=True)
        viewer_file = pdf_dir / (_viewer_name(p, taken) + ".html")
        viewer_file.write_text(
            _PDFJS_VIEWER_TEMPLATE.replace("__PDF_BASE64__", pdf_b64),
            encoding="utf-8")
        out[str(p)] = str(viewer_file.relative_to(output_path.parent))
    return out


def _fact_source_hash(src: dict) -> str:
    """Build the viewer hash fragment for a fact source ref."""
    parts = []
    page = src.get("page")
    if isinstance(page, int) and page > 0:
        parts.append(f"page={page}")
    qt = (src.get("quote") or "").strip()
    para_pin = (src.get("para_pin") or "").strip()
    if qt:
        parts.append("hl=" + quote(qt[:200]))
    elif para_pin:
        m = re.search(r"\d+", para_pin)
        if m:
            # Candidate forms tried in order — court PDFs number paragraphs
            # as "¶ 9", "¶9", "[¶9]", or plain "9." depending on the drafter.
            n = m.group(0)
            parts.append("search=" + quote(f"¶ {n}||¶{n}||[¶{n}]||{n}."))
    return ("#" + "&".join(parts)) if parts else ""

_CSS = """\
:root {
  --bg: #1a1a2e;
  --surface: #222244;
  --surface-alt: #2a2a4a;
  --border: #3a3a5c;
  --text: #e0e0e8;
  --text-muted: #8888aa;
  --accent: #5b8def;
  --accent-dim: #3a5a9a;
  --verified: #4a9;
  --flagged: #d68;
  --skipped: #888;
  --highlight: #5b8def22;
  --cite-hl: #e8b93166;
  --cite-hl-border: #d4a017;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: 'SF Mono','Cascadia Code','JetBrains Mono',monospace;
  background: var(--bg); color: var(--text);
  height: 100vh; display: flex; flex-direction: column; overflow: hidden;
}
header {
  display:flex; align-items:center; justify-content:space-between;
  padding:10px 20px; background:var(--surface);
  border-bottom:1px solid var(--border); flex-shrink:0;
}
header h1 { font-size:14px; font-weight:600; }
.header-meta {
  display:flex; align-items:center; gap:20px;
  font-size:12px; color:var(--text-muted);
}
.progress-bar {
  width:120px; height:6px; background:var(--border);
  border-radius:3px; overflow:hidden;
}
.progress-fill {
  height:100%; width:0%; background:var(--accent);
  border-radius:3px; transition:width 0.3s ease;
}
.counter {
  font-variant-numeric:tabular-nums; color:var(--accent); font-weight:600;
}
main { display:flex; flex:1; overflow:hidden; }

/* Sidebar */
.sidebar {
  width:280px; background:var(--surface);
  border-right:1px solid var(--border);
  display:flex; flex-direction:column; flex-shrink:0;
}
.sidebar-header {
  padding:12px 16px; font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:0.05em;
  color:var(--text-muted); border-bottom:1px solid var(--border);
}
.cite-list { flex:1; overflow-y:auto; padding:4px 0; }
.cite-item {
  padding:8px 16px; cursor:pointer;
  border-left:3px solid transparent;
  display:flex; align-items:center; gap:8px;
  font-size:12px; transition:background 0.15s;
}
.cite-item:hover { background:var(--surface-alt); }
.cite-item.active {
  background:var(--highlight);
  border-left-color:var(--accent);
}
.cite-item .dot {
  width:8px; height:8px; border-radius:50%;
  flex-shrink:0; background:var(--border);
}
.cite-item .dot.verified { background:var(--verified); }
.cite-item .dot.flagged { background:var(--flagged); }
.cite-item .dot.skipped { background:var(--skipped); }
.cite-item .lbl {
  flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.cite-item .typ {
  font-size:10px; color:var(--text-muted); flex-shrink:0;
}
.cite-item .via {
  font-size:9px; flex-shrink:0; padding:1px 5px; border-radius:3px;
  border:1px solid var(--border); color:var(--text-muted);
  text-transform:lowercase; letter-spacing:.02em;
}
/* MCP/local tiers are authoritative; web is the weaker fallback. Distinguished
   by border weight + label text (not color alone) for colorblind safety. */
.cite-item .via.mcp, .cite-group-hdr .via.mcp { border-color:var(--text-muted); font-weight:600; }
.cite-item .via.web, .cite-group-hdr .via.web { border-style:dashed; }

/* Authority group headers: one per cited case; occurrences nest below */
.cite-group-hdr {
  display:flex; align-items:baseline; gap:6px; cursor:pointer;
  padding:9px 12px 5px; margin-top:6px;
  border-top:1px solid var(--border);
  font-size:11px;
}
.cite-group-hdr:first-child { border-top:none; margin-top:0; }
.cite-group-hdr:hover { background:var(--surface-alt); }
.cite-group-hdr .gname {
  font-weight:600; color:var(--text);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}
.cite-group-hdr .gcite {
  color:var(--text-muted); flex-shrink:0;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  max-width:40%;
}
.cite-group-hdr .via {
  font-size:9px; flex-shrink:0; padding:1px 5px; border-radius:3px;
  border:1px solid var(--border); color:var(--text-muted);
  text-transform:lowercase; letter-spacing:.02em;
}
.cite-group-hdr .glink {
  flex-shrink:0; color:var(--accent); text-decoration:none; font-size:12px;
}
.cite-group-hdr .gcount {
  margin-left:auto; flex-shrink:0;
  font-size:9px; color:var(--text-muted);
  border:1px solid var(--border); border-radius:8px; padding:0 6px;
}
.cite-item { padding-left:26px; }
.cite-item .ploc {
  font-size:10px; color:var(--text-muted); flex-shrink:0;
}
.cite-item .pin-warn { color:var(--flagged); }

/* Content */
.content { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.split { flex:1; display:flex; flex-direction:column; overflow:hidden; }

/* Draft pane */
.pane-draft {
  flex:0 0 40%; display:flex; flex-direction:column;
  overflow:hidden; min-height:120px;
}
.pane-hdr {
  padding:8px 20px; background:var(--surface);
  border-bottom:1px solid var(--border);
  display:flex; align-items:center; justify-content:space-between;
  flex-shrink:0;
}
.pane-hdr .ptitle {
  font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:0.05em; color:var(--text-muted);
}
.pane-hdr .ctitle { font-size:13px; font-weight:600; color:var(--text); }
.pane-hdr .curl {
  font-size:11px; color:var(--accent); text-decoration:none;
  max-width:50%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.pane-hdr .curl:hover { text-decoration:underline; }

.draft-body {
  flex:1; padding:16px 24px; overflow-y:auto;
  line-height:1.7; font-family:'Charter','Georgia',serif; font-size:15px;
}
.opinion-header {
  margin-bottom:20px; padding:12px 16px;
  text-align:center; font-style:italic;
  color:var(--text-muted); white-space:pre-line;
  border-bottom:1px solid var(--border);
}
.opinion-para {
  padding:8px 16px; margin:2px 0;
  border-left:3px solid transparent;
  border-radius:4px;
  transition:background 0.2s, border-color 0.2s;
}
.opinion-para.active-para {
  background:var(--highlight);
  border-left-color:var(--accent);
}
.para-marker {
  color:var(--accent); font-weight:600;
  font-family:'SF Mono','Cascadia Code',monospace; font-size:12px;
}
.opinion-heading {
  text-align:center; font-weight:600;
  margin:14px 0 4px; padding:0 16px;
}
.opinion-quote {
  margin:10px 32px; padding:0;
  font-size:14px;
}
.draft-link {
  color:var(--text); text-decoration:none;
  border-bottom:1px dotted var(--text-muted);
}
.draft-link:hover { color:var(--accent); border-bottom-color:var(--accent); }
.cite-hl {
  background:var(--cite-hl); padding:2px 5px;
  border-radius:3px; border-bottom:2px solid var(--cite-hl-border);
  animation: cite-flash 0.6s ease-out;
}
@keyframes cite-flash {
  0% { background:#e8b93100; }
  30% { background:#e8b931aa; }
  100% { background:var(--cite-hl); }
}

/* Resize handle */
.resize-handle {
  height:5px; background:var(--accent-dim); cursor:row-resize;
  flex-shrink:0; position:relative;
}
.resize-handle::after {
  content:''; position:absolute; left:50%; top:50%;
  transform:translate(-50%,-50%);
  width:32px; height:2px; background:var(--accent); border-radius:1px;
}

/* Source pane */
.pane-src {
  flex:1; display:flex; flex-direction:column; overflow:hidden;
  min-height:120px;
}
.pane-src iframe {
  flex:1; border:none; background:#fff; width:100%;
}
/* ndlaw is a compiled copy, not an official source — say so in the pane,
   not only in a footer the reviewer scrolls past. Amber, and paired with the
   word "unofficial", so it reads the same to a red-green colorblind viewer. */
.unofficial-badge, .official-badge {
  margin-left:auto; flex:none;
  font-family:'SF Mono',monospace; font-size:10px; letter-spacing:.04em;
  text-transform:uppercase; cursor:help;
  border-radius:3px; padding:2px 6px;
}
.unofficial-badge {
  color:#8a6d1a; background:#f5edd2; border:1px solid #e3d49a;
}
/* Blue against the amber above — distinguishable without relying on a
   red/green contrast, and the words differ regardless of color. */
.official-badge {
  color:#1a4d8a; background:#dde8f5; border:1px solid #9ab8dc;
}
.pane-src .no-url, .pane-src .no-local {
  flex:1; display:flex; flex-direction:column;
  align-items:center; justify-content:center;
  color:var(--text-muted); font-size:13px; gap:16px;
}
.passage-box {
  flex:1; overflow-y:auto; padding:20px 28px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size:15px; line-height:1.7;
  background:#fdfcf8; color:#222;
}
.passage-box .passage-caption {
  font-family:'SF Mono',monospace; font-size:11px;
  color:#8a6d1a; background:#f5edd2; border:1px solid #e3d49a;
  border-radius:4px; padding:6px 10px; margin-bottom:14px;
}
.passage-box blockquote {
  margin:0; padding-left:14px; border-left:3px solid #d4a017;
  white-space:pre-wrap;
}
.open-tab-btn {
  display:inline-block; padding:10px 20px;
  font-size:13px; color:#fff; background:var(--accent);
  border-radius:6px; text-decoration:none;
  font-family:'SF Mono',monospace; font-weight:600;
  transition:background 0.15s;
}
.open-tab-btn:hover { background:var(--accent-dim); }
.fallback-link {
  position:absolute; bottom:8px; right:12px;
  font-size:11px; color:var(--accent); background:var(--surface);
  padding:4px 10px; border-radius:4px;
  border:1px solid var(--border); text-decoration:none;
  font-family:'SF Mono',monospace; z-index:10;
}
.fallback-link:hover { background:var(--accent-dim); color:#fff; }
/* The source pane's header label IS the view switcher: it names the view you
   are looking at and cycles on click, with that view's own URL to its right.
   Chips floating over the body could not do this — they had to name the view
   you were NOT in, and they overlapped the PDF viewer's own controls. */
.src-mode-wrap { display:flex; align-items:center; gap:8px; min-width:0; }
.src-mode {
  font:inherit; font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:0.05em; color:var(--text-muted);
  background:none; border:1px solid transparent; border-radius:4px;
  padding:3px 8px; margin:-3px -8px;
}
.src-mode.cycles { cursor:pointer; }
.src-mode.cycles:hover {
  color:var(--text); border-color:var(--border); background:var(--bg);
}
.src-mode.cycles::after { content:' \\21bb'; opacity:.55; }
/* ndlaw.org is a domain, not a label — show it as written, per its own
   spelling, rather than shouting it in caps like the other two states.
   is-domain does the same for the web-source modes whose labels are
   domains or citation forms (ndcourts.gov, U.S. Reports (LOC)). */
.src-mode.mode-ndlaw, .src-mode.is-domain { text-transform:none; letter-spacing:0; }
.src-badge {
  font-family:'SF Mono',monospace; font-size:10px; letter-spacing:.04em;
  text-transform:uppercase; cursor:help; flex:none;
  border-radius:3px; padding:2px 6px;
  color:#8a6d1a; background:#f5edd2; border:1px solid #e3d49a;
}
.src-badge.is-official { color:#1a4d8a; background:#dde8f5; border-color:#9ab8dc; }
.src-badge.is-offline  { color:#4a4a4a; background:#e8e8e6; border-color:#c9c9c5; }
.local-ref-html {
  flex:1; overflow-y:auto; padding:24px 36px;
  font-family:'Charter','Georgia','Times New Roman',serif; font-size:17px;
  line-height:1.85; color:#1a1a1a; background:#fdfdf8;
  margin:0;
}
.src-meta-card {
  font-family:system-ui,sans-serif;
  background:#f2f1e8; border:1px solid #ddd9c4; border-radius:6px;
  padding:12px 16px; margin-bottom:20px;
}
.src-meta-card .src-meta-title {
  font-size:16px; font-weight:650; color:#1a1a2e; margin-bottom:2px;
}
.src-meta-card .src-meta-line {
  font-size:12px; color:#555; line-height:1.6;
}
.local-ref-html h1, .local-ref-html h2, .local-ref-html h3, .local-ref-html h4 {
  color:#1a1a2e; margin:1.4em 0 0.5em; font-family:system-ui,sans-serif;
}
.local-ref-html h1 { font-size:22px; }
.local-ref-html h2 { font-size:19px; }
.local-ref-html h3 { font-size:17px; }
.local-ref-html p { margin:0.7em 0; }
.local-ref-html blockquote {
  border-left:3px solid #b0b0c0; margin:1em 0; padding:6px 20px;
  color:#333; background:#f4f4f0; font-size:16px;
}
.local-ref-html .para-anchor {
  font-weight:700; color:#2255aa; scroll-margin-top:40px;
}
.local-ref-html .sec-anchor {
  font-weight:600; color:#2255aa; scroll-margin-top:40px;
}
.local-ref-html .star-anchor {
  font-weight:700; color:#8a6d1a; scroll-margin-top:40px;
}
.local-ref-html .pinpoint-active {
  background:#fde68a; padding:3px 8px; border-radius:4px;
  outline:2px solid #d4a017; outline-offset:3px;
  animation: pinpoint-pulse 1.5s ease-in-out;
}
@keyframes pinpoint-pulse {
  0% { outline-color:#d4a017; outline-offset:3px; }
  50% { outline-color:#e8c840; outline-offset:6px; }
  100% { outline-color:#d4a017; outline-offset:3px; }
}
.search-hint {
  position:absolute; bottom:8px; left:12px;
  font-size:11px; color:var(--text-muted); background:var(--surface);
  padding:4px 10px; border-radius:4px;
  border:1px solid var(--border);
  font-family:'SF Mono',monospace; z-index:10;
}
.search-hint code { color:var(--accent); }

/* Action bar */
.action-bar {
  padding:10px 20px; background:var(--surface);
  border-top:1px solid var(--border);
  display:flex; align-items:center; gap:16px;
  flex-shrink:0;
}
.actions { display:flex; gap:8px; }
.btn {
  padding:6px 14px; border:1px solid var(--border); border-radius:4px;
  background:var(--surface-alt); color:var(--text);
  font-family:inherit; font-size:12px; cursor:pointer;
  transition:all 0.15s; display:flex; align-items:center; gap:6px;
}
.btn:hover { border-color:var(--accent); }
.btn.v-btn.active { background:#4a92; border-color:var(--verified); color:var(--verified); }
.btn.f-btn.active { background:#d682; border-color:var(--flagged); color:var(--flagged); }
.btn.s-btn.active { background:#8882; border-color:var(--skipped); color:var(--skipped); }
.notes-input {
  flex:1; padding:6px 12px; background:var(--bg);
  border:1px solid var(--border); border-radius:4px;
  color:var(--text); font-family:inherit; font-size:12px;
  min-width:0;
}
.notes-input::placeholder { color:var(--text-muted); }
.notes-input:focus { outline:none; border-color:var(--accent); }
.kbd {
  display:inline-block; padding:1px 5px; font-size:10px;
  background:var(--bg); border:1px solid var(--border);
  border-radius:3px; color:var(--text-muted); font-family:inherit;
}
.shortcuts {
  display:flex; gap:14px; font-size:11px; color:var(--text-muted);
  flex-shrink:0;
}
.shortcuts span { display:flex; align-items:center; gap:4px; }
#auto-advance-indicator {
  font-size:10px; padding:2px 8px; border-radius:3px;
  background:var(--accent-dim); color:var(--text); font-weight:600;
}

/* Help modal */
.help-overlay {
  display:none; position:fixed; inset:0; background:#000a;
  z-index:100; align-items:center; justify-content:center;
}
.help-overlay.visible { display:flex; }
.help-box {
  background:var(--surface); border:1px solid var(--border);
  border-radius:8px; padding:24px 32px; max-width:420px;
  font-size:13px; line-height:1.8;
}
.help-box h2 { font-size:15px; margin-bottom:12px; }
.help-box .row { display:flex; gap:12px; }
.help-box .row .k { width:80px; text-align:right; color:var(--accent); }

/* Factual-assertion entries (Pass 4 ledger) */
.typ.fact-verified { color:var(--verified); }
.typ.fact-discrepancy { color:var(--flagged); font-weight:700; }
.typ.fact-unverified { color:var(--text-muted); }
.fact-hdr .gname { color:var(--accent); }
.fact-banner {
  flex-shrink:0; padding:8px 14px; font-size:12px; line-height:1.5;
  background:var(--surface-alt); border-bottom:1px solid var(--border);
  max-height:110px; overflow-y:auto;
}
.fact-banner.discrepancy { border-left:3px solid var(--flagged); }
.fact-banner.verified { border-left:3px solid var(--verified); }
.fact-banner.unverified { border-left:3px solid var(--skipped); }

::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:var(--border); border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:var(--text-muted); }
"""

_JS = """\
(function() {
  const DATA = __DATA__;
  const SOURCES = __SOURCES__;
  const STORAGE_KEY = 'cite-review-' + __FILE_KEY__;

  let currentIdx = 0;
  let autoAdvance = true;
  let state = loadState();

  function loadState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch(e) {}
    return {};
  }

  function saveState() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch(e) {}
  }

  // Review state is keyed by character position (stable across page
  // regenerations); index is the fallback for entries without one. Fact
  // entries get their own prefix so a fact anchored at the same offset as a
  // citation never shares its status.
  function stateKey(idx) {
    const d = DATA[idx];
    const pre = (d && d.kind === 'fact') ? 'f' : '';
    return (d && d.position != null) ? pre + 'p' + d.position
                                     : pre + 'i' + idx;
  }

  function getCiteState(idx) {
    return state[stateKey(idx)] || { status: null, notes: '' };
  }

  function setCiteState(idx, key, val) {
    const k = stateKey(idx);
    if (!state[k]) state[k] = { status: null, notes: '' };
    state[k][key] = val;
    saveState();
  }

  function citeItemEl(idx) {
    return document.querySelector('.cite-item[data-idx="' + idx + '"]');
  }

  // Render sidebar grouped by authority: one header per cited case/
  // authority, one row per occurrence (full cite, repeat, short form, Id.)
  const listEl = document.querySelector('.cite-list');
  const groups = [];
  const groupByKey = {};
  DATA.forEach((d, i) => {
    if (d.kind === 'fact') return;  // facts render in their own section below
    const key = d.authority || d.normalized || d.cite_text;
    let g = groupByKey[key];
    if (!g) {
      g = { key: key, items: [], name: null, url: null, via: null,
            parallel: null };
      groupByKey[key] = g;
      groups.push(g);
    }
    if (!g.name && d.case_name) g.name = d.case_name;
    if (!g.name && d.antecedent_name) g.name = d.antecedent_name;
    if (!g.url && d.url) g.url = d.url;
    if (!g.via && d.via) g.via = d.via;
    if (!g.parallel && d.parallel_cite && !d.is_repeat) g.parallel = d.parallel_cite;
    g.items.push(i);
  });

  groups.forEach(g => {
    const hdr = document.createElement('div');
    hdr.className = 'cite-group-hdr';
    const viaCls = g.via === 'web' ? ' web'
      : (g.via === 'ndlaw' || g.via === 'CourtListener' || g.via === 'ndcourts-mcp') ? ' mcp' : '';  // 'ndcourts-mcp': legacy via label
    hdr.innerHTML =
      '<span class="gname">' + escWithItalics(g.name || g.key) + '</span>' +
      (g.name ? '<span class="gcite">' + esc(g.key) +
        (g.parallel ? ', ' + esc(g.parallel) : '') + '</span>' : '') +
      (g.via ? '<span class="via' + viaCls + '" title="Verified via ' + esc(g.via) + '">' + esc(g.via) + '</span>' : '') +
      (g.url ? '<a class="glink" href="' + esc(g.url) + '" target="_blank" title="' + esc(g.url) + '">&#x2197;</a>' : '') +
      '<span class="gcount">' + g.items.length + '</span>';
    var glink = hdr.querySelector('.glink');
    if (glink) glink.addEventListener('click', function(e) { e.stopPropagation(); });
    hdr.addEventListener('click', () => navigate(g.items[0]));
    listEl.appendChild(hdr);

    g.items.forEach(i => {
      const d = DATA[i];
      const item = document.createElement('div');
      item.className = 'cite-item' + (i === 0 ? ' active' : '');
      item.dataset.idx = i;
      const cs = getCiteState(i);
      item.innerHTML =
        '<div class="dot' + (cs.status ? ' ' + cs.status : '') + '"></div>' +
        '<span class="lbl">' + escWithItalics(d.cite_text) +
        (d.pin_warning ? ' <span class="pin-warn" title="' + esc(d.pin_warning) + '">&#x26a0;</span>' : '') +
        '</span>' +
        (d.para_num != null ? '<span class="ploc">&#xb6;' + d.para_num + '</span>' : '') +
        '<span class="typ">' + esc(d.is_repeat ? 'repeat' : d.cite_type) + '</span>';
      if (d.antecedent_name) item.title = 'Case name in draft: ' + d.antecedent_name;
      item.addEventListener('click', () => navigate(i));
      listEl.appendChild(item);
    });
  });

  // Factual assertions section (Pass 4 ledger entries, kind === 'fact')
  const factIdxs = [];
  DATA.forEach((d, i) => { if (d.kind === 'fact') factIdxs.push(i); });
  if (factIdxs.length) {
    const hdr = document.createElement('div');
    hdr.className = 'cite-group-hdr fact-hdr';
    hdr.innerHTML =
      '<span class="gname">Factual assertions</span>' +
      '<span class="gcount">' + factIdxs.length + '</span>';
    hdr.addEventListener('click', () => navigate(factIdxs[0]));
    listEl.appendChild(hdr);
    factIdxs.forEach(i => {
      const d = DATA[i];
      const item = document.createElement('div');
      item.className = 'cite-item fact';
      item.dataset.idx = i;
      const cs = getCiteState(i);
      item.innerHTML =
        '<div class="dot' + (cs.status ? ' ' + cs.status : '') + '"></div>' +
        '<span class="lbl">' + esc(d.claim) + '</span>' +
        (d.para_num != null ? '<span class="ploc">&#xb6;' + d.para_num + '</span>' : '') +
        '<span class="typ fact-' + d.result + '" title="' +
          esc(d.result_label) + '">' + esc(d.result) + '</span>';
      item.title = d.claim + (d.note ? ' \\u2014 ' + d.note : '');
      item.addEventListener('click', () => navigate(i));
      listEl.appendChild(item);
    });
  }

  function esc(s) {
    if (!s) return '';
    const el = document.createElement('span');
    el.textContent = s;
    return el.innerHTML;
  }

  function escWithItalics(s) {
    // HTML-escape then convert *text* to <em>text</em>
    var h = esc(s);
    return h.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
  }

  // Store original paragraph HTML for restoring after highlight removal
  const paraOriginals = {};
  document.querySelectorAll('.opinion-para').forEach(el => {
    paraOriginals[el.id] = el.innerHTML;
  });

  // Fold curly quotes and nbsp so a fact ledger quote matches the draft
  // regardless of which form each side carries (length-preserving).
  function foldQ(s) {
    return s.replace(/[\\u2018\\u2019]/g, "'")
            .replace(/[\\u201C\\u201D]/g, '"')
            .replace(/\\u00a0/g, ' ');
  }

  // Highlight a verbatim quote inside a rendered paragraph by walking its
  // text nodes — entity- and inline-markup-proof, unlike an HTML splice
  // (case names render inside <em> tags, so cite text spans inline markup).
  // occurrence selects the nth match; falls back to the first if absent.
  function highlightQuoteInPara(paraEl, quoteText, occurrence) {
    if (!quoteText) return;
    const walker = document.createTreeWalker(paraEl, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let joined = '';
    while (walker.nextNode()) {
      nodes.push({ node: walker.currentNode, start: joined.length });
      joined += walker.currentNode.nodeValue;
    }
    const hay = foldQ(joined), needle = foldQ(quoteText);
    let at = -1, from = 0;
    for (let n = 0; n <= (occurrence || 0); n++) {
      at = hay.indexOf(needle, from);
      if (at === -1) break;
      from = at + needle.length;
    }
    if (at === -1) at = hay.indexOf(needle);
    if (at < 0) return;
    const end = at + quoteText.length;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const ns = nodes[i].start;
      const len = nodes[i].node.nodeValue.length;
      if (ns + len <= at || ns >= end) continue;
      const range = document.createRange();
      range.setStart(nodes[i].node, Math.max(at - ns, 0));
      range.setEnd(nodes[i].node, Math.min(end - ns, len));
      const span = document.createElement('span');
      span.className = 'cite-hl';
      try { range.surroundContents(span); } catch (err) {}
    }
  }

  function navigate(idx) {
    if (idx < 0 || idx >= DATA.length) return;
    // Save current notes
    const notesEl = document.getElementById('notes-input');
    if (notesEl) setCiteState(currentIdx, 'notes', notesEl.value);

    currentIdx = idx;
    const d = DATA[idx];
    const cs = getCiteState(idx);

    // Sidebar (items are grouped by authority, so select by data-idx,
    // not DOM order)
    document.querySelectorAll('.cite-item').forEach(el => {
      const isActive = Number(el.dataset.idx) === idx;
      el.classList.toggle('active', isActive);
      if (isActive) el.scrollIntoView({ block: 'nearest' });
    });

    // Draft pane header
    document.querySelector('.pane-hdr .ptitle').textContent =
      'Draft' + (d.para_num != null ? ' \\u2014 \\u00b6 ' + d.para_num : '');
    document.querySelector('.pane-hdr .ctitle').textContent = d.cite_text;

    // Restore previous paragraph, highlight new one
    document.querySelectorAll('.opinion-para.active-para').forEach(el => {
      el.classList.remove('active-para');
      if (paraOriginals[el.id]) el.innerHTML = paraOriginals[el.id];
    });

    if (d.para_num != null) {
      const paraEl = document.getElementById('para-' + d.para_num);
      if (paraEl) {
        paraEl.classList.add('active-para');
        if (d.kind === 'fact') {
          // Fact entries highlight the verbatim draft quote via the text-node
          // walker: quotes routinely contain apostrophes (HTML-escaped in the
          // rendered markup) and can span inline citation links.
          highlightQuoteInPara(paraEl, d.draft_quote);
          paraEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
          // Citation occurrences use the same markup-proof walker: the cite
          // text routinely spans <em> case names and draft links, which an
          // innerHTML splice cannot match. d.occurrence counts earlier
          // appearances of the same string in this paragraph (repeated short
          // cites, multiple Id.s).
          highlightQuoteInPara(paraEl, d.cite_text, d.occurrence || 0);
          paraEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
    }

    // Notes
    if (notesEl) notesEl.value = cs.notes || '';

    // Source pane
    const srcHdr = document.querySelector('.pane-src .pane-hdr');
    const urlLink = srcHdr.querySelector('.curl');
    const modeBtn = srcHdr.querySelector('.src-mode');
    const modeBadge = srcHdr.querySelector('.src-badge');
    const srcBody = document.querySelector('.src-body');
    const sourceHtml = d.source_key ? SOURCES[d.source_key] : null;

    // ---- Source view modes -------------------------------------------------
    // Renderers write ONLY the content. The header carries the provenance
    // label and the URL for whichever view is showing, so an in-body link bar
    // would just repeat it.

    function renderLocal() {
      srcBody.innerHTML = '';
      var wrap = document.createElement('div');
      wrap.className = 'local-ref-html';
      wrap.innerHTML = sourceHtml;
      srcBody.appendChild(wrap);
      // Scroll to the pinpoint anchor: opinion [¶N] markers, or the [*N]
      // star-page marker for page pinpoints like "at 776". A source with
      // neither shows from the top.
      var target = null;
      if (d.pin_anchor) {
        target = wrap.querySelector('#pin-' + d.pin_anchor);
      }
      if (!target && d.page_anchor) {
        // Star-page anchor for page pinpoints ("at 776" → [*776] marker)
        target = wrap.querySelector('#pg-' + d.page_anchor);
      }
      if (!target && d.search_hint) {
        // Statute § section anchor. CSS.escape because case-cite hints
        // contain spaces/dots that would make the selector invalid.
        try { target = wrap.querySelector('#sec-' + CSS.escape(d.search_hint)); }
        catch (e) { target = null; }
      }
      if (target) {
        target.classList.add('pinpoint-active');
        setTimeout(function() { target.scrollIntoView({block:'center'}); }, 80);
      }
    }

    // The publisher's own text: ndcourts.gov PDF (through the PDF.js viewer
    // when we have one, so the pinpoint ¶ is searched and highlighted),
    // ndlegis.gov chapter/article PDF for N.D.C.C. and N.D.A.C. with
    // #nameddest landing on the section, ndcourts.gov HTML for court rules,
    // ndconst.org HTML for the Constitution.
    function renderOfficial() {
      var host = d.url ? d.url.replace(/^https?:\\/\\//, '').split('/')[0] : '';
      var html = '';
      if (d.viewer_path) {
        var vurl = d.viewer_path;
        if (d.search_term) vurl += '#search=' + encodeURIComponent(d.search_term);
        html = '<iframe src="' + esc(vurl) + '"></iframe>' +
          (d.search_term
            ? '<div class="search-hint">Searching: <code>' +
              esc(d.search_term) + '</code></div>'
            : '');
      } else if (d.iframe_ok) {
        html = '<iframe src="' + esc(d.url) + '"></iframe>';
      } else {
        html = '<div class="no-local">' +
          '<p>' + (d.url ? esc(host) + ' cannot be displayed inline'
                         : 'No source URL for this citation') + '</p>' +
          (d.url ? '<a class="open-tab-btn" href="' + esc(d.url) +
                   '" target="_blank">Open on ' +
                   esc(d.url_label || 'source site') + ' &#x2197;</a>' : '') +
          '</div>';
      }
      srcBody.innerHTML = html;
    }

    // Link-only official-print PDF (LOC per-case scan or supremecourt.gov
    // bound volume). Both hosts allow framing; the browser's PDF viewer
    // provides paging and search. A bound volume opens at its front matter —
    // the header URL opens it in a full tab for serious reading.
    function renderOfficialPdf() {
      srcBody.innerHTML =
        '<iframe src="' + esc(d.official_pdf.url) + '"></iframe>';
    }

    function renderNdlaw() {
      srcBody.innerHTML = '<iframe src="' + esc(d.ndlaw_url) + '"></iframe>';
    }

    function renderPassage() {
      srcBody.innerHTML = '<div class="passage-box">' +
        '<div class="passage-caption">Passage retrieved during citation ' +
        'verification' + (d.pinpoint ? ' (' + esc(d.pinpoint) + ')' : '') +
        ' — full text not embedded</div>' +
        '<blockquote>' + esc(d.passage) + '</blockquote></div>';
    }

    function renderNoSource() {
      srcBody.innerHTML =
        '<div class="no-url">No source URL for this citation</div>';
    }

    // No load-timeout fallback. An earlier version switched to the offline
    // copy if a frame had not loaded in 8s, and it misfired on the first
    // request to a cold server — the reviewer picked ndlaw and silently got
    // ~/refs. Slow is not failed, the switch is one click or one keypress
    // away, and a verification tool should never change what you are looking
    // at without being asked.

    // Order here is both the cycle order and the default (modes[0] opens).
    // ndlaw leads for ND authority: it is the only view that opens at the
    // cited ¶ for every authority type, including the statutes and rules that
    // have no local reference and no court PDF. Avalon plays the same role
    // for U.S. Const. cites (the two never coexist on one entry).
    var modes = [];
    if (d.kind === 'fact') {
      // One mode per cited record/brief source (PDF embedded at the cited
      // page with the evidence quote highlighted), then the Pass 4 detail.
      var banner = '<div class="fact-banner ' + d.result + '">' +
        '<b>' + esc(d.result_label) + '</b>' +
        (d.note ? ' \\u2014 ' + esc(d.note) : '') + '</div>';
      (d.sources || []).forEach(function(s) {
        modes.push({
          key: 'record', label: s.label, badge: 'record',
          badgeTitle: 'Cited record/brief source, embedded from the case files.',
          url: null,
          render: function() {
            srcBody.innerHTML = banner + (s.href
              ? '<iframe src="' + esc(s.href) + '"></iframe>'
              : '<div class="no-local"><p>Source PDF not found for ' +
                esc(s.label) + '</p>' +
                (s.quote ? '<blockquote>' + esc(s.quote) + '</blockquote>' : '') +
                '</div>');
          }});
      });
      modes.push({
        key: 'factnote', label: 'Fact-check detail', badge: d.result,
        badgeTitle: 'The Pass 4 fact-check finding for this claim.',
        url: null,
        render: function() {
          var q = (d.sources || []).filter(function(s) { return s.quote; })
            .map(function(s) {
              return '<div class="passage-caption">' + esc(s.label) +
                '</div><blockquote>' + esc(s.quote) + '</blockquote>';
            }).join('');
          srcBody.innerHTML = banner +
            '<div class="passage-box">' +
            '<div class="passage-caption">Claim (draft \\u00b6 ' +
            esc(d.para_display || String(d.para_num || '')) +
            ')</div><blockquote>' + esc(d.claim) + '</blockquote>' + q +
            '</div>';
        }});
    } else {
    if (d.ndlaw_url) modes.push({
      key: 'ndlaw', label: 'ndlaw.org', badge: 'unofficial',
      badgeTitle: 'Compiled copy, not an official source. Verify against the '
                + 'official text before relying on it.',
      url: d.ndlaw_url, render: renderNdlaw});
    if (d.avalon_url) modes.push({
      // Default reading pane for U.S. Const. cites: the only reliable
      // Constitution source that allows framing, opened at the cited
      // section anchor. congress.gov stays the official (link-out) mode.
      key: 'avalon', label: 'Avalon (Yale)', badge: 'unofficial',
      badgeTitle: 'Yale Law Library\\'s Avalon Project transcription, not '
                + 'an official source. Verify against the official text '
                + 'before relying on it.',
      url: d.avalon_url, render: function() {
        srcBody.innerHTML = '<iframe src="' + esc(d.avalon_url) + '"></iframe>';
      }});
    if (d.official_pdf) modes.push({
      key: 'officialpdf', label: d.official_pdf.label,
      badge: d.official_pdf.badge, badgeCls: d.official_pdf.badge_cls,
      badgeTitle: d.official_pdf.title,
      url: d.official_pdf.url, render: renderOfficialPdf});
    if (d.url) modes.push({
      key: 'weburl', label: d.url_label || 'Web source',
      badge: d.url_badge || 'unofficial', badgeCls: d.url_badge_cls || '',
      badgeTitle: d.url_badge_title || '',
      url: d.url, render: renderOfficial});
    if (d.authority_pdf) modes.push({
      key: 'authpdf', label: 'Local PDF', badge: 'pdf',
      badgeTitle: 'A PDF copy of this authority from the project directory.',
      url: d.authority_pdf.external || null,
      render: function() {
        srcBody.innerHTML =
          '<iframe src="' + esc(d.authority_pdf.href) + '"></iframe>';
      }});
    if (sourceHtml) modes.push({
      key: 'local', label: 'Local reference', badge: 'offline',
      badgeTitle: 'Cached copy under ~/refs. Readable with no network.',
      url: null, render: renderLocal});
    else if (d.passage) modes.push({
      key: 'passage', label: 'Verification passage', badge: 'excerpt',
      badgeTitle: 'The exact text the citation check relied on.',
      url: d.url, render: renderPassage});
    }
    if (!modes.length) modes.push({
      key: 'none', label: 'Source', badge: '', badgeTitle: '',
      url: null, render: renderNoSource});

    var curMode = 0;
    function setMode(i) {
      curMode = ((i % modes.length) + modes.length) % modes.length;
      var m = modes[curMode];
      var cycles = modes.length > 1;
      modeBtn.textContent = m.label;
      // Labels containing a dot are domains or citation forms ("ndcourts.gov",
      // "U.S. Reports (LOC)") — show them as written, not uppercased.
      modeBtn.className = 'ptitle src-mode mode-' + m.key +
        (m.label.indexOf('.') > -1 ? ' is-domain' : '') +
        (cycles ? ' cycles' : '');
      modeBtn.disabled = !cycles;
      modeBtn.title = cycles
        ? 'Showing ' + m.label + ' — click for '
          + modes[(curMode + 1) % modes.length].label
        : m.label;
      if (m.badge) {
        modeBadge.hidden = false;
        modeBadge.textContent = m.badge;
        modeBadge.title = m.badgeTitle;
        modeBadge.className = 'src-badge ' + (m.badgeCls !== undefined
          ? m.badgeCls : 'is-' + m.key.replace('local', 'offline'));
      } else {
        modeBadge.hidden = true;
      }
      if (m.url) {
        urlLink.href = m.url;
        urlLink.textContent = m.url.replace(/^https?:\\/\\//, '');
      } else {
        urlLink.removeAttribute('href');
        urlLink.textContent = m.key === 'local'
          ? 'cached copy — no network needed' : '';
      }
      m.render();
    }
    modeBtn.onclick = function() { if (modes.length > 1) setMode(curMode + 1); };
    // Keyboard reaches the same control: l forward, h back (the keys that
    // used to jump straight to the web and local views).
    window._cycleSource = function(delta) {
      if (modes.length > 1) setMode(curMode + (delta || 1));
    };
    setMode(0);

    // Buttons
    updateButtons(cs.status);

    // Counter
    document.querySelector('.counter').textContent = (idx + 1) + ' / ' + DATA.length;
    updateProgress();
  }

  function updateButtons(status) {
    document.querySelector('.v-btn').classList.toggle('active', status === 'verified');
    document.querySelector('.f-btn').classList.toggle('active', status === 'flagged');
    document.querySelector('.s-btn').classList.toggle('active', status === 'skipped');
  }

  function setStatus(status, advance) {
    const cs = getCiteState(currentIdx);
    const newStatus = cs.status === status ? null : status;
    setCiteState(currentIdx, 'status', newStatus);
    updateButtons(newStatus);

    // Update sidebar dot
    const itemEl = citeItemEl(currentIdx);
    if (itemEl) {
      itemEl.querySelector('.dot').className =
        'dot' + (newStatus ? ' ' + newStatus : '');
    }
    updateProgress();

    // Auto-advance to next citation if enabled and status was set (not cleared)
    if (advance && newStatus && autoAdvance && currentIdx < DATA.length - 1) {
      setTimeout(function() { navigate(currentIdx + 1); }, 120);
    }
  }

  function updateProgress() {
    let verified = 0;
    DATA.forEach((_, i) => {
      const cs = getCiteState(i);
      if (cs.status === 'verified') verified++;
    });
    document.querySelector('.progress-fill').style.width =
      (verified / DATA.length * 100) + '%';
    document.querySelector('.header-meta span').textContent =
      verified + ' of ' + DATA.length + ' verified';
  }

  // Keyboard
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') {
      if (e.key === 'Escape') { e.target.blur(); return; }
      return;
    }
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); navigate(currentIdx + 1); }
    else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); navigate(currentIdx - 1); }
    else if (e.key === 'v') setStatus('verified', true);
    else if (e.key === 'f') setStatus('flagged', true);
    else if (e.key === 's') setStatus('skipped', true);
    else if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault(); setStatus('verified', true);
    }
    else if (e.key === 'a') {
      autoAdvance = !autoAdvance;
      updateAutoAdvanceIndicator();
    }
    else if (e.key === 'l') { if (window._cycleSource) window._cycleSource(1); }
    else if (e.key === 'h') { if (window._cycleSource) window._cycleSource(-1); }
    else if (e.key === 'n') { e.preventDefault(); document.getElementById('notes-input').focus(); }
    else if (e.key === '?') toggleHelp();
    else if (e.key === 'Escape') closeHelp();
  });

  // Keep j/k working: embedded frames (Chrome's PDF viewer, PDF.js with
  // #search) grab keyboard focus when they finish loading, which silently
  // routes every subsequent keypress into the frame. Reclaim focus when a
  // frame takes it uninvited; respect a deliberate click into the pane.
  // "Uninvited" = the frame loaded within the last moment (load-time
  // focus steal) or the pointer is not even over a frame (programmatic
  // steal). A deliberate click leaves focus in the frame — clicking
  // anywhere outside it hands the keys back.
  var lastFrameLoad = 0;
  var pointerInFrame = false;
  document.addEventListener('load', function(e) {
    if (e.target && e.target.tagName === 'IFRAME') lastFrameLoad = Date.now();
  }, true);
  document.addEventListener('mouseover', function(e) {
    if (e.target.tagName === 'IFRAME') pointerInFrame = true;
  });
  document.addEventListener('mouseout', function(e) {
    if (e.target.tagName === 'IFRAME') pointerInFrame = false;
  });
  window.addEventListener('blur', function() {
    setTimeout(function() {
      var ae = document.activeElement;
      if (ae && ae.tagName === 'IFRAME' &&
          (Date.now() - lastFrameLoad < 1500 || !pointerInFrame)) {
        ae.blur();
        window.focus();
      }
    }, 0);
  });

  // Button clicks
  document.querySelector('.v-btn').addEventListener('click', () => setStatus('verified', true));
  document.querySelector('.f-btn').addEventListener('click', () => setStatus('flagged', true));
  document.querySelector('.s-btn').addEventListener('click', () => setStatus('skipped', true));

  // Help modal
  function toggleHelp() {
    document.querySelector('.help-overlay').classList.toggle('visible');
  }
  function closeHelp() {
    document.querySelector('.help-overlay').classList.remove('visible');
  }
  document.querySelector('.help-overlay').addEventListener('click', (e) => {
    if (e.target === document.querySelector('.help-overlay')) closeHelp();
  });

  // Resize handle
  const handle = document.querySelector('.resize-handle');
  const draftPane = document.querySelector('.pane-draft');
  const split = document.querySelector('.split');
  let dragging = false;

  handle.addEventListener('mousedown', (e) => {
    dragging = true;
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const rect = split.getBoundingClientRect();
    const pct = ((e.clientY - rect.top) / rect.height) * 100;
    const clamped = Math.max(15, Math.min(85, pct));
    draftPane.style.flex = '0 0 ' + clamped + '%';
  });
  document.addEventListener('mouseup', () => { dragging = false; });

  // Export state
  window.exportReviewState = function() {
    const out = DATA.map((d, i) => {
      const cs = getCiteState(i);
      if (d.kind === 'fact') {
        return {
          kind: 'fact',
          claim: d.claim,
          para_num: d.para_num,
          machine_result: d.result_label,
          status: cs.status,
          notes: cs.notes
        };
      }
      return {
        cite_text: d.cite_text,
        cite_type: d.cite_type,
        para_num: d.para_num,
        url: d.url,
        status: cs.status,
        notes: cs.notes
      };
    });
    const blob = new Blob([JSON.stringify(out, null, 2)], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'cite-review-state.json';
    a.click();
  };

  // Auto-advance indicator
  function updateAutoAdvanceIndicator() {
    var el = document.getElementById('auto-advance-indicator');
    if (el) el.textContent = autoAdvance ? 'auto-advance ON' : 'auto-advance OFF';
  }

  // Init first citation
  navigate(0);
  updateAutoAdvanceIndicator();
})();
"""


_NW_RE = re.compile(r"N\.W\.\s*[23]d")
_SCT_RE = re.compile(r"S\.\s*Ct\.")
_LED_RE = re.compile(r"L\.\s*Ed\.")


def _dedup_parallel_citations(citations: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Remove secondary parallel citations from the list.

    Rules (type-based, no reliance on parallel_cite directionality):
    - regional_reporter (N.W.2d/3d) that has a parallel_cite → drop it
    - federal_reporter matching S.Ct. or L.Ed. → always drop
    - Any citation whose parallel_cite points to a primary already kept
      and the citation itself is a reporter (not neutral/U.S.) → drop

    Returns (kept entries, alias map of dropped norm → its kept parallel
    norm) so consumers can fold occurrences citing the dropped form into
    the primary authority's group.
    """
    # Build a set of primary normalizations we want to keep
    primary_norms: set[str] = set()
    for c in citations:
        ct = c.get("cite_type", "")
        norm = c.get("normalized", "")
        # Neutral citations are always primary
        if ct == "neutral_cite":
            primary_norms.add(norm)
        # U.S. Reports are always primary
        elif ct == "us_supreme_court":
            primary_norms.add(norm)

    skip_norms: set[str] = set()
    alias: dict[str, str] = {}
    for c in citations:
        norm = c.get("normalized", "")
        ct = c.get("cite_type", "")
        pc = c.get("parallel_cite", "")

        # N.W.2d/3d parallel of a neutral cite → drop
        if ct == "regional_reporter" and _NW_RE.search(norm) and pc:
            skip_norms.add(norm)
            alias[norm] = pc
            continue

        # S.Ct. → always drop (SCOTUS parallel)
        if ct == "federal_reporter" and _SCT_RE.search(norm):
            skip_norms.add(norm)
            if pc:
                alias[norm] = pc
            continue

        # L.Ed. → always drop (SCOTUS parallel)
        if ct == "federal_reporter" and _LED_RE.search(norm):
            skip_norms.add(norm)
            if pc:
                alias[norm] = pc
            continue

        # Old ND cases cited only by N.W.2d (no neutral) with no parallel
        # → keep (e.g., 543 N.W.2d 491 for pre-1997 ND cases)

    # Collapse alias chains (dropped → dropped → kept)
    for norm in list(alias):
        target = alias[norm]
        while target in alias:
            target = alias[target]
        alias[norm] = target

    removed = len(skip_norms)
    if removed:
        print(f"  Removed {removed} parallel citations", file=sys.stderr)
    return ([c for c in citations if c.get("normalized") not in skip_norms],
            alias)


def _via_key(s: str) -> str:
    """Normalize a citation string for matching against the via map."""
    return " ".join((s or "").split()).casefold()


def _find_passage(passages: list[dict], cite: str,
                  pin_anchor: str | None, pin_page: str | None) -> str | None:
    """Find a Pass 3B verification passage for a citation occurrence.

    ``passages`` is a list of {"cite", "paragraph"|"page", "text"} objects
    written by the Pass 3B subagent as it verifies pinpoints. Matching is by
    citation (any short whitespace variance tolerated) plus the paragraph or
    page number; a cite-level passage (no paragraph/page) matches when the
    occurrence has no pinpoint either.
    """
    want_cite = _via_key(cite)
    want_page = None
    if pin_page:
        m = re.search(r"\d+", pin_page)
        want_page = m.group(0) if m else None
    for p in passages:
        if _via_key(str(p.get("cite", ""))) != want_cite:
            continue
        para = str(p.get("paragraph", "") or "")
        page = str(p.get("page", "") or "")
        if pin_anchor and para == pin_anchor:
            return p.get("text")
        if want_page and page == want_page:
            return p.get("text")
        if not pin_anchor and not want_page and not para and not page:
            return p.get("text")
    return None


_QTRANS = str.maketrans({"‘": "'", "’": "'", "“": '"',
                         "”": '"', " ": " "})


def _find_quote_position(pp_text: str, quote_text: str) -> int | None:
    """Locate a verbatim draft quote; length-preserving quote/nbsp folding
    keeps the returned offset valid against the original text."""
    if not quote_text:
        return None
    i = pp_text.find(quote_text)
    if i == -1:
        i = pp_text.translate(_QTRANS).find(quote_text.translate(_QTRANS))
    return i if i >= 0 else None


def _build_html(title: str, citations: list[dict], paragraphs: list[dict],
                file_key: str, opinion_text: str,
                viewers: dict[str, str] | None = None,
                via_map: dict[str, str] | None = None,
                sources_meta: dict[str, dict] | None = None,
                passages: list[dict] | None = None,
                authority_alias: dict[str, str] | None = None,
                ndlaw_base: str | None = _NDLAW_DEFAULT_BASE,
                facts: list[dict] | None = None,
                fact_viewers: dict[str, str] | None = None,
                link_pdfs: bool = False,
                italic_spans: list[tuple[int, int]] | None = None,
                quote_spans: list[tuple[int, int]] | None = None) -> str:
    """Build the self-contained HTML string."""
    viewers = viewers or {}
    via_map = via_map or {}
    # Build a de-duplicated map of local source HTML keyed by local_path.
    # Each citation references into this map by key, avoiding duplication.
    # Pin/repeat entries carry no file of their own; their parent's path
    # (parent_local_path) keys the same map.
    sources_map: dict[str, str] = {}  # local_path → rendered HTML
    for c in citations:
        for lp, exists in ((c.get("local_path"), c.get("local_exists")),
                           (c.get("parent_local_path"),
                            c.get("parent_local_exists"))):
            if lp and exists and lp not in sources_map:
                md = _read_local_markdown(lp)
                if md:
                    sources_map[lp] = _md_to_html(md)

    # Position→paragraph mapping happens on the same preprocessed text the
    # scanner indexed; paragraph numbers are shared with the display split.
    pp_text = _preprocess_like_scanner(opinion_text)
    pp_paragraphs = _split_paragraphs(pp_text)

    sources_meta = sources_meta or {}
    passages = passages or []
    authority_alias = authority_alias or {}

    # Enrich citation entries
    enriched = []
    for c in citations:
        para_num, occurrence = None, 0
        if isinstance(c.get("position"), int):
            para_num, occurrence = _locate_occurrence(
                pp_paragraphs, pp_text, c["position"], c["cite_text"])
        if para_num is None:
            para = _find_paragraph(paragraphs, c["cite_text"])
            para_num = para["num"] if para else None
        norm = c.get("normalized", c["cite_text"])
        parent_norm = c.get("parent_normalized")
        url = c.get("url") or ""
        # ndlaw metadata: authoritative case name and the court's direct
        # opinion URL, keyed by any citation form of the opinion.
        meta = sources_meta.get(_via_key(norm)) or (
            sources_meta.get(_via_key(parent_norm)) if parent_norm else None) or {}
        case_name = meta.get("case_name")
        if meta.get("url"):
            url = meta["url"]
        # Fallback for ND opinions with local refs but no direct URL:
        # derive the ndcourts.gov search URL from the refs path
        lp = c.get("local_path") or c.get("parent_local_path")
        if lp and (not url or "?cit1=" in url):
            direct = _nd_direct_url(lp)
            if direct:
                url = direct
        host = urlparse(url).netloc if url else ""
        pinpoint = c.get("pinpoint")
        viewer_path = viewers.get(url) if url else None
        search_term = _pinpoint_search_term(pinpoint) if pinpoint and viewer_path else ""
        has_source = lp is not None and lp in sources_map
        # Anchors for scrolling the embedded source: opinion ¶ markers, or —
        # for page pinpoints like "at 776" — the [*776] star-page marker in
        # the cached markdown (#pg-N locally, #starN on ndlaw.org). A range
        # pin ("at 776-77") anchors on its first page.
        pin_anchor = None
        if c.get("pin_paragraph"):
            m = re.search(r"\d+", c["pin_paragraph"])
            pin_anchor = m.group(0) if m else None
        elif pinpoint and "¶" in pinpoint:
            m = re.search(r"\d+", pinpoint)
            pin_anchor = m.group(0) if m else None
        page_anchor = None
        if pin_anchor is None:
            page_src = c.get("pin_page")
            if not page_src and pinpoint and re.match(r"(?i)at\s+\d", pinpoint):
                page_src = pinpoint
            if page_src:
                m = re.search(r"\d+", page_src)
                page_anchor = m.group(0) if m else None
        via = via_map.get(_via_key(norm)) or via_map.get(_via_key(c["cite_text"]))
        if not via and meta.get("via"):
            via = meta["via"]
        # Verification passage (Pass 3B ledger): the exact text the cite
        # check relied on. Shown when no full source text is embedded.
        passage = None
        if not has_source:
            passage = _find_passage(passages, parent_norm or norm,
                                    pin_anchor, c.get("pin_page"))
        # Authority grouping key: the first-occurrence cite this entry
        # ultimately refers to, with dropped parallels folded into their
        # kept primary form.
        authority = parent_norm or norm
        authority = authority_alias.get(authority, authority)
        # ndlaw reading copy. Keyed on the authority (a pin/repeat entry
        # resolves to the cite it refers back to) but carrying THIS entry's
        # pinpoint, so every occurrence opens at its own ¶.
        ndlaw_url = None
        if ndlaw_base and _ndlaw_eligible(c, meta):
            ndlaw_url = _ndlaw_url(authority, pin_anchor, ndlaw_base,
                                   page_anchor=page_anchor)
        # Local-PDF authority (an obscure source dropped as a PDF in the
        # project dir, declared in sources-meta): same viewer treatment as
        # record items, surfaced as its own source-pane mode.
        authority_pdf = meta.get("pdf_viewer") or None
        # Web-source provenance for the URL mode: label the pane with the
        # actual source and badge it official only when the host is the
        # issuing/publishing government entity.
        url_label = url_badge = url_badge_cls = url_badge_title = None
        if url:
            url_label, url_badge, url_badge_cls, url_badge_title = \
                _url_source_info(url)
        # Link-only official-print PDF (jetcite official_pdf_url: LOC
        # per-case scan or supremecourt.gov bound volume for U.S. Reports).
        official_pdf = None
        pdf_url = c.get("official_pdf_url")
        if pdf_url:
            # LOC per-case scans start at the case's first reporter page, so
            # a page pin maps to a PDF page: page_anchor − first + 1. Chrome's
            # viewer honors #page= in iframes; a bad guess still shows the PDF.
            if page_anchor and "tile.loc.gov" in pdf_url:
                m = re.search(r"\d+\s+U\.S\.\s+(\d+)", parent_norm or norm)
                if m:
                    offset = int(page_anchor) - int(m.group(1)) + 1
                    if offset > 1:
                        pdf_url += f"#page={offset}"
            _pl, _pb, _pc, _pt = _url_source_info(pdf_url)
            official_pdf = {"url": pdf_url, "label": _pl, "badge": _pb,
                            "badge_cls": _pc or "is-official", "title": _pt}
        # Frameable scholarly reading copy for U.S. Const. cites (Avalon
        # Project, Yale) — the default pane; congress.gov stays the official
        # link-out. Pin/repeat entries inherit their parent's sources at scan
        # time, so the field is already present on them.
        avalon_url = c.get("avalon_url")
        enriched.append({
            "ndlaw_url": ndlaw_url,
            "authority_pdf": authority_pdf,
            "cite_text": c["cite_text"],
            "cite_type": c.get("cite_type", ""),
            "normalized": norm,
            "authority": authority,
            "antecedent_name": c.get("antecedent_name"),
            "case_name": case_name,
            "url": url or None,
            "url_label": url_label,
            "url_badge": url_badge,
            "url_badge_cls": url_badge_cls,
            "url_badge_title": url_badge_title,
            "official_pdf": official_pdf,
            "avalon_url": avalon_url,
            "iframe_ok": host in _IFRAME_OK_DOMAINS,
            "para_num": para_num,
            "occurrence": occurrence,
            "position": c.get("position"),
            "is_repeat": bool(c.get("is_repeat")),
            "parent_normalized": parent_norm,
            "pin_warning": c.get("pin_warning"),
            "parallel_cite": c.get("parallel_cite"),
            "search_hint": c.get("search_hint", ""),
            "pinpoint": pinpoint,
            "pin_anchor": pin_anchor,
            "page_anchor": page_anchor,
            "viewer_path": viewer_path,
            "search_term": search_term,
            "source_key": lp if has_source else None,
            "passage": passage,
            "via": via,
        })

    # Factual assertions (Pass 4 facts ledger), appended after the citation
    # entries so they share navigation, statuses, notes, and export.
    facts = facts or []
    fact_viewers = fact_viewers or {}
    n_cites = len(enriched)
    for f in facts:
        position = None
        para_num = None
        occurrence = 0
        dq = f.get("draft_quote") or ""
        pos = _find_quote_position(pp_text, dq)
        if pos is not None:
            position = pos
            para_num, occurrence = _locate_occurrence(
                pp_paragraphs, pp_text, pos, dq)
        if para_num is None:
            m = re.search(r"\d+", f.get("para") or "")
            para_num = int(m.group(0)) if m else None
        srcs = []
        for s in f.get("sources", []):
            resolved = s.get("_resolved_path")
            base_url = fact_viewers.get(resolved) if resolved else None
            href = None
            if base_url:
                if link_pdfs:
                    page = s.get("page")
                    href = base_url + (f"#page={page}"
                                       if isinstance(page, int) and page > 0
                                       else "")
                else:
                    href = base_url + _fact_source_hash(s)
            srcs.append({
                "label": (s.get("raw") or s.get("item") or "source").strip(),
                "href": href,
                "page": s.get("page"),
                "quote": (s.get("quote") or "").strip() or None,
            })
        enriched.append({
            "kind": "fact",
            "cite_text": f["claim"],
            "claim": f["claim"],
            "result": f["result"],
            "result_label": f["result_label"],
            "note": f["note"],
            "para_display": f.get("para") or "",
            "para_num": para_num,
            "occurrence": occurrence,
            "position": position,
            "draft_quote": dq or None,
            "sources": srcs,
        })

    data_json = json.dumps(enriched, ensure_ascii=False)
    sources_json = json.dumps(sources_map, ensure_ascii=False)
    file_key_json = json.dumps(file_key, ensure_ascii=False)

    js = (_JS
          .replace("__DATA__", data_json)
          .replace("__SOURCES__", sources_json)
          .replace("__FILE_KEY__", file_key_json))
    escaped_title = html.escape(title)
    opinion_html = _opinion_to_html(opinion_text, paragraphs, italic_spans,
                                    quote_spans)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Citation Review — {escaped_title}</title>
<style>
{_CSS}
</style>
</head>
<body>

<header>
  <h1>Citation Review — {escaped_title}</h1>
  <div class="header-meta">
    <span>0 of {len(enriched)} verified</span>
    <div class="progress-bar"><div class="progress-fill"></div></div>
    <span class="counter">1 / {len(enriched)}</span>
  </div>
</header>

<main>
  <div class="sidebar">
    <div class="sidebar-header">Citations ({n_cites})</div>
    <div class="cite-list"></div>
  </div>

  <div class="content">
    <div class="split">
      <div class="pane-draft">
        <div class="pane-hdr">
          <span class="ptitle">Draft</span>
          <span class="ctitle"></span>
        </div>
        <div class="draft-body" id="opinion-body">
          {opinion_html}
        </div>
      </div>

      <div class="resize-handle"></div>

      <div class="pane-src">
        <div class="pane-hdr">
          <span class="src-mode-wrap">
            <button type="button" class="ptitle src-mode">Source</button>
            <span class="src-badge" hidden></span>
          </span>
          <a class="curl" href="#" target="_blank"></a>
        </div>
        <div class="src-body" style="flex:1;display:flex;flex-direction:column;position:relative;min-height:0;overflow:hidden;">
          <div class="no-url">Select a citation</div>
        </div>
      </div>
    </div>

    <div class="action-bar">
      <div class="actions">
        <button class="btn v-btn"><span class="kbd">v</span> Verified</button>
        <button class="btn f-btn"><span class="kbd">f</span> Flag</button>
        <button class="btn s-btn"><span class="kbd">s</span> Skip</button>
        <button class="btn" onclick="exportReviewState()" style="margin-left:12px;">
          Export JSON
        </button>
      </div>
      <input type="text" class="notes-input" id="notes-input"
             placeholder="Notes for this citation..." />
      <div class="shortcuts">
        <span><span class="kbd">j</span>/<span class="kbd">&darr;</span> next</span>
        <span><span class="kbd">k</span>/<span class="kbd">&uarr;</span> prev</span>
        <span><span class="kbd">n</span> notes</span>
        <span id="auto-advance-indicator" class="auto-advance-on"></span>
        <span><span class="kbd">?</span> help</span>
      </div>
    </div>
  </div>
</main>

<div class="help-overlay">
  <div class="help-box">
    <h2>Keyboard Shortcuts</h2>
    <div class="row"><span class="k">j / &darr;</span> Next citation</div>
    <div class="row"><span class="k">k / &uarr;</span> Previous citation</div>
    <div class="row"><span class="k">v</span> Toggle verified</div>
    <div class="row"><span class="k">f</span> Toggle flagged</div>
    <div class="row"><span class="k">s</span> Toggle skipped</div>
    <div class="row"><span class="k">Space / Enter</span> Verify + advance</div>
    <div class="row"><span class="k">a</span> Toggle auto-advance</div>
    <div class="row"><span class="k">h</span> Show local source</div>
    <div class="row"><span class="k">l</span> Show web source</div>
    <div class="row"><span class="k">n</span> Focus notes</div>
    <div class="row"><span class="k">Esc</span> Blur notes / close help</div>
    <div class="row"><span class="k">?</span> Toggle this help</div>
  </div>
</div>

<script>
{js}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate citation review HTML from an opinion and its citations."
    )
    parser.add_argument("--opinion", "-o", required=True,
                        help="Path to opinion markdown file")
    parser.add_argument("--docx",
                        help="Original .docx the opinion markdown was "
                        "extracted from. Used solely to recover italics "
                        "(case names, Id., signals, added emphasis) for the "
                        "draft pane; no effect on citation scanning.")
    parser.add_argument("--cite-json", "-c",
                        help="Path to pre-generated cite_check.py JSON "
                             "(if omitted, runs cite_check internally)")
    parser.add_argument("--refs-dir", default="~/refs",
                        help="Refs directory for cite_check (default: ~/refs)")
    parser.add_argument("--output", default="cite-review.html",
                        help="Output HTML file path (default: cite-review.html)")
    parser.add_argument("--title", "-t", default="",
                        help="Document title for the header")
    parser.add_argument("--local-only", action="store_true",
                        help="Skip web downloads; use local refs only")
    parser.add_argument("--via-json",
                        help="Path to a JSON object mapping a citation "
                             "(normalized or as-written) to the tier that "
                             "verified it (ndlaw / CourtListener / "
                             "local / web / not found), from Pass 3B. Renders "
                             "a per-citation 'via' provenance badge.")
    parser.add_argument("--sources-meta",
                        help="Path to ndlaw_export.py metadata JSON mapping "
                             "a citation to case_name / direct opinion url / "
                             "url_source / via. Supplies the court's direct "
                             "PDF URL and authoritative captions.")
    parser.add_argument("--passages-json",
                        help="Path to a Pass 3B passages ledger: JSON array "
                             "of {cite, paragraph|page, text} objects holding "
                             "the exact text each pinpoint verification "
                             "relied on. Shown in the source pane when no "
                             "full text is embedded for the citation.")
    parser.add_argument("--facts-json",
                        help="Path to the Pass 4 facts ledger: JSON array of "
                             "{para, claim, draft_quote, result, note, "
                             "sources:[{raw, item, file, page, para_pin, "
                             "quote}]} objects. Adds a factual-assertion "
                             "review section with the cited record/brief "
                             "PDFs embedded at the cited spot.")
    parser.add_argument("--record-dir",
                        help="Directory of district-court record item PDFs "
                             "named 'R<N> - <Type> <Title>.pdf'. Used to "
                             "resolve record cites like 'R243' from the "
                             "facts ledger.")
    parser.add_argument("--case-manifest",
                        help="Path to a case manifest JSON (array of "
                             "{docketId, filename, ...}) mapping docket "
                             "numbers and brief names to PDF files in the "
                             "manifest's directory.")
    parser.add_argument("--case-dir",
                        help="Project directory holding the case PDFs and "
                             "manifest.json (default: the opinion file's "
                             "directory). Pass this when the opinion "
                             "markdown lives in a temp dir.")
    parser.add_argument("--link-pdfs", action="store_true",
                        help="Reference record/authority PDFs via native "
                             "iframes (relative file links + #page=N) "
                             "instead of embedding base64 PDF.js viewer "
                             "sidecars. Zero-copy, but no quote "
                             "highlighting and page landing depends on the "
                             "browser's built-in PDF viewer.")
    parser.add_argument("--ndlaw-base", default=_NDLAW_DEFAULT_BASE,
                        help="Base URL of the ndlaw citation site used for the "
                             "reading-copy pane (default: %(default)s). Point "
                             "at a local instance to test unreleased corpus "
                             "changes.")
    parser.add_argument("--no-ndlaw", action="store_true",
                        help="Do not embed ndlaw reading copies; official "
                             "sources and local refs only.")
    args = parser.parse_args()

    opinion_path = Path(args.opinion).expanduser()
    if not opinion_path.exists():
        print(f"Error: opinion file not found: {opinion_path}", file=sys.stderr)
        sys.exit(1)

    cite_json_path = Path(args.cite_json).expanduser() if args.cite_json else None
    # Resolve to absolute: jetcite's local-source attach builds file:// URIs,
    # which require absolute paths.
    args.refs_dir = str(Path(args.refs_dir).expanduser().resolve())
    citations = _load_citations(opinion_path, cite_json_path, args.refs_dir,
                                local_only=args.local_only)

    via_map: dict[str, str] = {}
    if args.via_json:
        try:
            raw = json.loads(Path(args.via_json).expanduser().read_text(encoding="utf-8"))
            via_map = {_via_key(k): v for k, v in raw.items() if v}
        except (OSError, ValueError) as e:
            print(f"Warning: could not read --via-json ({e}); "
                  "rendering without via badges.", file=sys.stderr)

    sources_meta: dict[str, dict] = {}
    if args.sources_meta:
        try:
            raw = json.loads(Path(args.sources_meta).expanduser().read_text(encoding="utf-8"))
            sources_meta = {_via_key(k): v for k, v in raw.items()
                            if isinstance(v, dict)}
        except (OSError, ValueError) as e:
            print(f"Warning: could not read --sources-meta ({e}); "
                  "rendering without ndlaw metadata.", file=sys.stderr)

    passages: list[dict] = []
    if args.passages_json:
        try:
            raw = json.loads(Path(args.passages_json).expanduser().read_text(encoding="utf-8"))
            passages = [p for p in raw if isinstance(p, dict) and p.get("text")]
        except (OSError, ValueError, TypeError) as e:
            print(f"Warning: could not read --passages-json ({e}); "
                  "rendering without verification passages.", file=sys.stderr)

    facts: list[dict] = []
    if args.facts_json:
        try:
            facts = _load_facts(Path(args.facts_json).expanduser())
        except (OSError, ValueError) as e:
            print(f"Warning: could not read --facts-json ({e}); "
                  "rendering without factual assertions.", file=sys.stderr)

    if not citations:
        print("No citations found.", file=sys.stderr)
        sys.exit(1)

    citations, authority_alias = _dedup_parallel_citations(citations)

    text = opinion_path.read_text(encoding="utf-8")
    paragraphs = _split_paragraphs(text)

    title = args.title or opinion_path.stem
    file_key = opinion_path.stem
    out = Path(args.output)

    # Resolve fact-ledger source refs and local-PDF authorities to files on
    # disk, then build embeddable viewers for each unique PDF (base64 PDF.js
    # sidecars by default; relative file links with --link-pdfs).
    base_dir = (Path(args.case_dir).expanduser().resolve()
                if args.case_dir else opinion_path.parent.resolve())
    record_dir = (Path(args.record_dir).expanduser().resolve()
                  if args.record_dir else None)
    manifest_dir = base_dir
    manifest: list[dict] = []
    if args.case_manifest:
        mp = Path(args.case_manifest).expanduser().resolve()
        manifest = _load_manifest(mp)
        manifest_dir = mp.parent
    else:
        default_manifest = base_dir / "manifest.json"
        if default_manifest.exists():
            manifest = _load_manifest(default_manifest)

    fact_pdfs: list[Path] = []
    unresolved = 0
    for f in facts:
        for s in f["sources"]:
            p = _resolve_fact_source(s, record_dir, manifest, base_dir,
                                     manifest_dir)
            if p:
                s["_resolved_path"] = str(p.resolve())
                fact_pdfs.append(p)
            else:
                unresolved += 1
    if unresolved:
        print(f"  Note: {unresolved} fact source ref(s) did not resolve to a "
              "PDF; shown as text-only.", file=sys.stderr)

    for meta in sources_meta.values():
        pdf = meta.get("pdf")
        if not pdf:
            continue
        p = Path(pdf).expanduser()
        if not p.is_absolute():
            p = base_dir / p
        if p.exists():
            meta["_pdf_path"] = str(p.resolve())
            fact_pdfs.append(p)
        else:
            print(f"  Warning: sources-meta pdf not found: {pdf}",
                  file=sys.stderr)

    fact_viewers = (_generate_local_pdf_viewers(fact_pdfs, out,
                                                link_pdfs=args.link_pdfs)
                    if fact_pdfs else {})

    for meta in sources_meta.values():
        pp = meta.pop("_pdf_path", None)
        if pp and pp in fact_viewers:
            base_url = fact_viewers[pp]
            if args.link_pdfs:
                page = meta.get("page")
                href = base_url + (f"#page={page}"
                                   if isinstance(page, int) and page > 0
                                   else "")
            else:
                href = base_url + _fact_source_hash(
                    {"page": meta.get("page"), "quote": meta.get("quote")})
            meta["pdf_viewer"] = {"href": href, "external": base_url,
                                  "label": Path(pp).name}

    # Download opinion PDFs and generate local PDF.js viewers for pinpoint search
    viewers = _generate_pdfjs_viewers(
        [{"url": c.get("url"), "pinpoint": c.get("pinpoint"),
          "normalized": c.get("normalized", ""),
          "local_path": c.get("local_path"),
          "local_exists": c.get("local_exists")}
         for c in citations],
        out,
        local_only=args.local_only,
    )

    italic_spans: list[tuple[int, int]] = []
    quote_spans: list[tuple[int, int]] = []
    if args.docx:
        docx_path = Path(args.docx).expanduser()
        if docx_path.exists():
            italic_spans, quote_spans = _format_spans_from_docx(docx_path, text)
            if italic_spans or quote_spans:
                print(f"  Formatting recovered from {docx_path.name}: "
                      f"{len(italic_spans)} italic span(s), "
                      f"{len(quote_spans)} block quote(s)", file=sys.stderr)
        else:
            print(f"Warning: --docx not found: {docx_path}; "
                  "rendering plain.", file=sys.stderr)

    html_str = _build_html(title, citations, paragraphs, file_key, text, viewers,
                           via_map=via_map, sources_meta=sources_meta,
                           passages=passages, authority_alias=authority_alias,
                           ndlaw_base=None if args.no_ndlaw else args.ndlaw_base,
                           facts=facts, fact_viewers=fact_viewers,
                           link_pdfs=args.link_pdfs, italic_spans=italic_spans,
                           quote_spans=quote_spans)

    out.write_text(html_str, encoding="utf-8")
    n_viewers = len(viewers) + len(fact_viewers)
    extra = f", {n_viewers} PDF viewer(s)" if n_viewers else ""
    fact_note = f", {len(facts)} factual assertion(s)" if facts else ""
    print(f"Wrote {out} ({len(citations)} citations{fact_note}{extra})")


if __name__ == "__main__":
    main()

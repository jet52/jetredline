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
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

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

    Returns list of {"num": int|None, "text": str}.
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
        return [{"num": None, "text": text.strip()}]

    paragraphs = []
    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        paragraphs.append({"num": num, "text": text[start:end].strip()})
    return paragraphs


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


def _inline_links(text: str) -> str:
    """Convert markdown [text](url) links in already-escaped HTML to <a> tags.

    We run this on the raw text *before* html.escape so we can identify the
    link structure, then rebuild with escaped parts.
    """
    def _replace(m: re.Match) -> str:
        label = html.escape(m.group(1))
        url = html.escape(m.group(2))
        return f'<a class="draft-link" href="{url}" target="_blank" title="{url}">{label}</a>'
    return _MD_LINK_RE.sub(_replace, text)


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


def _opinion_to_html(text: str, paragraphs: list[dict]) -> str:
    """Convert opinion text to HTML fragment with paragraph anchors."""
    if not paragraphs or paragraphs[0]["num"] is None:
        return f'<div class="opinion-text">{_escape_with_links(text)}</div>'

    parts = []
    # Header text before first paragraph marker
    # Use whichever regex produced more matches (same logic as _split_paragraphs)
    para_matches = list(_PARA_RE.finditer(text))
    num_matches = list(_PARA_NUM_RE.finditer(text))
    if num_matches and len(num_matches) > len(para_matches):
        first_match = num_matches[0] if num_matches else None
    else:
        first_match = para_matches[0] if para_matches else None
    if first_match and first_match.start() > 0:
        header = text[:first_match.start()].strip()
        if header:
            parts.append(
                f'<div class="opinion-header">{_escape_with_links(header)}</div>'
            )

    for p in paragraphs:
        pid = f'para-{p["num"]}' if p["num"] is not None else "para-0"
        escaped = _escape_with_links(p["text"])
        parts.append(
            f'<div class="opinion-para" id="{pid}">'
            f'<span class="para-marker">[¶{p["num"]}]</span> '
            f'{escaped}</div>'
        )
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
            # Build Citation objects from the result entries for fetch_and_cache.
            # Re-scan with resolution disabled to get Citation objects.
            saved2 = _disable_url_resolution()
            from jetcite import scan_text as _st
            cite_objs = {
                c.normalized: c
                for c in _st(text, refs_dir=Path(refs_dir).expanduser())
            }
            _restore_url_resolution(saved2)

            _CACHEABLE = {
                "neutral_cite", "us_supreme_court",
                "federal_reporter", "regional_reporter",
            }
            to_cache = [
                e for e in result
                if not e.get("local_exists") and e.get("url")
                and e.get("cite_type") in _CACHEABLE
            ]
            if to_cache:
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


# Domains whose pages can be loaded in an iframe (no X-Frame-Options block)
# ndcourts.gov removed — cached markdown is always a better experience
_IFRAME_OK_DOMAINS = frozenset({
    "ndlegis.gov",
})

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
canvas { display:block; box-shadow:0 1px 4px rgba(0,0,0,.4); }
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
// Read search term from URL hash: viewer.html#search=...
const hashParams = new URLSearchParams(location.hash.slice(1));
const SEARCH = decodeURIComponent(hashParams.get('search') || '');

const raw = atob(PDF_DATA);
const bytes = new Uint8Array(raw.length);
for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

try {
  const pdf = await pdfjsLib.getDocument({ data: bytes }).promise;
  document.getElementById('loading').remove();

  const container = document.getElementById('pages');
  const scale = 1.5;
  let targetCanvas = null;

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement('canvas');
    canvas.id = 'page-' + i;
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    await page.render({ canvasContext: ctx, viewport }).promise;

    if (SEARCH && !targetCanvas) {
      const tc = await page.getTextContent();
      const text = tc.items.map(item => item.str).join('');
      if (text.includes(SEARCH)) {
        targetCanvas = canvas;
      }
    }
  }

  if (targetCanvas) {
    targetCanvas.classList.add('target-page');
    targetCanvas.scrollIntoView({ block: 'start' });
    document.getElementById('search-bar').textContent =
      'Found on page ' + targetCanvas.id.replace('page-', '');
    setTimeout(() => targetCanvas.classList.remove('target-page'), 3000);
  } else if (SEARCH) {
    document.getElementById('search-bar').textContent =
      'Search term not found: ' + SEARCH;
  }
} catch (err) {
  document.getElementById('loading').textContent = 'Error loading PDF: ' + err.message;
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


def _needs_pdfjs_viewer(url: str, pinpoint: str | None) -> bool:
    """Check if a citation URL should use the PDF.js viewer with search."""
    if not url or not pinpoint:
        return False
    # Already has a named destination — browser handles it
    if "#nameddest=" in url:
        return False
    # Only for ndcourts.gov opinion PDFs
    host = urlparse(url).netloc
    return host in ("www.ndcourts.gov", "ndcourts.gov")


def _pinpoint_search_term(pinpoint: str | None) -> str:
    """Convert a pinpoint like '¶ 15' to a PDF search term like '[¶15]'."""
    if not pinpoint:
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
_MD_SECTION = re.compile(r"§\s*([\d\w.-]+)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_BLOCKQUOTE_LINE = re.compile(r"^>\s?(.*)", re.MULTILINE)


def _md_to_html(md: str) -> str:
    """Convert legal markdown to HTML with anchors for pinpoint navigation."""
    lines = md.split("\n")
    out: list[str] = []
    in_blockquote = False
    in_para = False

    def _inline(text: str) -> str:
        text = html.escape(text)
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

    return "\n".join(out)


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
# HTML generation
# ---------------------------------------------------------------------------

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
.pane-src .no-url, .pane-src .no-local {
  flex:1; display:flex; flex-direction:column;
  align-items:center; justify-content:center;
  color:var(--text-muted); font-size:13px; gap:16px;
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
.local-toggle {
  position:absolute; bottom:8px; left:12px;
  font-size:11px; color:var(--accent); background:var(--surface);
  padding:4px 10px; border-radius:4px;
  border:1px solid var(--border); text-decoration:none;
  font-family:'SF Mono',monospace; z-index:10; cursor:pointer;
}
.local-toggle:hover { background:var(--accent-dim); color:#fff; }
.source-link-bar {
  display:flex; align-items:center; gap:8px;
  padding:6px 16px; background:#f0f0ee; border-bottom:1px solid #d8d8d4;
  flex-shrink:0; font-family:'SF Mono','Cascadia Code',monospace; font-size:11px;
}
.source-link-bar a {
  color:#3366cc; text-decoration:none; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap;
}
.source-link-bar a:hover { text-decoration:underline; }
.source-link-bar .ext-icon { font-size:13px; flex-shrink:0; }
.local-ref-html {
  flex:1; overflow-y:auto; padding:24px 36px;
  font-family:'Charter','Georgia','Times New Roman',serif; font-size:17px;
  line-height:1.85; color:#1a1a1a; background:#fdfdf8;
  margin:0;
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

  function getCiteState(idx) {
    return state[idx] || { status: null, notes: '' };
  }

  function setCiteState(idx, key, val) {
    if (!state[idx]) state[idx] = { status: null, notes: '' };
    state[idx][key] = val;
    saveState();
  }

  // Render sidebar
  const listEl = document.querySelector('.cite-list');
  DATA.forEach((d, i) => {
    const item = document.createElement('div');
    item.className = 'cite-item' + (i === 0 ? ' active' : '');
    item.dataset.idx = i;
    const cs = getCiteState(i);
    item.innerHTML =
      '<div class="dot' + (cs.status ? ' ' + cs.status : '') + '"></div>' +
      '<span class="lbl">' + escWithItalics(d.cite_text) + '</span>' +
      '<span class="typ">' + esc(d.cite_type) + '</span>';
    item.addEventListener('click', () => navigate(i));
    listEl.appendChild(item);
  });

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

  function navigate(idx) {
    if (idx < 0 || idx >= DATA.length) return;
    // Save current notes
    const notesEl = document.getElementById('notes-input');
    if (notesEl) setCiteState(currentIdx, 'notes', notesEl.value);

    currentIdx = idx;
    const d = DATA[idx];
    const cs = getCiteState(idx);

    // Sidebar
    document.querySelectorAll('.cite-item').forEach((el, i) => {
      el.classList.toggle('active', i === idx);
      if (i === idx) el.scrollIntoView({ block: 'nearest' });
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
        // Highlight the citation text
        const escapedCite = esc(d.cite_text);
        const original = paraEl.innerHTML;
        const markerEnd = original.indexOf('</span>');
        if (markerEnd > -1) {
          const cutpoint = markerEnd + 7;
          const before = original.slice(0, cutpoint);
          const after = original.slice(cutpoint);
          paraEl.innerHTML = before + after.replace(
            escapedCite,
            '<span class="cite-hl">' + escapedCite + '</span>'
          );
        }
        paraEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }

    // Notes
    if (notesEl) notesEl.value = cs.notes || '';

    // Source pane
    const srcHdr = document.querySelector('.pane-src .pane-hdr');
    const urlLink = srcHdr.querySelector('.curl');
    const srcBody = document.querySelector('.src-body');
    const sourceHtml = d.source_key ? SOURCES[d.source_key] : null;

    // Helper: render local source HTML into the source pane
    function showLocal() {
      srcBody.innerHTML = '';
      // Source link bar at top
      if (d.url) {
        var bar = document.createElement('div');
        bar.className = 'source-link-bar';
        bar.innerHTML = '<span class="ext-icon">&#x1f517;</span>' +
          '<a href="' + esc(d.url) + '" target="_blank">' +
          esc(d.url.replace(/^https?:\\/\\//, '')) + '</a>';
        srcBody.appendChild(bar);
      }
      var wrap = document.createElement('div');
      wrap.className = 'local-ref-html';
      wrap.innerHTML = sourceHtml;
      srcBody.appendChild(wrap);
      // Scroll to pinpoint anchor
      var target = null;
      if (d.pinpoint) {
        // Opinion ¶ pinpoint
        var pNum = (d.pinpoint.match(/\\d+/) || [''])[0];
        if (pNum) target = wrap.querySelector('#pin-' + pNum);
      }
      if (!target && d.search_hint) {
        // Statute § section anchor
        target = wrap.querySelector('#sec-' + d.search_hint);
      }
      if (target) {
        target.classList.add('pinpoint-active');
        setTimeout(function() { target.scrollIntoView({block:'center'}); }, 80);
      }
    }

    // Helper: render iframe/web view into the source pane
    function showIframe() {
      var html = '';
      if (d.url) {
        html += '<div class="source-link-bar"><span class="ext-icon">&#x1f517;</span>' +
          '<a href="' + esc(d.url) + '" target="_blank">' +
          esc(d.url.replace(/^https?:\\/\\//, '')) + '</a></div>';
      }
      if (d.viewer_path) {
        var viewerUrl = d.viewer_path;
        if (d.search_term) viewerUrl += '#search=' + encodeURIComponent(d.search_term);
        html += '<iframe src="' + esc(viewerUrl) + '"></iframe>' +
          (d.search_term
            ? '<div class="search-hint">Searching: <code>' + esc(d.search_term) + '</code></div>'
            : '');
      } else if (d.iframe_ok) {
        html += '<iframe src="' + esc(d.url) + '"></iframe>';
      }
      if (sourceHtml) {
        html += '<span class="local-toggle" onclick="window._showLocal()">Local reference</span>';
      }
      srcBody.innerHTML = html;
      // Detect iframe load failure and auto-switch to local
      var iframe = srcBody.querySelector('iframe');
      if (iframe && sourceHtml) {
        var loadTimer = setTimeout(function() { showLocal(); }, 8000);
        iframe.addEventListener('load', function() { clearTimeout(loadTimer); });
        iframe.addEventListener('error', function() { clearTimeout(loadTimer); showLocal(); });
      }
    }
    // Expose for onclick
    window._showLocal = showLocal;
    window._showIframe = showIframe;

    // Set URL link (always visible)
    if (d.url) {
      urlLink.href = d.url;
      urlLink.textContent = d.url.replace(/^https?:\\/\\//, '');
    } else {
      urlLink.href = '#';
      urlLink.textContent = sourceHtml ? 'local reference' : 'no URL available';
    }

    // Choose primary view: local source preferred (instant), web as fallback
    if (sourceHtml) {
      showLocal();
    } else if (d.viewer_path || d.iframe_ok) {
      showIframe();
    } else if (d.url) {
      srcBody.innerHTML =
        '<div class="source-link-bar"><span class="ext-icon">&#x1f517;</span>' +
        '<a href="' + esc(d.url) + '" target="_blank">' +
        esc(d.url.replace(/^https?:\\/\\//, '')) + '</a></div>' +
        '<div class="no-local">' +
        '<p>Source not cached locally</p>' +
        '<a class="open-tab-btn" href="' + esc(d.url) +
        '" target="_blank">Open source in new tab &#x2197;</a>' +
        '</div>';
    } else {
      srcBody.innerHTML = '<div class="no-url">No source URL for this citation</div>';
    }

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
    const dot = document.querySelectorAll('.cite-item')[currentIdx].querySelector('.dot');
    dot.className = 'dot' + (newStatus ? ' ' + newStatus : '');
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
    else if (e.key === 'l') { if (window._showIframe) window._showIframe(); }
    else if (e.key === 'h') { if (window._showLocal) window._showLocal(); }
    else if (e.key === 'n') { e.preventDefault(); document.getElementById('notes-input').focus(); }
    else if (e.key === '?') toggleHelp();
    else if (e.key === 'Escape') closeHelp();
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


def _dedup_parallel_citations(citations: list[dict]) -> list[dict]:
    """Remove secondary parallel citations from the list.

    Rules (type-based, no reliance on parallel_cite directionality):
    - regional_reporter (N.W.2d/3d) that has a parallel_cite → drop it
    - federal_reporter matching S.Ct. or L.Ed. → always drop
    - Any citation whose parallel_cite points to a primary already kept
      and the citation itself is a reporter (not neutral/U.S.) → drop
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
    for c in citations:
        norm = c.get("normalized", "")
        ct = c.get("cite_type", "")
        pc = c.get("parallel_cite", "")

        # N.W.2d/3d parallel of a neutral cite → drop
        if ct == "regional_reporter" and _NW_RE.search(norm) and pc:
            skip_norms.add(norm)
            continue

        # S.Ct. → always drop (SCOTUS parallel)
        if ct == "federal_reporter" and _SCT_RE.search(norm):
            skip_norms.add(norm)
            continue

        # L.Ed. → always drop (SCOTUS parallel)
        if ct == "federal_reporter" and _LED_RE.search(norm):
            skip_norms.add(norm)
            continue

        # Old ND cases cited only by N.W.2d (no neutral) with no parallel
        # → keep (e.g., 543 N.W.2d 491 for pre-1997 ND cases)

    removed = len(skip_norms)
    if removed:
        print(f"  Removed {removed} parallel citations", file=sys.stderr)
    return [c for c in citations if c.get("normalized") not in skip_norms]


def _build_html(title: str, citations: list[dict], paragraphs: list[dict],
                file_key: str, opinion_text: str,
                viewers: dict[str, str] | None = None) -> str:
    """Build the self-contained HTML string."""
    viewers = viewers or {}
    # Build a de-duplicated map of local source HTML keyed by local_path.
    # Each citation references into this map by key, avoiding duplication.
    sources_map: dict[str, str] = {}  # local_path → rendered HTML
    for c in citations:
        lp = c.get("local_path")
        if lp and lp not in sources_map and c.get("local_exists"):
            md = _read_local_markdown(lp)
            if md:
                sources_map[lp] = _md_to_html(md)

    # Enrich citation entries
    enriched = []
    for c in citations:
        para = _find_paragraph(paragraphs, c["cite_text"])
        url = c.get("url") or ""
        # For ND opinions with local refs, derive the direct URL
        lp = c.get("local_path")
        if lp and (not url or "?cit1=" in url):
            direct = _nd_direct_url(lp)
            if direct:
                url = direct
        host = urlparse(url).netloc if url else ""
        pinpoint = c.get("pinpoint")
        viewer_path = viewers.get(url) if url else None
        search_term = _pinpoint_search_term(pinpoint) if pinpoint and viewer_path else ""
        lp = c.get("local_path")
        has_source = lp is not None and lp in sources_map
        enriched.append({
            "cite_text": c["cite_text"],
            "cite_type": c.get("cite_type", ""),
            "normalized": c.get("normalized", c["cite_text"]),
            "url": url or None,
            "iframe_ok": host in _IFRAME_OK_DOMAINS,
            "para_num": para["num"] if para else None,
            "search_hint": c.get("search_hint", ""),
            "pinpoint": pinpoint,
            "viewer_path": viewer_path,
            "search_term": search_term,
            "source_key": lp if has_source else None,
        })

    data_json = json.dumps(enriched, ensure_ascii=False)
    sources_json = json.dumps(sources_map, ensure_ascii=False)
    file_key_json = json.dumps(file_key, ensure_ascii=False)

    js = (_JS
          .replace("__DATA__", data_json)
          .replace("__SOURCES__", sources_json)
          .replace("__FILE_KEY__", file_key_json))
    escaped_title = html.escape(title)
    opinion_html = _opinion_to_html(opinion_text, paragraphs)

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
    <div class="sidebar-header">Citations ({len(enriched)})</div>
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
          <span class="ptitle">Source</span>
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
    args = parser.parse_args()

    opinion_path = Path(args.opinion).expanduser()
    if not opinion_path.exists():
        print(f"Error: opinion file not found: {opinion_path}", file=sys.stderr)
        sys.exit(1)

    cite_json_path = Path(args.cite_json).expanduser() if args.cite_json else None
    citations = _load_citations(opinion_path, cite_json_path, args.refs_dir,
                                local_only=args.local_only)

    if not citations:
        print("No citations found.", file=sys.stderr)
        sys.exit(1)

    citations = _dedup_parallel_citations(citations)

    text = opinion_path.read_text(encoding="utf-8")
    paragraphs = _split_paragraphs(text)

    title = args.title or opinion_path.stem
    file_key = opinion_path.stem
    out = Path(args.output)

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

    html_str = _build_html(title, citations, paragraphs, file_key, text, viewers)

    out.write_text(html_str, encoding="utf-8")
    n_viewers = len(viewers)
    extra = f", {n_viewers} PDF viewer(s)" if n_viewers else ""
    print(f"Wrote {out} ({len(citations)} citations{extra})")


if __name__ == "__main__":
    main()

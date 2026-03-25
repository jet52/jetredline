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

    # Or pipe nd_cite_check.py JSON directly:
    python3 cite_review.py --opinion opinion.md --cite-json cites.json \\
        --output cite-review.html
"""

import argparse
import html
import json
import re
import sys
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


def _split_paragraphs(text: str) -> list[dict]:
    """Split opinion text into paragraphs keyed by ¶ number.

    Returns list of {"num": int|None, "text": str}.
    """
    matches = list(_PARA_RE.finditer(text))
    if not matches:
        # No ¶ markers — treat entire text as one block
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

def _opinion_to_html(text: str, paragraphs: list[dict]) -> str:
    """Convert opinion text to HTML fragment with paragraph anchors."""
    if not paragraphs or paragraphs[0]["num"] is None:
        return f'<div class="opinion-text">{html.escape(text)}</div>'

    parts = []
    # Header text before first ¶ marker
    first_match = _PARA_RE.search(text)
    if first_match and first_match.start() > 0:
        header = text[:first_match.start()].strip()
        if header:
            parts.append(
                f'<div class="opinion-header">{html.escape(header)}</div>'
            )

    for p in paragraphs:
        pid = f'para-{p["num"]}' if p["num"] is not None else "para-0"
        escaped = html.escape(p["text"])
        parts.append(
            f'<div class="opinion-para" id="{pid}">'
            f'<span class="para-marker">[¶{p["num"]}]</span> '
            f'{escaped}</div>'
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Citation data
# ---------------------------------------------------------------------------

def _load_citations(opinion_path: Path, cite_json_path: Path | None,
                    refs_dir: str) -> list[dict]:
    """Load citation JSON — from file or by running nd_cite_check."""
    if cite_json_path and cite_json_path.exists():
        return json.loads(cite_json_path.read_text(encoding="utf-8"))

    # Import and run nd_cite_check directly
    skill_dir = Path(__file__).parent
    sys.path.insert(0, str(skill_dir))
    try:
        from nd_cite_check import scan_opinion
        text = opinion_path.read_text(encoding="utf-8")
        return scan_opinion(text, refs_dir=refs_dir)
    finally:
        sys.path.pop(0)


# Domains whose pages can be loaded in an iframe (no X-Frame-Options block)
_IFRAME_OK_DOMAINS = frozenset({
    "www.ndcourts.gov", "ndcourts.gov", "ndlegis.gov",
})


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
  --cite-hl: #5b8def44;
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
.cite-hl {
  background:var(--cite-hl); padding:1px 4px;
  border-radius:3px; border-bottom:2px solid var(--accent);
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
  const STORAGE_KEY = 'cite-review-' + __FILE_KEY__;

  let currentIdx = 0;
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
      '<span class="lbl">' + esc(d.cite_text) + '</span>' +
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

    if (d.url) {
      urlLink.href = d.url;
      urlLink.textContent = d.url.replace(/^https?:\\/\\//, '');
      if (d.iframe_ok) {
        srcBody.innerHTML =
          '<iframe src="' + esc(d.url) + '"></iframe>' +
          '<a class="fallback-link" href="' + esc(d.url) +
          '" target="_blank">Open in new tab</a>';
      } else {
        srcBody.innerHTML =
          '<div class="no-local">' +
          '<p>Source cannot be embedded (site restriction)</p>' +
          '<a class="open-tab-btn" href="' + esc(d.url) +
          '" target="_blank">Open source in new tab &#x2197;</a>' +
          '</div>';
      }
    } else {
      urlLink.href = '#';
      urlLink.textContent = 'no URL available';
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

  function setStatus(status) {
    const cs = getCiteState(currentIdx);
    const newStatus = cs.status === status ? null : status;
    setCiteState(currentIdx, 'status', newStatus);
    updateButtons(newStatus);

    // Update sidebar dot
    const dot = document.querySelectorAll('.cite-item')[currentIdx].querySelector('.dot');
    dot.className = 'dot' + (newStatus ? ' ' + newStatus : '');
    updateProgress();
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
    else if (e.key === 'v') setStatus('verified');
    else if (e.key === 'f') setStatus('flagged');
    else if (e.key === 's') setStatus('skipped');
    else if (e.key === 'n') { e.preventDefault(); document.getElementById('notes-input').focus(); }
    else if (e.key === '?') toggleHelp();
    else if (e.key === 'Escape') closeHelp();
  });

  // Button clicks
  document.querySelector('.v-btn').addEventListener('click', () => setStatus('verified'));
  document.querySelector('.f-btn').addEventListener('click', () => setStatus('flagged'));
  document.querySelector('.s-btn').addEventListener('click', () => setStatus('skipped'));

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

  // Init first citation
  navigate(0);
})();
"""


def _build_html(title: str, citations: list[dict], paragraphs: list[dict],
                file_key: str, opinion_text: str) -> str:
    """Build the self-contained HTML string."""
    # Enrich citation entries
    enriched = []
    for c in citations:
        para = _find_paragraph(paragraphs, c["cite_text"])
        url = c.get("url") or ""
        host = urlparse(url).netloc if url else ""
        enriched.append({
            "cite_text": c["cite_text"],
            "cite_type": c.get("cite_type", ""),
            "normalized": c.get("normalized", c["cite_text"]),
            "url": url or None,
            "iframe_ok": host in _IFRAME_OK_DOMAINS,
            "para_num": para["num"] if para else None,
        })

    data_json = json.dumps(enriched, ensure_ascii=False)
    file_key_json = json.dumps(file_key, ensure_ascii=False)

    js = _JS.replace("__DATA__", data_json).replace("__FILE_KEY__", file_key_json)
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
        <div class="src-body" style="flex:1;display:flex;flex-direction:column;position:relative;">
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
                        help="Path to pre-generated nd_cite_check.py JSON "
                             "(if omitted, runs nd_cite_check internally)")
    parser.add_argument("--refs-dir", default="~/refs",
                        help="Refs directory for nd_cite_check (default: ~/refs)")
    parser.add_argument("--output", default="cite-review.html",
                        help="Output HTML file path (default: cite-review.html)")
    parser.add_argument("--title", "-t", default="",
                        help="Document title for the header")
    args = parser.parse_args()

    opinion_path = Path(args.opinion).expanduser()
    if not opinion_path.exists():
        print(f"Error: opinion file not found: {opinion_path}", file=sys.stderr)
        sys.exit(1)

    cite_json_path = Path(args.cite_json).expanduser() if args.cite_json else None
    citations = _load_citations(opinion_path, cite_json_path, args.refs_dir)

    if not citations:
        print("No citations found.", file=sys.stderr)
        sys.exit(1)

    text = opinion_path.read_text(encoding="utf-8")
    paragraphs = _split_paragraphs(text)

    title = args.title or opinion_path.stem
    file_key = opinion_path.stem

    html_str = _build_html(title, citations, paragraphs, file_key, text)

    out = Path(args.output)
    out.write_text(html_str, encoding="utf-8")
    print(f"Wrote {out} ({len(citations)} citations)")


if __name__ == "__main__":
    main()

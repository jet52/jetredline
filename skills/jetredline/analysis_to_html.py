#!/usr/bin/env python3
"""Render a JetRedline ``-ANALYSIS.md`` report as a readable HTML page.

The analysis report is a triage document: eight or more tables whose value is
concentrated in a handful of rows (the discrepancies, the unaddressed
arguments, the citations not found, the authorities with no copy in the case
file).  In markdown those rows are buried.  This renderer surfaces them.

What it adds over a generic markdown viewer:

  - a triage banner and a sticky table of contents, each carrying per-section
    counts of flagged rows;
  - status badges on the report's three status vocabularies, keyed on *column
    header names* rather than section titles (headings drift, column names
    do not), colorblind-safe and never color-alone;
  - per-table filtering and a "problems only" toggle;
  - a print stylesheet, so print-to-PDF produces a clean chambers document.

Markdown is the source of truth; this is a terminal render step.  Run it
*after* ``provenance.py`` stamps the report, or the footer and the subagent
token table will be missing from the page.

Usage:
    python3 analysis_to_html.py <stem>-ANALYSIS.md [-o out.html]
                                [--cite-review PATH] [--title TEXT] [--check]

Writes ``<stem>-ANALYSIS.html`` beside the input unless ``-o`` says otherwise.
``--check`` additionally verifies that every non-blank source line's text
survived into the page and fails (exit 3) if any did not.

Standard library only — no third-party dependency, no network, and the output
is a single self-contained file.
"""

import argparse
import html
import re
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Inline markdown
# ---------------------------------------------------------------------------

# Code spans and links are pulled out whole before any emphasis pass so that
# a URL containing "*" or "_" can't be mangled into <em>.
# One level of balanced parens in the URL: Wikipedia-style targets and
# ndcourts query strings both carry them.
_URL_PAT = r"(?:[^()\s]|\([^()\s]*\))+"
_TOKEN_RE = re.compile(r"`[^`]+`|\[[^\]]*\]\(" + _URL_PAT + r"\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\((" + _URL_PAT + r")\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)")

_SAFE_SCHEMES = ("http://", "https://", "mailto:")


def _safe_url(url: str) -> str | None:
    """Return the URL if it is safe to emit as an href, else None.

    Anything with a scheme we don't recognize (``javascript:`` above all) is
    rejected; the link then renders as plain text rather than disappearing.
    """
    u = url.strip()
    if not u:
        return None
    low = u.lower()
    if low.startswith(_SAFE_SCHEMES) or u.startswith("#"):
        return u
    if ":" in u.split("/")[0]:
        return None          # some other scheme — refuse
    return u                 # relative path (a sibling file, e.g. the PDF)


def _emphasis(escaped: str) -> str:
    """Apply bold/italic to already-escaped text."""
    out = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    return _ITALIC_RE.sub(r"<em>\1</em>", out)


def render_inline(text: str) -> str:
    """Render one line of inline markdown to HTML.

    Code spans and links are stashed behind sentinels before the emphasis
    pass, so ``**`Id. At`**`` bolds correctly and a URL containing "*" can't
    be mangled into <em>.
    """
    stash: list[str] = []

    def _stash(m: re.Match) -> str:
        tok = m.group(0)
        if tok.startswith("`"):
            rendered = "<code>" + html.escape(tok[1:-1]) + "</code>"
        else:
            lm = _LINK_RE.fullmatch(tok)
            label = _emphasis(html.escape(lm.group(1)))
            url = _safe_url(lm.group(2))
            rendered = (
                f'<a href="{html.escape(url, quote=True)}" rel="noopener">'
                f"{label}</a>" if url else label)
        stash.append(rendered)
        return f"\x00{len(stash) - 1}\x00"

    staged = _TOKEN_RE.sub(_stash, text)
    out = _emphasis(html.escape(staged))
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], out)


def _plain(text: str) -> str:
    """Strip inline markdown to bare text (for status matching and slugs)."""
    t = _LINK_RE.sub(r"\1", text)
    t = t.replace("`", "").replace("**", "").replace("*", "")
    return t.strip()


# ---------------------------------------------------------------------------
# Status vocabularies
#
# Keyed on column header names.  The report's headings get rewritten from run
# to run; its column names are stable, and an unrecognized header simply
# renders as a plain cell.
# ---------------------------------------------------------------------------

_STATUS_HEADERS = {
    "result", "addressed", "quote check", "page check", "supports",
    "caption check", "fair characterization", "fairly characterized",
    "fair char.", "status", "verified", "page verified", "quote verified",
}
_FILE_HEADERS = {"matched file", "source file", "matched pdf"}

# Longest / most specific phrase first: "no quote" must beat bare "no", and
# "unverified" must beat "verified".
_STATUS_PHRASES: list[tuple[str, str]] = [
    ("does not support", "problem"),
    ("not addressed", "problem"),
    ("none found", "problem"),
    ("not found", "problem"),
    ("not verified", "problem"),
    ("discrepancy", "problem"),
    ("contradicted", "problem"),
    ("no quote", "caution"),
    ("unverified", "caution"),
    ("partially", "caution"),
    ("partial", "caution"),
    ("unclear", "caution"),
    ("n/a", "neutral"),
    ("not applicable", "neutral"),
    ("verified", "ok"),
    ("supports", "ok"),
    ("confirmed", "ok"),
    ("yes", "ok"),
    ("no", "problem"),
]

_RANK = {"neutral": 0, "ok": 1, "caution": 2, "problem": 3}
_GLYPH = {"ok": "✓", "caution": "◐", "problem": "✗", "neutral": ""}


def _norm_header(cell: str) -> str:
    h = _plain(cell).lower().strip()
    h = h.rstrip("?").strip()
    return re.sub(r"\s+", " ", h)


def classify_status(cell: str) -> str:
    """Map a status cell to ok / caution / problem / neutral."""
    t = _plain(cell).lower().strip()
    t = t.replace("—", " ").replace("–", " ")
    t = re.sub(r"\s+", " ", t).strip(" .")
    if not t or t in {"-", "--", "—"}:
        return "neutral"
    for phrase, kind in _STATUS_PHRASES:
        if phrase in t:
            return kind
    return "neutral"


def classify_file_cell(cell: str) -> str:
    t = _plain(cell).lower().strip()
    if not t:
        return "neutral"
    if "none" in t or "not found" in t or "no copy" in t:
        return "problem"
    return "neutral"


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_HR_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
_UL_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")
_BQ_RE = re.compile(r"^>\s?(.*)$")
_TABLE_DELIM_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_PROV_RE = re.compile(r"^\*Report generated by .+\*$")
_CREDIT_RE = re.compile(r"^\*Claude skills crafted by .+\*$")
_SENTINEL_RE = re.compile(r"^[–—-]+\s*(Begin|End) Analysis\s*[–—-]+$",
                          re.IGNORECASE)


def _split_row(line: str) -> list[str]:
    """Split a markdown table row into cells, honoring escaped pipes."""
    s = line.strip()
    s = s.replace("\\|", "\x00")
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.replace("\x00", "|").strip() for c in s.split("|")]


def parse_blocks(lines: list[str]) -> list[dict]:
    """Parse markdown into a flat list of block dicts.

    Anything unrecognized falls through as a paragraph — the renderer never
    drops content, it only fails to enrich it.
    """
    blocks: list[dict] = []
    i = 0
    n = len(lines)
    para: list[str] = []

    def flush_para():
        nonlocal para
        if para:
            lines_ = [x.strip() for x in para if x.strip()]
            text = "\n".join(lines_)
            if text:
                if _PROV_RE.match(text):
                    blocks.append({"kind": "provenance", "text": text.strip("*")})
                elif _CREDIT_RE.match(text):
                    blocks.append({"kind": "credit", "text": text.strip("*")})
                else:
                    blocks.append({"kind": "para", "lines": lines_, "text": text})
            para = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        if _SENTINEL_RE.match(stripped):
            flush_para()
            i += 1
            continue

        m = _HEADING_RE.match(stripped)
        if m:
            flush_para()
            blocks.append({"kind": "heading",
                           "level": min(len(m.group(1)), 6),
                           "text": m.group(2).strip()})
            i += 1
            continue

        if _HR_RE.match(line):
            flush_para()
            blocks.append({"kind": "hr"})
            i += 1
            continue

        # Table: a header row followed by a delimiter row.
        if "|" in stripped and i + 1 < n and _TABLE_DELIM_RE.match(lines[i + 1].strip()):
            flush_para()
            header = _split_row(lines[i])
            rows: list[list[str]] = []
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            blocks.append({"kind": "table", "header": header, "rows": rows})
            continue

        if _BQ_RE.match(line):
            flush_para()
            inner: list[str] = []
            while i < n and _BQ_RE.match(lines[i]):
                inner.append(_BQ_RE.match(lines[i]).group(1))
                i += 1
            blocks.append({"kind": "quote", "blocks": parse_blocks(inner)})
            continue

        um, om = _UL_RE.match(line), _OL_RE.match(line)
        if um or om:
            flush_para()
            ordered = om is not None
            items: list[dict] = []
            while i < n:
                um2, om2 = _UL_RE.match(lines[i]), _OL_RE.match(lines[i])
                if not (um2 or om2):
                    # A wrapped continuation line belongs to the item above.
                    if (items and lines[i].strip()
                            and lines[i].startswith((" ", "\t"))):
                        items[-1]["text"] += " " + lines[i].strip()
                        i += 1
                        continue
                    break
                if (om2 is not None) != ordered and not items:
                    ordered = om2 is not None
                body = (om2.group(3) if om2 else um2.group(2)).strip()
                indent = len(om2.group(1) if om2 else um2.group(1))
                tm = _TASK_RE.match(body)
                if tm:
                    items.append({"text": tm.group(2).strip(),
                                  "task": True,
                                  "done": tm.group(1).lower() == "x",
                                  "indent": indent})
                else:
                    items.append({"text": body, "task": False, "indent": indent})
                i += 1
            blocks.append({"kind": "list", "ordered": ordered, "items": items})
            continue

        para.append(line)
        i += 1

    flush_para()
    return blocks


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------

def _slug(text: str, taken: set[str]) -> str:
    t = unicodedata.normalize("NFKD", _plain(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower() or "section"
    base, k = t, 2
    while t in taken:
        t = f"{base}-{k}"
        k += 1
    taken.add(t)
    return t


class Renderer:
    def __init__(self, blocks: list[dict]):
        self.blocks = blocks
        self.sections: list[dict] = []
        self.taken: set[str] = set()
        self.title: str | None = None
        self.table_seq = 0
        self.checkbox_seq = 0
        self.footer: list[str] = []

    # -- section bookkeeping -------------------------------------------------

    def _section(self) -> dict:
        if not self.sections:
            self.sections.append({"id": _slug("report", self.taken),
                                  "title": "", "level": 2, "html": [],
                                  "problems": 0, "cautions": 0, "alert": False,
                                  "in_toc": False})
        return self.sections[-1]

    def _emit(self, html_str: str):
        self._section()["html"].append(html_str)

    # -- blocks --------------------------------------------------------------

    def render(self) -> None:
        for b in self.blocks:
            self._block(b)

    def _block(self, b: dict, into: list[str] | None = None) -> None:
        kind = b["kind"]
        sink = self._emit if into is None else into.append

        if kind == "heading":
            self._heading(b, sink, standalone=into is None)
        elif kind == "para":
            body = "<br>".join(render_inline(x) for x in b.get("lines", [b["text"]]))
            sink(f"<p>{body}</p>")
        elif kind == "hr":
            sink("<hr>")
        elif kind == "list":
            sink(self._list(b))
        elif kind == "table":
            sink(self._table(b))
        elif kind == "quote":
            inner: list[str] = []
            alert = any(x["kind"] == "heading" and "⚠" in x["text"]
                        for x in b["blocks"])
            for sub in b["blocks"]:
                self._block(sub, into=inner)
            cls = "quote alert" if alert else "quote"
            if alert:
                self._section()["alert"] = True
            sink(f'<blockquote class="{cls}">' + "\n".join(inner) + "</blockquote>")
        elif kind == "provenance":
            self.footer.append(
                f'<p class="prov">{render_inline(b["text"])}</p>')
        elif kind == "credit":
            self.footer.append(
                f'<p class="credit">{render_inline(b["text"])}</p>')

    def _heading(self, b: dict, sink, standalone: bool) -> None:
        level, text = b["level"], b["text"]
        alert = "⚠" in text

        if level == 1 and self.title is None and standalone:
            self.title = _plain(text)
            return

        if not standalone:
            lv = min(max(level, 3), 6)
            cls = ' class="alert-h"' if alert else ""
            sink(f"<h{lv}{cls}>{render_inline(text)}</h{lv}>")
            return

        if level <= 2:
            sid = _slug(text, self.taken)
            self.sections.append({"id": sid, "title": _plain(text), "level": 2,
                                  "html": [], "problems": 0, "cautions": 0,
                                  "alert": alert, "in_toc": True})
            return

        sec = self._section()
        sid = _slug(text, self.taken)
        if alert:
            sec["alert"] = True
        cls = " alert-h" if alert else ""
        sec["html"].append(
            f'<h3 id="{sid}" class="sub{cls}">{render_inline(text)}</h3>')

    def _list(self, b: dict) -> str:
        tag = "ol" if b["ordered"] else "ul"
        out = [f'<{tag} class="md">']
        for item in b["items"]:
            if item["task"]:
                self.checkbox_seq += 1
                cid = f"cb{self.checkbox_seq}"
                checked = " checked" if item["done"] else ""
                out.append(
                    f'<li class="task"><label><input type="checkbox" '
                    f'data-cb="{cid}"{checked}> '
                    f'<span>{render_inline(item["text"])}</span></label></li>')
            else:
                out.append(f"<li>{render_inline(item['text'])}</li>")
        out.append(f"</{tag}>")
        return "\n".join(out)

    def _table(self, b: dict) -> str:
        header, rows = b["header"], b["rows"]
        ncols = len(header)
        norm = [_norm_header(h) for h in header]
        status_cols = {i for i, h in enumerate(norm) if h in _STATUS_HEADERS}
        file_cols = {i for i, h in enumerate(norm) if h in _FILE_HEADERS}

        sec = self._section()
        self.table_seq += 1
        tid = f"t{self.table_seq}"

        body: list[str] = []
        n_problem = n_caution = 0
        for row in rows:
            cells = (row + [""] * ncols)[:ncols]
            worst = "neutral"
            tds: list[str] = []
            for idx, cell in enumerate(cells):
                kind = "neutral"
                if idx in status_cols:
                    kind = classify_status(cell)
                elif idx in file_cols:
                    kind = classify_file_cell(cell)
                if _RANK[kind] > _RANK[worst]:
                    worst = kind
                inner = render_inline(cell)
                if kind in ("ok", "caution", "problem"):
                    gly = _GLYPH[kind]
                    inner = (f'<span class="badge b-{kind}">'
                             f'<span class="gly" aria-hidden="true">{gly}</span>'
                             f'{inner}</span>')
                first = ' class="c0"' if idx == 0 else ""
                tds.append(f"<td{first}>{inner}</td>")
            if worst == "problem":
                n_problem += 1
            elif worst == "caution":
                n_caution += 1
            body.append(f'<tr data-status="{worst}">' + "".join(tds) + "</tr>")

        sec["problems"] += n_problem
        sec["cautions"] += n_caution

        ths = "".join(f"<th>{render_inline(h)}</th>" for h in header)
        wide = " wide" if ncols >= 7 else ""
        table = (f'<div class="tbl-scroll"><table class="md{wide}" id="{tid}">'
                 f"<thead><tr>{ths}</tr></thead>"
                 f'<tbody>{"".join(body)}</tbody></table></div>')

        tools = ""
        if len(rows) >= 5 or n_problem or n_caution:
            only = ""
            if status_cols or file_cols:
                only = ('<label class="only"><input type="checkbox" '
                        'class="tbl-only"> Problems only</label>')
            tools = ('<div class="tbl-tools">'
                     '<input type="search" class="tbl-filter" '
                     'placeholder="Filter rows…" aria-label="Filter rows">'
                     f'{only}<span class="tbl-count"></span></div>')

        return f'<div class="tbl-wrap" data-for="{tid}">{tools}{table}</div>'


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

_CSS = """\
:root{
  --bg:#ffffff; --surface:#f6f7f9; --surface-2:#eef1f5;
  --text:#1a1c20; --muted:#5a6069; --border:#d5dae1;
  --accent:#1f4e9c; --accent-soft:#e8eefb;
  --ok:#0b6b5e; --ok-bg:#e0f1ee;
  --caution:#8a5300; --caution-bg:#fbeed6;
  --problem:#8f1d4e; --problem-bg:#fae2ec;
  --serif:Charter,"Bitstream Charter","Iowan Old Style",Georgia,
    "Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,
    sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:var(--serif); font-size:16px; line-height:1.55;
  -webkit-text-size-adjust:100%;
}
a{color:var(--accent);}
a:hover{text-decoration:none;}
code{font-family:var(--mono); font-size:0.88em; background:var(--surface-2);
  padding:1px 4px; border-radius:3px;}

.page{display:grid; grid-template-columns:264px minmax(0,1fr); gap:32px;
  max-width:1400px; margin:0 auto; padding:0 28px 64px;}

/* ---- masthead ---- */
.masthead{grid-column:1/-1; border-bottom:2px solid var(--text);
  padding:26px 0 14px; margin-bottom:24px;}
.masthead .kicker{font-family:var(--sans); font-size:11px; font-weight:700;
  letter-spacing:.13em; text-transform:uppercase; color:var(--muted);}
.masthead h1{font-size:29px; line-height:1.2; margin:6px 0 0; font-weight:600;}

/* ---- table of contents ---- */
nav.toc{position:sticky; top:16px; align-self:start; max-height:calc(100vh - 32px);
  overflow:auto; font-family:var(--sans); font-size:13px; padding-bottom:24px;}
nav.toc .toc-h{font-size:11px; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); margin:0 0 10px;}
nav.toc ol{list-style:none; margin:0; padding:0;}
nav.toc li{margin:0 0 2px;}
nav.toc a{display:flex; gap:8px; align-items:baseline; text-decoration:none;
  color:var(--text); padding:4px 8px; border-radius:4px; border-left:2px solid transparent;}
nav.toc a:hover{background:var(--surface);}
nav.toc a.active{background:var(--accent-soft); border-left-color:var(--accent);
  font-weight:600;}
nav.toc .lbl{flex:1; min-width:0;}
nav.toc .n{font-variant-numeric:tabular-nums; font-size:11px; font-weight:700;
  padding:1px 6px; border-radius:9px;}
.n.problem{background:var(--problem-bg); color:var(--problem);}
.n.caution{background:var(--caution-bg); color:var(--caution);}

/* ---- triage banner ---- */
.banner{border:1px solid var(--border); border-left:4px solid var(--accent);
  background:var(--surface); border-radius:6px; padding:16px 18px;
  margin:0 0 28px; font-family:var(--sans); font-size:14px;}
.banner.clean{border-left-color:var(--ok);}
.banner h2{font-size:13px; letter-spacing:.09em; text-transform:uppercase;
  color:var(--muted); margin:0 0 10px; font-weight:700;}
.tallies{display:flex; flex-wrap:wrap; gap:10px; margin-bottom:10px;}
.tally{display:flex; align-items:baseline; gap:7px; padding:5px 11px;
  border-radius:16px; border:1px solid var(--border); background:var(--bg);}
.tally .v{font-size:17px; font-weight:700; font-variant-numeric:tabular-nums;}
.tally.problem{border-color:var(--problem); color:var(--problem);}
.tally.caution{border-color:var(--caution); color:var(--caution);}
.tally.ok{border-color:var(--ok); color:var(--ok);}
.jump{margin:0; padding:0; list-style:none; display:flex; flex-wrap:wrap; gap:6px;}
.jump li a{display:inline-block; padding:3px 9px; border-radius:12px;
  background:var(--bg); border:1px solid var(--border); font-size:12.5px;
  text-decoration:none;}

/* ---- sections ---- */
section{margin:0 0 34px; scroll-margin-top:16px;}
section > h2{font-family:var(--sans); font-size:18px; font-weight:700;
  margin:0 0 12px; padding-bottom:6px; border-bottom:1px solid var(--border);}
section.alert > h2{border-bottom-color:var(--problem); color:var(--problem);}
h3.sub{font-family:var(--sans); font-size:15px; font-weight:700;
  margin:20px 0 8px; scroll-margin-top:16px;}
h3.alert-h,h4.alert-h{color:var(--problem);}
p{margin:0 0 11px; max-width:74ch;}
ul.md,ol.md{margin:0 0 12px; padding-left:22px; max-width:74ch;}
ul.md li,ol.md li{margin:0 0 6px;}
li.task{list-style:none; margin-left:-20px;}
li.task label{display:flex; gap:8px; align-items:baseline; cursor:pointer;}
blockquote.quote{margin:0 0 14px; padding:12px 16px; border-left:3px solid var(--border);
  background:var(--surface);}
blockquote.quote p{margin-bottom:8px;}
blockquote.quote p:last-child{margin-bottom:0;}
blockquote.alert{border-left-color:var(--problem); background:var(--problem-bg);}
blockquote.alert h3,blockquote.alert h4{margin-top:0; color:var(--problem);}
hr{border:0; border-top:1px solid var(--border); margin:26px 0;}

/* ---- tables ---- */
.tbl-wrap{margin:0 0 18px;}
.tbl-tools{display:flex; align-items:center; gap:12px; margin-bottom:6px;
  font-family:var(--sans); font-size:12.5px; color:var(--muted);}
.tbl-filter{font:inherit; padding:4px 9px; border:1px solid var(--border);
  border-radius:4px; min-width:190px; background:var(--bg); color:var(--text);}
.tbl-tools .only{display:flex; align-items:center; gap:5px; cursor:pointer;
  user-select:none;}
.tbl-count{margin-left:auto; font-variant-numeric:tabular-nums;}
.tbl-scroll{overflow-x:auto; border:1px solid var(--border); border-radius:6px;}
table.md{border-collapse:collapse; width:100%; font-family:var(--sans);
  font-size:13.5px; line-height:1.45;}
table.md.wide{font-size:12.5px;}
table.md th{position:sticky; top:0; background:var(--surface-2); text-align:left;
  font-weight:700; padding:8px 10px; border-bottom:1px solid var(--border);
  white-space:nowrap; z-index:1;}
table.md td{padding:8px 10px; border-bottom:1px solid var(--border);
  vertical-align:top;}
table.md tbody tr:nth-child(even){background:var(--surface);}
table.md tbody tr:last-child td{border-bottom:0;}
table.md td.c0{font-variant-numeric:tabular-nums; white-space:nowrap;
  color:var(--muted);}
table.md tr[data-status="problem"] td.c0{color:var(--problem); font-weight:700;}
tr.hide{display:none;}

/* Badges carry a glyph and their text label; color is never load-bearing. */
.badge{display:inline-flex; gap:5px; align-items:baseline; padding:1px 7px 2px;
  border-radius:10px; font-weight:600; white-space:normal;}
.badge .gly{font-weight:700;}
.b-ok{background:var(--ok-bg); color:var(--ok);}
.b-caution{background:var(--caution-bg); color:var(--caution);}
.b-problem{background:var(--problem-bg); color:var(--problem);}

/* ---- footer ---- */
footer.report{grid-column:1/-1; margin-top:12px; padding-top:14px;
  border-top:1px solid var(--border); font-family:var(--sans); font-size:12px;
  color:var(--muted);}
footer.report p{margin:0 0 4px; max-width:none;}
.prov{font-style:italic;}

@media (max-width:900px){
  .page{grid-template-columns:minmax(0,1fr); gap:0;}
  nav.toc{position:static; max-height:none; margin-bottom:24px;
    border-bottom:1px solid var(--border); padding-bottom:12px;}
}

/* ---- print: this is the chambers deliverable ---- */
@media print{
  @page{margin:0.7in;}
  html,body{background:#fff; color:#000; font-size:10.5pt;}
  .page{display:block; max-width:none; padding:0;}
  nav.toc,.tbl-tools,.jump{display:none !important;}
  .masthead{border-bottom:1.5pt solid #000; padding-top:0;}
  .masthead h1{font-size:19pt;}
  .banner{border:0.5pt solid #000; border-left:2pt solid #000;
    background:transparent; break-inside:avoid;}
  section{break-inside:auto;}
  section > h2{break-after:avoid;}
  h3.sub{break-after:avoid;}
  .tbl-scroll{overflow:visible; border:0.5pt solid #000;}
  table.md{font-size:8.5pt;}
  table.md.wide{font-size:7.6pt;}
  table.md th{position:static; background:#e8e8e8; -webkit-print-color-adjust:exact;
    print-color-adjust:exact;}
  thead{display:table-header-group;}
  tr{break-inside:avoid;}
  tr.hide{display:table-row;}
  .badge{border:0.5pt solid #000; background:transparent !important;
    color:#000 !important; padding:0 3px;}
  blockquote.alert{background:transparent; border-left:2pt solid #000;}
  a{color:#000; text-decoration:none;}
  a[href^="http"]::after{content:" \\003c" attr(href) "\\003e";
    font-size:7.5pt; color:#333; word-break:break-all;}
}
"""

_JS = """\
(function () {
  'use strict';

  // --- per-table filter + problems-only toggle ---
  document.querySelectorAll('.tbl-wrap').forEach(function (wrap) {
    var table = wrap.querySelector('table');
    if (!table) { return; }
    var rows = Array.prototype.slice.call(table.tBodies[0].rows);
    var filter = wrap.querySelector('.tbl-filter');
    var only = wrap.querySelector('.tbl-only');
    var count = wrap.querySelector('.tbl-count');
    var total = rows.length;

    function apply() {
      var q = filter && filter.value ? filter.value.toLowerCase().trim() : '';
      var problemsOnly = !!(only && only.checked);
      var shown = 0;
      rows.forEach(function (tr) {
        var st = tr.getAttribute('data-status');
        var hit = !q || tr.textContent.toLowerCase().indexOf(q) !== -1;
        var keep = hit && (!problemsOnly || st === 'problem' || st === 'caution');
        tr.classList.toggle('hide', !keep);
        if (keep) { shown += 1; }
      });
      if (count) {
        count.textContent = shown === total
          ? total + ' rows'
          : shown + ' of ' + total + ' rows';
      }
    }

    if (filter) { filter.addEventListener('input', apply); }
    if (only) { only.addEventListener('change', apply); }
    apply();
  });

  // --- checkbox worklist, persisted per report ---
  var KEY = 'jetredline-analysis:' + (document.body.dataset.reportKey || 'default');
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; }
  var boxes = document.querySelectorAll('input[data-cb]');
  boxes.forEach(function (box) {
    var id = box.getAttribute('data-cb');
    if (Object.prototype.hasOwnProperty.call(saved, id)) { box.checked = !!saved[id]; }
    box.addEventListener('change', function () {
      saved[id] = box.checked;
      try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) { /* private mode */ }
    });
  });

  // --- table-of-contents scrollspy ---
  var links = {};
  document.querySelectorAll('nav.toc a[href^="#"]').forEach(function (a) {
    links[a.getAttribute('href').slice(1)] = a;
  });
  var sections = document.querySelectorAll('section[id]');
  if (sections.length && 'IntersectionObserver' in window) {
    var visible = {};
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { visible[en.target.id] = en.isIntersecting; });
      var current = null;
      sections.forEach(function (s) { if (!current && visible[s.id]) { current = s.id; } });
      Object.keys(links).forEach(function (id) {
        links[id].classList.toggle('active', id === current);
      });
    }, { rootMargin: '-8% 0px -75% 0px' });
    sections.forEach(function (s) { obs.observe(s); });
  }
}());
"""


def _banner(sections: list[dict], n_tables: int) -> str:
    problems = sum(s["problems"] for s in sections)
    cautions = sum(s["cautions"] for s in sections)
    alerts = [s for s in sections if s["alert"]]
    flagged = [s for s in sections if s["problems"] or s["cautions"]]

    tallies = []
    if problems:
        tallies.append('<span class="tally problem"><span class="v">'
                       f'{problems}</span> flagged rows</span>')
    if cautions:
        tallies.append('<span class="tally caution"><span class="v">'
                       f'{cautions}</span> partial / unverified</span>')
    if not problems and not cautions:
        tallies.append('<span class="tally ok"><span class="v">0</span>'
                       ' flagged rows</span>')
    tallies.append(f'<span class="tally"><span class="v">{n_tables}</span>'
                   " tables</span>")

    jumps = []
    for s in alerts:
        if s["title"]:
            jumps.append(f'<li><a href="#{s["id"]}">⚠ {html.escape(s["title"])}</a></li>')
    for s in flagged:
        if s["alert"] or not s["title"]:
            continue
        bits = []
        if s["problems"]:
            bits.append(f'{s["problems"]} flagged')
        if s["cautions"]:
            bits.append(f'{s["cautions"]} partial')
        jumps.append(f'<li><a href="#{s["id"]}">{html.escape(s["title"])}'
                     f' · {" / ".join(bits)}</a></li>')

    cls = "banner" if (problems or cautions or alerts) else "banner clean"
    head = "Where to look first" if jumps else "Summary"
    body = [f'<div class="{cls}">', f"<h2>{head}</h2>",
            '<div class="tallies">' + "".join(tallies) + "</div>"]
    if jumps:
        body.append('<ul class="jump">' + "".join(jumps) + "</ul>")
    else:
        # Never let "0 flagged" read as a clean bill of health: only columns
        # with a recognized status vocabulary are counted, and a report's
        # findings often live in tables that have none.
        body.append("<p>No table row carries a flagged status. Findings can "
                    "still sit in tables without a status column and in the "
                    "narrative sections below — read on.</p>")
    body.append("</div>")
    return "\n".join(body)


def _toc(sections: list[dict]) -> str:
    items = []
    for s in sections:
        if not s["in_toc"] or not s["title"]:
            continue
        badge = ""
        if s["problems"]:
            badge = f'<span class="n problem">{s["problems"]}</span>'
        elif s["cautions"]:
            badge = f'<span class="n caution">{s["cautions"]}</span>'
        label = ("⚠ " if s["alert"] else "") + html.escape(s["title"])
        items.append(f'<li><a href="#{s["id"]}">'
                     f'<span class="lbl">{label}</span>{badge}</a></li>')
    if not items:
        return ""
    return ('<nav class="toc" aria-label="Contents"><p class="toc-h">Contents</p>'
            "<ol>" + "".join(items) + "</ol></nav>")


def title_from_stem(stem: str) -> str:
    """Turn ``20260004_Burleigh-County-v-Venture_Opinion-ANALYSIS`` into a
    human title.  The tab and the masthead have to name the case."""
    t = re.sub(r"[-_]ANALYSIS$", "", stem, flags=re.IGNORECASE)
    t = t.replace("_", " · ").replace("-", " ")
    return re.sub(r"\s+", " ", t).strip()


def build_page(md_text: str, title: str | None = None,
               cite_review: str | None = None,
               fallback_title: str | None = None) -> str:
    """Render an analysis markdown report to a self-contained HTML page."""
    blocks = parse_blocks(md_text.split("\n"))
    r = Renderer(blocks)
    r.render()

    doc_title = (title or r.title or fallback_title or "JetRedline Analysis")

    body: list[str] = []
    for s in r.sections:
        if not s["html"]:
            continue
        cls = ' class="alert"' if s["alert"] else ""
        head = (f'<h2>{html.escape(s["title"])}</h2>' if s["title"] else "")
        body.append(f'<section id="{s["id"]}"{cls}>{head}'
                    + "\n".join(s["html"]) + "</section>")

    links = ""
    if cite_review:
        links = ('<p class="jump-cite"><a href="'
                 + html.escape(cite_review, quote=True)
                 + '">Open the citation review page →</a></p>')

    footer = ("<footer class=\"report\">" + "\n".join(r.footer) + "</footer>"
              if r.footer else "")

    key = _slug(doc_title, set())
    esc_title = html.escape(doc_title)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc_title}</title>
<style>
{_CSS}</style>
</head>
<body data-report-key="{html.escape(key, quote=True)}">
<div class="page">
  <header class="masthead">
    <div class="kicker">JetRedline Analysis</div>
    <h1>{esc_title}</h1>
  </header>
{_toc(r.sections)}
  <main>
{_banner(r.sections, r.table_seq)}
{links}
{chr(10).join(body)}
  </main>
{footer}
</div>
<script>
{_JS}</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")


def _norm_probe(s: str) -> str:
    """Normalize for the coverage comparison.

    Whitespace, emphasis markers, and backticks are syntax on the markdown
    side and absent (or re-wrapped) on the HTML side; comparing without them
    is what keeps the check honest about real content loss instead of
    reporting phantom misses.
    """
    return re.sub(r"[\s*`]+", "", s)


def coverage_misses(md_text: str, page: str) -> list[tuple[int, str]]:
    """Return (line_number, probe) for source lines whose text is missing.

    The renderer's one hard invariant is that it never silently drops
    content.  For each non-blank source line we take its longest run of
    ordinary characters and confirm it survived into the page text.
    """
    # Compare whitespace-free: stripping tags splices words together
    # ("<em>Martinez</em>," -> "Martinez,") and paragraphs are re-wrapped,
    # so any space-sensitive comparison reports phantom losses.
    text = _norm_probe(html.unescape(_TAG_RE.sub("", page)))
    misses: list[tuple[int, str]] = []
    for lineno, raw in enumerate(md_text.split("\n"), 1):
        line = raw.strip()
        if not line or _SENTINEL_RE.match(line):
            continue
        # Drop list markers before probing: an <ol> renders "1." as chrome,
        # not as text, so a probe carrying the marker never matches.
        stripped = _plain(line).lstrip("#>| ").strip()
        stripped = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", stripped)
        stripped = re.sub(r"^\[[ xX]\]\s+", "", stripped).strip()
        if _TABLE_DELIM_RE.match(line) or _HR_RE.match(line):
            continue
        runs = [x for x in re.split(r"[|`*_\[\]()<>]+", stripped) if len(x.strip()) >= 14]
        if not runs:
            continue
        probe = max(runs, key=len).strip()
        if _norm_probe(probe) not in text:
            misses.append((lineno, re.sub(r"\s+", " ", probe)[:70]))
    return misses


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render a JetRedline -ANALYSIS.md report as HTML")
    ap.add_argument("input", help="path to the -ANALYSIS.md report")
    ap.add_argument("-o", "--output", help="output .html path "
                    "(default: input with .html suffix)")
    ap.add_argument("--title", help="page title (default: first H1, else filename)")
    ap.add_argument("--cite-review", help="path to the -CITE-REVIEW.html page "
                    "to link from the report")
    ap.add_argument("--check", action="store_true",
                    help="verify every source line survived into the page")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.is_file():
        print(f"error: no such file: {src}", file=sys.stderr)
        return 1

    md_text = src.read_text(encoding="utf-8")
    page = build_page(md_text, title=args.title or None,
                      cite_review=args.cite_review,
                      fallback_title=title_from_stem(src.stem))

    out = Path(args.output) if args.output else src.with_suffix(".html")
    out.write_text(page, encoding="utf-8")

    blocks = parse_blocks(md_text.split("\n"))
    r = Renderer(blocks)
    r.render()
    problems = sum(s["problems"] for s in r.sections)
    cautions = sum(s["cautions"] for s in r.sections)
    sections = sum(1 for s in r.sections if s["in_toc"] and s["title"])

    print(f"analysis_to_html: wrote {out} "
          f"({sections} sections, {r.table_seq} tables, "
          f"{problems} flagged rows, {cautions} partial/unverified)")

    if args.check:
        misses = coverage_misses(md_text, page)
        if misses:
            print(f"analysis_to_html: {len(misses)} source line(s) missing "
                  f"from the page:", file=sys.stderr)
            for lineno, probe in misses[:20]:
                print(f"  line {lineno}: {probe}", file=sys.stderr)
            return 3
        print("analysis_to_html: coverage check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

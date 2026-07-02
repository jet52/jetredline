#!/usr/bin/env python3
"""Extract plain-text/markdown from a .docx draft for JetRedline.

Deterministic .docx -> markdown conversion so the draft's text never has to
be transcribed through model context.  Operates on the ZIP archive directly
(zipfile + defusedxml), like apply_edits.py — no unpack/pack pipeline, no
dependency on the docx plugin.

Behavior:
    - Paragraphs are emitted in document order, separated by blank lines
      (table-cell paragraphs included; text boxes are skipped).
    - Tracked changes resolve to the "as accepted" view: inserted text
      (w:ins) is included, deleted text (w:delText) is excluded.
    - Footnotes become markdown references: [^3] in the body, with
      "[^3]: text" definitions appended after a --- separator.
    - Literal paragraph markers ("[¶ 12]", "¶12") pass through untouched.
      When the draft instead uses Word automatic numbering, the visible
      marker is reconstructed from numbering.xml (lvlText + counters) and
      prefixed to each numbered paragraph, so downstream tools
      (cite_check.py / cite_review.py) see the same ¶ numbers Word shows.
      Numbering attached through paragraph styles (e.g. the ND chambers
      template's MainBody style, "[¶%1]") is resolved down the basedOn
      chain; numId=0 (how BlockQuote/continuation styles disable
      numbering) suppresses the marker.
    - Field instruction text (w:instrText), comment/text-box content, and
      mc:Fallback duplicates are excluded.

Usage:
    python extract_text.py --input draft.docx [--output draft.md]

Without --output, markdown goes to stdout.  A one-line summary always goes
to stderr, including whether the input already carries tracked changes.

Exit codes:
    0 — success
    2 — argument/setup error (missing file, not a .docx, no document.xml)
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

import defusedxml.minidom

# Subtrees whose text must not leak into the extraction (by localName).
_SKIP_SUBTREES = {
    "pPr",          # paragraph properties (numbering lvlText lives elsewhere)
    "rPr",          # run properties
    "txbxContent",  # text boxes (classic VML and DrawingML both wrap in this)
    "Fallback",     # mc:Fallback — duplicate of mc:Choice content
    "instrText",    # field codes (e.g. " HYPERLINK ... ")
    "delInstrText",
    "delText",      # tracked deletions — extraction is the "as accepted" view
}

_LITERAL_PARA_MARKER_RE = re.compile(r"^\[?¶\s*\d+")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _local_name(node) -> str:
    return node.localName or ""


def _para_text(para_elem, footnote_refs: list) -> str:
    """Concatenate the visible text of one w:p, in document order.

    Appends any footnote-reference ids encountered to ``footnote_refs`` and
    emits a markdown [^id] marker in their place.
    """
    parts: list[str] = []

    def walk(node):
        for child in node.childNodes:
            if child.nodeType != child.ELEMENT_NODE:
                continue
            name = _local_name(child)
            if name in _SKIP_SUBTREES:
                continue
            if name == "p" and child is not para_elem:
                # Nested paragraph (shouldn't survive _SKIP_SUBTREES, but
                # never merge another paragraph's text into this one).
                continue
            if name == "t":
                parts.append("".join(
                    t.data for t in child.childNodes
                    if t.nodeType in (t.TEXT_NODE, t.CDATA_SECTION_NODE)))
            elif name == "tab":
                parts.append("\t")
            elif name in ("br", "cr"):
                parts.append("\n")
            elif name == "noBreakHyphen":
                parts.append("-")
            elif name == "footnoteReference":
                ref_id = child.getAttribute("w:id")
                if ref_id:
                    footnote_refs.append(ref_id)
                    parts.append(f"[^{ref_id}]")
            else:
                walk(child)

    walk(para_elem)
    return "".join(parts)


def _body_paragraphs(dom) -> list:
    """All w:p elements in document order, excluding text-box content."""
    paras = []
    for p in dom.getElementsByTagName("w:p"):
        node = p.parentNode
        skip = False
        while node is not None and node.nodeType == node.ELEMENT_NODE:
            if _local_name(node) in ("txbxContent", "Fallback"):
                skip = True
                break
            node = node.parentNode
        if not skip:
            paras.append(p)
    return paras


# ---------------------------------------------------------------------------
# Automatic-numbering reconstruction (numbering.xml)
# ---------------------------------------------------------------------------

def _int_to_roman(n: int) -> str:
    vals = ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"),
            (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"),
            (5, "v"), (4, "iv"), (1, "i"))
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def _int_to_letter(n: int) -> str:
    # 1 -> a, 26 -> z, 27 -> aa (Word wraps this way)
    out = []
    n -= 1
    while True:
        out.append(chr(ord("a") + n % 26))
        n = n // 26 - 1
        if n < 0:
            break
    return "".join(reversed(out))


def _format_counter(value: int, num_fmt: str) -> str | None:
    if num_fmt == "decimal":
        return str(value)
    if num_fmt == "lowerLetter":
        return _int_to_letter(value)
    if num_fmt == "upperLetter":
        return _int_to_letter(value).upper()
    if num_fmt == "lowerRoman":
        return _int_to_roman(value)
    if num_fmt == "upperRoman":
        return _int_to_roman(value).upper()
    if num_fmt == "none":
        return ""
    return None  # bullet / unsupported format — no marker


def _first_val(elem, tag: str) -> str | None:
    nodes = elem.getElementsByTagName(tag)
    return nodes[0].getAttribute("w:val") if nodes else None


class _Numbering:
    """Minimal resolver for Word list numbering.

    Handles the shapes that occur in opinion/memo drafts: per-level numFmt,
    start, lvlText (with %k placeholders), and w:num startOverride.  Counters
    nest: incrementing a level resets deeper levels of the same numId.
    """

    def __init__(self, xml_bytes: bytes | None):
        # abstractNumId -> {ilvl -> {"fmt", "start", "text"}}
        self._abstract: dict[str, dict[int, dict]] = {}
        # numId -> (abstractNumId, {ilvl -> start_override})
        self._nums: dict[str, tuple[str, dict[int, int]]] = {}
        # (numId, ilvl) -> current counter value
        self._counters: dict[tuple[str, int], int] = {}
        if xml_bytes:
            self._parse(xml_bytes)

    def _parse(self, xml_bytes: bytes) -> None:
        dom = defusedxml.minidom.parseString(xml_bytes)
        for an in dom.getElementsByTagName("w:abstractNum"):
            an_id = an.getAttribute("w:abstractNumId")
            levels = {}
            for lvl in an.getElementsByTagName("w:lvl"):
                ilvl = int(lvl.getAttribute("w:ilvl") or 0)
                start = _first_val(lvl, "w:start")
                levels[ilvl] = {
                    "fmt": _first_val(lvl, "w:numFmt") or "decimal",
                    "start": int(start) if start else 1,
                    "text": _first_val(lvl, "w:lvlText") or "%1.",
                }
            self._abstract[an_id] = levels
        for num in dom.getElementsByTagName("w:num"):
            num_id = num.getAttribute("w:numId")
            abstract_id = _first_val(num, "w:abstractNumId")
            overrides = {}
            for ov in num.getElementsByTagName("w:lvlOverride"):
                ilvl = int(ov.getAttribute("w:ilvl") or 0)
                so = _first_val(ov, "w:startOverride")
                if so:
                    overrides[ilvl] = int(so)
            if abstract_id is not None:
                self._nums[num_id] = (abstract_id, overrides)

    def _level(self, num_id: str, ilvl: int) -> dict | None:
        entry = self._nums.get(num_id)
        if not entry:
            return None
        return self._abstract.get(entry[0], {}).get(ilvl)

    def _start(self, num_id: str, ilvl: int) -> int:
        entry = self._nums.get(num_id)
        if entry and ilvl in entry[1]:
            return entry[1][ilvl]
        level = self._level(num_id, ilvl)
        return level["start"] if level else 1

    def marker(self, num_id: str, ilvl: int) -> str | None:
        """Advance the counter for (num_id, ilvl) and render the marker."""
        level = self._level(num_id, ilvl)
        if level is None:
            return None
        key = (num_id, ilvl)
        if key in self._counters:
            self._counters[key] += 1
        else:
            self._counters[key] = self._start(num_id, ilvl)
        # Incrementing a level restarts deeper levels of the same list.
        for other_id, other_lvl in list(self._counters):
            if other_id == num_id and other_lvl > ilvl:
                del self._counters[(other_id, other_lvl)]

        def sub(m):
            k = int(m.group(1))
            value = self._counters.get((num_id, k - 1))
            if value is None:
                value = self._start(num_id, k - 1)
            lvl_k = self._level(num_id, k - 1) or {"fmt": "decimal"}
            rendered = _format_counter(value, lvl_k["fmt"])
            return rendered if rendered is not None else ""

        if _format_counter(1, level["fmt"]) is None:
            return None  # bullet or unsupported — omit marker
        return re.sub(r"%(\d)", sub, level["text"])


def _parse_styles(xml_bytes: bytes | None) -> dict[str, dict]:
    """Map styleId -> {basedOn, numId, ilvl} for paragraph styles.

    numId/ilvl are the style's own w:numPr contributions (either may be
    None — Word merges them down the basedOn chain, e.g. Heading2 supplies
    only ilvl and inherits numId from Heading1).
    """
    styles: dict[str, dict] = {}
    if not xml_bytes:
        return styles
    dom = defusedxml.minidom.parseString(xml_bytes)
    for style in dom.getElementsByTagName("w:style"):
        if style.getAttribute("w:type") != "paragraph":
            continue
        style_id = style.getAttribute("w:styleId")
        entry = {"basedOn": _first_val(style, "w:basedOn"),
                 "numId": None, "ilvl": None}
        for numpr in style.getElementsByTagName("w:numPr"):
            entry["numId"] = _first_val(numpr, "w:numId")
            ilvl = _first_val(numpr, "w:ilvl")
            entry["ilvl"] = int(ilvl) if ilvl is not None else None
            break
        styles[style_id] = entry
    return styles


def _para_num_pr(para_elem, styles: dict[str, dict]) -> tuple[str, int] | None:
    """Resolve the paragraph's effective (numId, ilvl), or None.

    Word semantics: direct w:numPr on the paragraph overrides the paragraph
    style; missing pieces (numId or ilvl) fall through to the pStyle's
    basedOn chain.  numId="0" turns numbering off (how templates make
    block-quote/continuation styles unnumbered).
    """
    num_id = None
    ilvl = None
    style_id = None
    for ppr in para_elem.getElementsByTagName("w:pPr"):
        if ppr.parentNode is not para_elem:
            continue
        style_id = _first_val(ppr, "w:pStyle")
        for numpr in ppr.getElementsByTagName("w:numPr"):
            num_id = _first_val(numpr, "w:numId")
            lvl = _first_val(numpr, "w:ilvl")
            ilvl = int(lvl) if lvl is not None else None
            break
        break
    seen = set()
    while style_id and style_id in styles and style_id not in seen:
        seen.add(style_id)
        entry = styles[style_id]
        if num_id is None and entry["numId"] is not None:
            num_id = entry["numId"]
        if ilvl is None and entry["ilvl"] is not None:
            ilvl = entry["ilvl"]
        style_id = entry["basedOn"]
    if not num_id or num_id == "0":
        return None
    return num_id, ilvl if ilvl is not None else 0


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------

def _extract_footnotes(xml_bytes: bytes) -> dict[str, str]:
    """Map footnote id -> text (skipping separator/continuation stubs)."""
    dom = defusedxml.minidom.parseString(xml_bytes)
    notes = {}
    for fn in dom.getElementsByTagName("w:footnote"):
        if fn.getAttribute("w:type") in ("separator", "continuationSeparator"):
            continue
        fn_id = fn.getAttribute("w:id")
        parts = []
        for p in fn.getElementsByTagName("w:p"):
            text = _para_text(p, footnote_refs=[]).strip()
            if text:
                parts.append(text)
        if fn_id and parts:
            notes[fn_id] = " ".join(parts)
    return notes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def extract(docx_path: Path) -> tuple[str, dict]:
    """Extract markdown text from a .docx.  Returns (markdown, summary)."""
    with zipfile.ZipFile(docx_path) as zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise ValueError("no word/document.xml — not a .docx?")
        doc_bytes = zf.read("word/document.xml")
        numbering_bytes = (zf.read("word/numbering.xml")
                           if "word/numbering.xml" in names else None)
        footnotes_bytes = (zf.read("word/footnotes.xml")
                           if "word/footnotes.xml" in names else None)
        styles_bytes = (zf.read("word/styles.xml")
                        if "word/styles.xml" in names else None)

    dom = defusedxml.minidom.parseString(doc_bytes)
    paras = _body_paragraphs(dom)

    # Extract raw text first; synthesize numbering only when the draft has
    # no literal ¶ markers of its own.
    footnote_refs: list[str] = []
    extracted: list[tuple[object, str]] = []
    literal_markers = 0
    for p in paras:
        text = _para_text(p, footnote_refs)
        if _LITERAL_PARA_MARKER_RE.match(text.lstrip()):
            literal_markers += 1
        extracted.append((p, text))

    numbering = _Numbering(numbering_bytes)
    styles = _parse_styles(styles_bytes)
    synthesize = literal_markers < 3
    lines = []
    synthesized = 0
    for p, text in extracted:
        marker = None
        if synthesize:
            num_pr = _para_num_pr(p, styles)
            if num_pr:
                marker = numbering.marker(*num_pr)
                if marker:
                    synthesized += 1
        if marker:
            text = f"{marker} {text.lstrip()}"
        if text.strip():
            lines.append(text.rstrip())

    footnotes = _extract_footnotes(footnotes_bytes) if footnotes_bytes else {}
    body = "\n\n".join(lines)
    used = [fid for fid in footnote_refs if fid in footnotes]
    if used:
        defs = "\n".join(f"[^{fid}]: {footnotes[fid]}" for fid in used)
        body = f"{body}\n\n---\n\n{defs}"

    summary = {
        "paragraphs": len(lines),
        "footnotes": len(used),
        "literal_para_markers": literal_markers,
        "synthesized_numbering": synthesized,
        "tracked_insertions": len(dom.getElementsByTagName("w:ins")),
        "tracked_deletions": len(dom.getElementsByTagName("w:del")),
    }
    return body + "\n", summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract markdown text from a .docx draft")
    parser.add_argument("--input", required=True, help="path to .docx")
    parser.add_argument("--output", help="markdown output path (default: stdout)")
    args = parser.parse_args()

    docx_path = Path(args.input)
    if not docx_path.is_file():
        print(f"error: {docx_path} not found", file=sys.stderr)
        return 2
    try:
        markdown, summary = extract(docx_path)
    except (zipfile.BadZipFile, ValueError, KeyError) as exc:
        print(f"error: cannot extract {docx_path}: {exc}", file=sys.stderr)
        return 2

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        sys.stdout.write(markdown)

    tracked = summary["tracked_insertions"] + summary["tracked_deletions"]
    tracked_note = (f"; input has {summary['tracked_insertions']} tracked "
                    f"insertions / {summary['tracked_deletions']} deletions "
                    f"(extracted as-accepted)" if tracked else "")
    print(f"extracted {summary['paragraphs']} paragraphs, "
          f"{summary['footnotes']} footnotes "
          f"({summary['literal_para_markers']} literal ¶ markers, "
          f"{summary['synthesized_numbering']} numbers synthesized)"
          f"{tracked_note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

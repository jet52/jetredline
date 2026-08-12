#!/usr/bin/env python3
"""Work with supplied source PDFs: probe, locate pages, extract, compact.

Supporting a *supplied authority* — a convention journal, a treatise, a
periodical, an archival volume sitting in the project directory — means
answering four questions that have nothing to do with citation parsing:

1. Can this file be read at all, and is its text layer trustworthy?
2. Which PDF page holds printed page 1522?
3. Can I pull just that page out as a small standalone file?
4. Will it still be small enough to embed once I do?

Each was done by hand with one-off shell commands before this module existed,
and each has a failure mode that is quiet rather than loud.

Design notes earned the hard way
--------------------------------
**Printed page != PDF page, and filenames lie.** Three volumes of one scanned
set, named `-1`, `-2`, `-3`, had printed-page offsets of 628, 1145, and 633:
the names were simply wrong about which volume each held, and a cited page was
in none of the file its name implied. :func:`locate` measures the offset rather
than trusting anything, and reports a confidence with it.

**Running heads contain numbers that are not page numbers.** A head reading
"Jan. 23, 1879. OF THE CONSTITUTIONAL CONVENTION. 1033" offers both 1879 and
1033. Rather than guess per page, :func:`locate` collects every candidate from
several sampled pages and picks the offset that the most pages agree on. A year
appears at a constant *value* across pages, so it yields a different offset on
each one and loses; a real page number increments with the PDF page, so its
offset is constant and wins.

**Big and damaged files defeat the usual tools.** Record packets above 2 GB
carry a cross-reference offset that overflows a signed 32-bit integer; pypdf
raises and qpdf fails its reconstruction, while poppler reads the same file
without complaint. Every extraction path here falls back to poppler.

**A silent no-op is worse than an error.** ``ocrmypdf --skip-text`` skips any
page that already carries text, so on a corrupt layer it exits 0 and changes
nothing. Text-layer state comes from :mod:`textquality`, which distinguishes
"missing" from "present but garbage" and picks the flag accordingly.

CLI::

    pdfsource.py probe   FILE...
    pdfsource.py locate  FILE [--sample N] [--json]
    pdfsource.py extract FILE --pages 1522-1523 [--printed] [-o OUT]
                              [--ocr] [--max-bytes N]
    pdfsource.py compact FILE -o OUT [--max-bytes N]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

try:
    import textquality
except ImportError:  # standalone use
    textquality = None

__all__ = [
    "probe", "locate", "extract", "compact",
    "page_count", "page_text", "LocateResult",
]

#: Pages sampled by `locate` before giving up on agreement.
DEFAULT_SAMPLES = 6

#: Default ceiling for `compact`. Sidecar viewers base64 the file, inflating
#: it by a third, so a few MB per authority is the practical limit.
DEFAULT_MAX_BYTES = 3_000_000

#: Render resolution for OCR probes. Enough for a running head; higher is
#: slower without being more accurate on 10-point type.
PROBE_DPI = 150


def _which(*names: str) -> dict[str, str | None]:
    return {n: shutil.which(n) for n in names}


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def page_count(path: Path) -> int | None:
    """Page count via pdfinfo, falling back to pypdf.

    pdfinfo first because poppler tolerates the damaged and oversized files
    that make pypdf raise.
    """
    tools = _which("pdfinfo")
    if tools["pdfinfo"]:
        p = _run([tools["pdfinfo"], str(path)], timeout=120)
        if p:
            for line in p.stdout.decode("utf-8", "replace").splitlines():
                if line.startswith("Pages:"):
                    try:
                        return int(line.split(":", 1)[1].strip())
                    except ValueError:
                        pass
    try:
        import pypdf
        return len(pypdf.PdfReader(str(path)).pages)
    except Exception:
        return None


def page_text(path: Path, page: int, ocr_fallback: bool = True) -> str:
    """Text of a single PDF page (1-indexed).

    Uses the embedded text layer when there is one; renders and OCRs the page
    when there is not. Returns "" if neither is possible.
    """
    tools = _which("pdftotext", "pdftoppm", "tesseract")
    if tools["pdftotext"]:
        p = _run([tools["pdftotext"], "-f", str(page), "-l", str(page),
                  str(path), "-"], timeout=120)
        if p:
            txt = p.stdout.decode("utf-8", "replace").strip()
            if len(txt) >= 20:
                return txt
    if not ocr_fallback or not (tools["pdftoppm"] and tools["tesseract"]):
        return ""
    with tempfile.TemporaryDirectory() as td:
        stem = str(Path(td) / "pg")
        if not _run([tools["pdftoppm"], "-r", str(PROBE_DPI), "-f", str(page),
                     "-l", str(page), "-png", "-singlefile", str(path), stem],
                    timeout=180):
            return ""
        img = Path(stem + ".png")
        if not img.exists():
            return ""
        p = _run([tools["tesseract"], str(img), "stdout"], timeout=180)
        return p.stdout.decode("utf-8", "replace").strip() if p else ""


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

def probe(path: Path) -> dict:
    """Health report for one PDF: size, pages, text-layer state, readability."""
    path = Path(path)
    out: dict = {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "pages": None,
        "text_state": "unknown",
        "text_quality": None,
        "ocr_args": None,
        "readable_by": [],
        "notes": [],
    }
    if not out["exists"]:
        out["notes"].append("file not found")
        return out

    out["pages"] = page_count(path)
    if out["pages"]:
        out["readable_by"].append("poppler")
    try:
        import pypdf
        pypdf.PdfReader(str(path))
        out["readable_by"].append("pypdf")
    except Exception as e:
        # The >2GB xref overflow lands here; poppler still works, so this is a
        # routing note, not a failure.
        out["notes"].append(f"pypdf cannot open it ({type(e).__name__}); "
                            "use the poppler extraction path")

    if textquality is not None:
        tq = textquality.score_pdf(path)
        out["text_state"] = tq.get("state", "unknown")
        out["text_quality"] = tq.get("quality")
        out["ocr_args"] = tq.get("ocr_args")
        if tq.get("reason"):
            out["notes"].append(tq["reason"])
    else:
        out["notes"].append("textquality unavailable; text layer not scored")
    return out


# ---------------------------------------------------------------------------
# locate
# ---------------------------------------------------------------------------

class LocateResult(dict):
    """Offset between printed page numbers and PDF page numbers.

    ``offset`` satisfies ``pdf_page = printed_page - offset``.
    """

    @property
    def offset(self) -> int | None:
        return self.get("offset")

    def pdf_page(self, printed: int) -> int | None:
        return None if self.offset is None else printed - self.offset

    def printed_page(self, pdf: int) -> int | None:
        return None if self.offset is None else pdf + self.offset

    def contains(self, printed: int) -> bool:
        """Whether the cited printed page can exist in this file at all.

        This is the check that catches a mislabeled volume: a file whose
        measured range cannot hold the cited page is not the right file, no
        matter what its name or metadata claims.
        """
        p = self.pdf_page(printed)
        return bool(p and self.get("pages") and 1 <= p <= self["pages"])


_RUNNING_NUM_RE = re.compile(r"\b(\d{1,5})\b")


def _candidates(text: str) -> list[int]:
    """Page-number candidates from a page's running head and foot.

    Only the outer few lines are considered — a number in the body is prose,
    not pagination. Three lines rather than one because OCR of a scan often
    prepends a line of speckle noise above the true running head.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    edge = lines[:3] + lines[-3:]
    out: list[int] = []
    for ln in edge:
        for m in _RUNNING_NUM_RE.finditer(ln):
            n = int(m.group(1))
            if 1 <= n <= 99999:
                out.append(n)
    return out


def locate(path: Path, samples: int = DEFAULT_SAMPLES,
           pages: int | None = None) -> LocateResult:
    """Measure the printed-page to PDF-page offset.

    Samples *adjacent pairs* of pages and looks for a number on one page whose
    successor appears on the next. A folio increments in step with the PDF
    page; nothing else on the page does.

    That pairing is what makes this work on scans. Single-page voting is too
    weak: on a poorly-OCR'd volume most sampled pages yield only footnote
    markers and the year from the running head, so the one page that does
    surface a real folio can never accumulate a majority. A year is *constant*
    across pages, so it fails the +1 test outright — which is precisely the
    contamination that defeats reading any single page in isolation.

    Falls back to modal single-page voting when no pair agrees, and requires a
    non-negative offset there: front matter means printed >= PDF page in
    essentially every bound volume.
    """
    path = Path(path)
    total = pages if pages is not None else page_count(path)
    res = LocateResult({
        "path": str(path), "pages": total, "offset": None,
        "confidence": 0.0, "votes": 0, "sampled": 0, "method": None,
        "evidence": [],
    })
    if not total or total < 1:
        return res

    # Skip the first few leaves: covers, plates and title pages are unnumbered
    # and contribute only noise.
    lo = min(total, 6)
    hi = max(lo, total - 1)          # leave room for the pair's second page
    n_pairs = max(2, samples // 2)
    if hi <= lo:
        starts = [lo]
    else:
        step = max(1, (hi - lo) // n_pairs)
        starts = list(range(lo, hi + 1, step))[:n_pairs]

    tally: Counter[int] = Counter()
    pair_votes: Counter[int] = Counter()
    evidence: list[dict] = []
    for pg in starts:
        a_txt = page_text(path, pg)
        b_txt = page_text(path, pg + 1) if pg + 1 <= total else ""
        a = _candidates(a_txt)
        b = set(_candidates(b_txt))
        if a_txt:
            res["sampled"] += 1
        for n in set(a):
            if n - pg >= 0:
                tally[n - pg] += 1
            if n + 1 in b:            # consecutive folios: a real page number
                pair_votes[n - pg] += 1
        evidence.append({"pdf_page": pg,
                         "candidates": sorted(set(a))[:6],
                         "next_page_candidates": sorted(b)[:6]})

    res["evidence"] = evidence

    if pair_votes:
        offset, votes = pair_votes.most_common(1)[0]
        conf = min(1.0, 0.6 + 0.2 * votes)
        res["offsets_seen"] = sorted(pair_votes)
        if len(pair_votes) > 1:
            # Different parts of the volume disagree. Usually an inserted plate
            # or a numbering restart, so the offset is not constant and a page
            # lookup far from a sampled pair may be off by a few. Say so rather
            # than report a single number as though it held throughout.
            spread = max(pair_votes) - min(pair_votes)
            conf = round(conf * (votes / sum(pair_votes.values())), 3)
            res["note"] = (f"pagination is not constant: offsets "
                           f"{sorted(pair_votes)} observed (spread {spread}); "
                           "page lookups may be off by that much")
        res.update(offset=offset, votes=votes, method="adjacent-pair",
                   confidence=round(conf, 3))
        return res

    if tally:
        offset, votes = tally.most_common(1)[0]
        if votes >= 2:
            res.update(offset=offset, votes=votes, method="modal-vote",
                       confidence=round(votes / max(1, res["sampled"]), 3))
    return res


# ---------------------------------------------------------------------------
# extract / compact
# ---------------------------------------------------------------------------

def extract(path: Path, first: int, last: int, out: Path,
            printed: bool = False, offset: int | None = None,
            ocr: bool = False, max_bytes: int | None = None) -> dict:
    """Pull a page range into a standalone PDF.

    ``first``/``last`` are PDF pages unless ``printed`` is set, in which case
    they are printed page numbers and are converted using ``offset`` (measured
    by :func:`locate` when not supplied).

    Tries qpdf, then poppler's pdfseparate/pdfunite. Optionally OCRs the result
    and compacts it to ``max_bytes``.
    """
    path, out = Path(path), Path(out)
    info: dict = {"source": str(path), "output": str(out), "ok": False,
                  "method": None, "printed_range": None, "pdf_range": None,
                  "notes": []}

    if printed:
        if offset is None:
            loc = locate(path)
            offset = loc.offset
            info["notes"].append(
                f"measured offset {offset} (confidence {loc['confidence']})"
                if offset is not None else "offset could not be measured")
        if offset is None:
            return info
        info["printed_range"] = [first, last]
        first, last = first - offset, last - offset

    total = page_count(path)
    if total and (first < 1 or last > total or first > last):
        info["notes"].append(
            f"page range {first}-{last} is outside the file's 1-{total}")
        return info
    info["pdf_range"] = [first, last]
    out.parent.mkdir(parents=True, exist_ok=True)

    tools = _which("qpdf", "pdfseparate", "pdfunite")
    if tools["qpdf"]:
        p = _run([tools["qpdf"], "--empty", "--pages", str(path),
                  f"{first}-{last}", "--", str(out)], timeout=600)
        if p and out.exists() and out.stat().st_size > 0:
            info["ok"], info["method"] = True, "qpdf"
    if not info["ok"] and tools["pdfseparate"] and tools["pdfunite"]:
        # The >2GB / damaged path: poppler reads what qpdf refuses.
        with tempfile.TemporaryDirectory() as td:
            pat = str(Path(td) / "pg-%d.pdf")
            _run([tools["pdfseparate"], "-f", str(first), "-l", str(last),
                  str(path), pat], timeout=1800)
            parts = sorted(Path(td).glob("pg-*.pdf"),
                           key=lambda q: int(re.search(r"(\d+)", q.name).group(1)))
            if parts:
                p = _run([tools["pdfunite"], *map(str, parts), str(out)],
                         timeout=600)
                if p and out.exists() and out.stat().st_size > 0:
                    info["ok"], info["method"] = True, "poppler"
                    info["notes"].append("qpdf unavailable or refused the "
                                         "file; used pdfseparate/pdfunite")
    if not info["ok"]:
        info["notes"].append("no extraction tool succeeded")
        return info

    if ocr:
        info["notes"].append(_ocr_in_place(out))
    if max_bytes and out.stat().st_size > max_bytes:
        c = compact(out, out, max_bytes=max_bytes)
        info["notes"].append(c["note"])
    info["bytes"] = out.stat().st_size
    return info


def _ocr_in_place(pdf: Path) -> str:
    """OCR a file with the flag its text-layer state calls for."""
    ocrmypdf = shutil.which("ocrmypdf")
    if not ocrmypdf:
        return "ocrmypdf unavailable; text layer left as-is"
    args = ["--force-ocr"]
    if textquality is not None:
        tq = textquality.score_pdf(pdf)
        if tq.get("state") == textquality.STATE_OK:
            return "text layer already good; OCR skipped"
        args = tq.get("ocr_args") or ["--force-ocr"]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "ocr.pdf"
        p = _run([ocrmypdf, *args, "--quiet", "--output-type", "pdf",
                  str(pdf), str(tmp)], timeout=1800)
        if p and p.returncode == 0 and tmp.exists():
            shutil.copyfile(tmp, pdf)
            return f"OCR applied ({' '.join(args)})"
    return f"OCR failed ({' '.join(args)}); text layer left as-is"


def compact(path: Path, out: Path,
            max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """Shrink a PDF toward ``max_bytes`` with Ghostscript.

    Verifies the text layer survives: a compacted file that lost its text is
    useless for quote anchoring, so the original is kept instead.
    """
    path, out = Path(path), Path(out)
    before = path.stat().st_size
    gs = shutil.which("gs")
    if not gs:
        if path != out:
            shutil.copyfile(path, out)
        return {"ok": False, "before": before, "after": before,
                "note": "ghostscript unavailable; left uncompressed"}

    had_text = bool(page_text(path, 1, ocr_fallback=False))
    for setting in ("/ebook", "/screen"):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "small.pdf"
            _run([gs, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
                  f"-dPDFSETTINGS={setting}", "-dNOPAUSE", "-dQUIET",
                  "-dBATCH", "-dDetectDuplicateImages=true",
                  f"-sOutputFile={tmp}", str(path)], timeout=900)
            if not tmp.exists() or tmp.stat().st_size == 0:
                continue
            if had_text and not page_text(tmp, 1, ocr_fallback=False):
                return {"ok": False, "before": before, "after": before,
                        "note": f"{setting} dropped the text layer; "
                                "left uncompressed"}
            if tmp.stat().st_size <= max_bytes or setting == "/screen":
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(tmp, out)
                after = out.stat().st_size
                ok = after <= max_bytes
                return {"ok": ok, "before": before, "after": after,
                        "note": (f"compacted {before:,}->{after:,} bytes "
                                 f"({setting})"
                                 + ("" if ok else "; still over budget"))}
    if path != out:
        shutil.copyfile(path, out)
    return {"ok": False, "before": before, "after": before,
            "note": "compaction produced nothing usable"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_range(s: str) -> tuple[int, int]:
    m = re.match(r"^\s*(\d+)\s*(?:[-–]\s*(\d+))?\s*$", s)
    if not m:
        raise argparse.ArgumentTypeError(f"bad page range: {s!r}")
    a = int(m.group(1))
    return a, int(m.group(2)) if m.group(2) else a


def main() -> int:
    ap = argparse.ArgumentParser(prog="pdfsource", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_probe = sub.add_parser("probe", help="health report for one or more PDFs")
    p_probe.add_argument("files", nargs="+", type=Path)
    p_probe.add_argument("--json", action="store_true")

    p_loc = sub.add_parser("locate", help="measure printed-to-PDF page offset")
    p_loc.add_argument("file", type=Path)
    p_loc.add_argument("--sample", type=int, default=DEFAULT_SAMPLES)
    p_loc.add_argument("--printed", type=int,
                       help="report which PDF page holds this printed page")
    p_loc.add_argument("--json", action="store_true")

    p_ex = sub.add_parser("extract", help="pull a page range into a new PDF")
    p_ex.add_argument("file", type=Path)
    p_ex.add_argument("--pages", required=True, type=_parse_range)
    p_ex.add_argument("--printed", action="store_true",
                      help="--pages are printed page numbers, not PDF pages")
    p_ex.add_argument("--offset", type=int)
    p_ex.add_argument("-o", "--output", required=True, type=Path)
    p_ex.add_argument("--ocr", action="store_true")
    p_ex.add_argument("--max-bytes", type=int)
    p_ex.add_argument("--json", action="store_true")

    p_c = sub.add_parser("compact", help="shrink a PDF toward a size budget")
    p_c.add_argument("file", type=Path)
    p_c.add_argument("-o", "--output", required=True, type=Path)
    p_c.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    p_c.add_argument("--json", action="store_true")

    a = ap.parse_args()

    if a.cmd == "probe":
        res = [probe(f) for f in a.files]
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            for r in res:
                print(f"{Path(r['path']).name}")
                print(f"  {r['bytes']:,} bytes · {r['pages']} pages · "
                      f"text: {r['text_state']}"
                      + (f" (quality {r['text_quality']})"
                         if r["text_quality"] is not None else ""))
                if r["ocr_args"]:
                    print(f"  → ocrmypdf {' '.join(r['ocr_args'])}")
                for n in r["notes"]:
                    print(f"  note: {n}")
        return 0

    if a.cmd == "locate":
        r = locate(a.file, samples=a.sample)
        if a.printed is not None:
            r["query_printed"] = a.printed
            r["query_pdf_page"] = r.pdf_page(a.printed)
            r["query_in_range"] = r.contains(a.printed)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            if r.offset is None:
                print(f"{a.file.name}: offset not determined "
                      f"({r['sampled']} page(s) sampled)")
                return 1
            print(f"{a.file.name}: offset {r.offset:+d} "
                  f"(confidence {r['confidence']}, {r['votes']}/{r['sampled']} pages)")
            print(f"  printed {r.printed_page(1)}–{r.printed_page(r['pages'])} "
                  f"across {r['pages']} PDF pages")
            if a.printed is not None:
                print(f"  printed {a.printed} → PDF page {r.pdf_page(a.printed)}"
                      + ("" if r.contains(a.printed) else "  [NOT IN THIS FILE]"))
        return 0

    if a.cmd == "extract":
        first, last = a.pages
        r = extract(a.file, first, last, a.output, printed=a.printed,
                    offset=a.offset, ocr=a.ocr, max_bytes=a.max_bytes)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            print(("wrote " if r["ok"] else "FAILED ") + str(a.output)
                  + (f" ({r.get('bytes', 0):,} bytes, {r['method']})"
                     if r["ok"] else ""))
            for n in r["notes"]:
                print(f"  note: {n}")
        return 0 if r["ok"] else 1

    if a.cmd == "compact":
        r = compact(a.file, a.output, max_bytes=a.max_bytes)
        print(json.dumps(r, indent=2) if a.json else r["note"])
        return 0 if r["ok"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Find a string in PDFs (or their extracted text) and report page numbers.

Exists so fact-checking and brief-matching passes stop writing throwaway
page-grep scripts into the scratchpad. An ad-hoc script produces a different
command line every run, which no permission rule can match; this one is a
fixed, allowlistable entry point.

Text comes from an adjacent `<file>.txt` when one is present (passes are told
to extract once and reuse), else from `pdftotext -layout` if poppler is
installed, else from pypdf. Pages are 1-indexed and counted by form feed, so a
hit's page number lines up with `pdftotext` output and with a PDF viewer.

Usage:
    pdf_page_grep.py PATTERN FILE [FILE ...]           # substring, case-insensitive
    pdf_page_grep.py -e 'R\\d+' FILE                    # regex
    pdf_page_grep.py -w continuance order.pdf brief.pdf # whole word
    pdf_page_grep.py --context 60 "summary judgment" order.pdf
    pdf_page_grep.py --json stipulation *.pdf           # machine-readable

Output (default), one line per hit:
    order.pdf:3: ...the parties filed a written stipulation...

Exit status: 0 if at least one hit, 1 if none, 2 on a usage or read error.

An unreadable file is status 2 even when other files produced hits, because
"1" means "searched everything, found nothing" — the finding a fact-checking
pass acts on. A mistyped path must never be able to say that.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _from_sidecar(pdf: Path):
    """Text from an adjacent .txt (or .ocr.txt), or None."""
    for candidate in (pdf.with_suffix(".txt"), pdf.with_suffix(".ocr.txt")):
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
    return None


def _from_pdftotext(pdf: Path):
    if not shutil.which("pdftotext"):
        return None
    try:
        r = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                           capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def _from_pypdf(pdf: Path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(pdf))
        return "\f".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        return None


def pages_of(pdf: Path):
    """List of page texts (1-indexed by position), or None if unreadable.

    A PDF with no text layer yields pages that are empty rather than an error;
    the caller reports "no hits", and the OCR ladder in the pass instructions
    is what recovers such a file.
    """
    text = _from_sidecar(pdf)
    if text is None and pdf.suffix.lower() == ".pdf":
        text = _from_pdftotext(pdf) or _from_pypdf(pdf)
    if text is None and pdf.suffix.lower() != ".pdf":
        try:
            text = pdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    if text is None:
        return None
    return text.split("\f")


def build_matcher(pattern, regex, word, case_sensitive):
    flags = 0 if case_sensitive else re.IGNORECASE
    if not regex:
        pattern = re.escape(pattern)
    if word:
        pattern = rf"\b(?:{pattern})\b"
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        print(f"pdf_page_grep: bad pattern: {exc}", file=sys.stderr)
        raise SystemExit(2)


def normalize(page_text):
    """Collapse all whitespace runs to single spaces.

    Searching happens against this, not the raw page. `pdftotext -layout` pads
    with spaces and wraps lines mid-sentence, so a two-word phrase routinely
    straddles a line break and a literal substring search for it finds
    nothing -- while the words are plainly there. That failure is silent
    and reads as "the record doesn't say this", which is exactly the wrong
    conclusion for a fact-checking pass to reach. Use --raw when line structure
    actually matters.
    """
    return " ".join(page_text.split())


def snippet(page_text, match, context):
    start = max(0, match.start() - context)
    end = min(len(page_text), match.end() + context)
    text = " ".join(page_text[start:end].split())
    return ("..." if start else "") + text + ("..." if end < len(page_text) else "")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Find a string in PDFs and report page numbers.")
    ap.add_argument("pattern")
    ap.add_argument("files", nargs="+")
    ap.add_argument("-e", "--regex", action="store_true",
                    help="treat PATTERN as a regular expression")
    ap.add_argument("-w", "--word", action="store_true",
                    help="match whole words only")
    ap.add_argument("-s", "--case-sensitive", action="store_true")
    ap.add_argument("-c", "--context", type=int, default=40,
                    help="characters of context around each hit (default 40)")
    ap.add_argument("--max-per-file", type=int, default=20,
                    help="stop after this many hits in one file (default 20)")
    ap.add_argument("--raw", action="store_true",
                    help="search the page as extracted, preserving line breaks "
                         "and layout padding; by default whitespace is collapsed "
                         "so phrases spanning a line break still match")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON records instead of grep-style lines")
    args = ap.parse_args()

    matcher = build_matcher(args.pattern, args.regex, args.word,
                            args.case_sensitive)
    results, unreadable = [], []

    for name in args.files:
        path = Path(name)
        pages = pages_of(path)
        if pages is None:
            unreadable.append(str(path))
            continue
        hits = 0
        for number, raw_page in enumerate(pages, 1):
            page_text = raw_page if args.raw else normalize(raw_page)
            for match in matcher.finditer(page_text):
                results.append({
                    "file": path.name,
                    "path": str(path),
                    "page": number,
                    "text": snippet(page_text, match, args.context),
                })
                hits += 1
                if hits >= args.max_per_file:
                    break
            if hits >= args.max_per_file:
                break

    if args.json:
        print(json.dumps({"hits": results, "unreadable": unreadable}, indent=1))
    else:
        for r in results:
            print(f"{r['file']}:{r['page']}: {r['text']}")
        for path in unreadable:
            print(f"pdf_page_grep: could not extract text: {path}",
                  file=sys.stderr)

    if unreadable:
        return 2
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())

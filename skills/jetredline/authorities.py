#!/usr/bin/env python3
"""Match authority references in a draft to the PDFs supplied alongside it.

Pass 3D's deterministic half. A draft may lean on a convention journal, a
treatise, a nineteenth-century periodical — sources the citation parser cannot
recognize, whose copies sit in the project directory. Connecting the two is a
bipartite match where *both sides are fuzzy*: the reference is prose, and the
filename is frequently wrong.

Three stages, each usable on its own:

``inventory``
    Walk the project directory, skip what other passes already own (party
    briefs, record items, the draft itself), and identify what is left from
    PDF metadata plus the first pages of text.
``candidates``
    Pull spans out of the draft that look like authority references but that
    jetcite did not claim. Deterministic pre-filter only — it feeds a model,
    which does the actual recognition, rather than trying to be one.
``match``
    Score references against files, then **validate the winner against the
    measured printed-page offset**.

That last step is not a refinement. Filenames lie: three volumes of one set,
named ``-1``/``-2``/``-3``, measured offsets of 630, 1145 and 633, and the
cited page lived in none of the files their names implied. A title match alone
would have embedded the wrong volume with full confidence. A file that cannot
hold the cited page is not a match, whatever it is called — so a page check
outranks any amount of title similarity.

CLI::

    authorities.py inventory DIR [--manifest M] [--json]
    authorities.py candidates DRAFT.md [--cites cites.json] [--json]
    authorities.py match --refs refs.json --dir DIR [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

try:
    import pdfsource
except ImportError:  # pragma: no cover - packaging guard
    pdfsource = None

__all__ = ["inventory", "identify", "candidates_from_draft", "match",
           "score_reference"]

#: Directories never worth walking for authorities. `authorities/` holds this
#: pipeline's own page extracts -- ingesting them would match a reference to a
#: file derived from that same reference.
_SKIP_DIRS = {"record_items", "authorities", "__pycache__", "node_modules",
              ".git", ".venv"}

#: Filename fragments owned by other passes.
_SKIP_NAME_BITS = ("_Apt-Br", "_Ape-Br", "_Amicus-Br", "Notice-of-Appeal",
                   "-Reply-Br", ".ocr", "MemoPacket", "-Packet", "_Packet")

#: Above this, a PDF is a record packet or a bundle, not an authority. The
#: largest genuine volume seen in the field is ~130 MB, so the ceiling has
#: room without admitting a multi-gigabyte packet.
_MAX_AUTHORITY_BYTES = 200 * 1024 * 1024

_YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20[0-2]\d)\b")
_STOP = frozenset("""a an the of and or in on at to for from by with is are was
were be been this that these those it its as v vs et al no not""".split())


# ---------------------------------------------------------------------------
# Side 2 — the PDFs on disk
# ---------------------------------------------------------------------------

def identify(path: Path, probe_pages: int = 3) -> dict:
    """Best-effort identity for a PDF: title, author, year.

    Metadata first — scanned historical material is often catalogued, and a
    ``Title`` written by the digitizing library beats anything guessable from
    the page image. Falls back to the opening pages, which on a bound volume
    is the title page.
    """
    path = Path(path)
    out = {"path": str(path), "name": path.name, "title": "", "author": "",
           "year": "", "source": "none", "text_sample": ""}

    meta = _pdf_metadata(path)
    title = (meta.get("Title") or "").strip()
    if title and not title.lower().endswith(".pdf"):
        out["title"], out["source"] = title, "metadata"
    out["author"] = (meta.get("Author") or "").strip()
    blob = " ".join(filter(None, (meta.get("Title"), meta.get("Subject"),
                                  meta.get("Keywords"))))

    sample = ""
    if pdfsource is not None:
        for pg in range(1, probe_pages + 1):
            sample += "\n" + pdfsource.page_text(path, pg)
            if len(sample) > 1500:
                break
    out["text_sample"] = sample.strip()[:1500]

    if not out["title"]:
        # Title page heuristic: the longest of the first few substantive lines.
        lines = [ln.strip() for ln in sample.splitlines() if len(ln.strip()) > 8]
        if lines:
            out["title"] = max(lines[:12], key=len)[:200]
            out["source"] = "text"
    if not out["title"]:
        out["title"] = path.stem.replace("-", " ").replace("_", " ")
        out["source"] = "filename"

    # Year from catalogued metadata or the filename only. Scraping it from the
    # page sample reads whatever four-digit number sits in the running head --
    # which on a periodical is as likely to be a page number or a cited year
    # as the imprint date.
    ym = _YEAR_RE.search(blob) or _YEAR_RE.search(path.name)
    if ym:
        out["year"] = ym.group(1)
    return out


def _pdf_metadata(path: Path) -> dict:
    import shutil
    import subprocess
    exe = shutil.which("pdfinfo")
    if not exe:
        return {}
    try:
        p = subprocess.run([exe, str(path)], capture_output=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return {}
    out = {}
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def inventory(root: Path, manifest: list[dict] | None = None,
              skip: set[str] | None = None) -> list[dict]:
    """Candidate authority PDFs under ``root``.

    Excludes anything another pass already owns: briefs named in the manifest,
    record items, and the conventional brief/notice filename patterns.
    """
    root = Path(root)
    owned = {e.get("filename") for e in (manifest or []) if e.get("filename")}
    skip = (skip or set()) | _SKIP_DIRS
    found = []
    for p in sorted(root.rglob("*.pdf")):
        rel = p.relative_to(root)
        if any(part in skip or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if p.name in owned:
            continue
        if any(bit in p.name for bit in _SKIP_NAME_BITS):
            continue
        try:
            if p.stat().st_size > _MAX_AUTHORITY_BYTES:
                continue
        except OSError:
            continue
        found.append(identify(p))
    return found


# ---------------------------------------------------------------------------
# Side 1 — references in the draft
# ---------------------------------------------------------------------------

_TITLE_WORD = r"(?:[A-Z][\w'’.\-]*|of|the|and|for|in|on|upon|to|a|an)"

_REF_PATTERNS = (
    # "Journal of the Constitutional Convention ... 65-113 (1889)". Inner
    # lowercase connectives are part of a title, so the span must not start
    # after them.
    re.compile(rf"[A-Z][\w'’.\-]*(?:\s+{_TITLE_WORD}){{1,12}}[^.,;]{{0,40}}\(\d{{4}}\)"),
    # Periodical form: "65 N.D. L. Rev. 343" / "41 Am. L. Reg. & Rev. 922"
    re.compile(r"\b\d{1,3}\s+(?:[A-Z][\w.'’&]*\s+){1,5}\d{1,4}\b"),
)


def candidates_from_draft(text: str,
                          claimed_spans: list[tuple[int, int]] | None = None,
                          italic_spans: list[tuple[int, int]] | None = None
                          ) -> list[dict]:
    """Spans in the draft that look like authority references.

    A deterministic pre-filter, not a recognizer. Its job is to hand a model a
    short list of candidate spans instead of the whole draft — recall matters
    much more than precision here, because the model discards false positives
    cheaply and can never recover a span this never surfaces.

    ``claimed_spans`` are character ranges jetcite already matched; anything
    overlapping one is a citation and belongs to Pass 3, not here.
    """
    claimed = claimed_spans or []
    out: list[dict] = []
    seen: set[tuple[int, int]] = set()

    def overlaps_claimed(a: int, b: int) -> bool:
        return any(a < d and b > c for c, d in claimed)

    for pat in _REF_PATTERNS:
        for m in pat.finditer(text):
            a, b = m.start(), m.end()
            if overlaps_claimed(a, b) or (a, b) in seen:
                continue
            frag = m.group(0).strip()
            if len(frag) < 12 or _looks_like_prose(frag):
                continue
            seen.add((a, b))
            out.append({"start": a, "end": b, "text": frag, "signal": "pattern"})

    # Italic runs recovered from the .docx are a strong signal: titles of works
    # are italicized, and jetcite claimed the ones that were case names.
    for a, b in (italic_spans or []):
        if overlaps_claimed(a, b) or (a, b) in seen:
            continue
        frag = text[a:b].strip()
        if 12 <= len(frag) <= 240 and not _looks_like_prose(frag):
            seen.add((a, b))
            out.append({"start": a, "end": b, "text": frag, "signal": "italic"})

    out.sort(key=lambda d: d["start"])
    return out


def _looks_like_prose(s: str) -> bool:
    """Reject spans that are ordinary sentences rather than titles."""
    words = s.split()
    if len(words) < 2:
        return True
    caps = sum(1 for w in words if w[:1].isupper())
    return caps / len(words) < 0.4


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------

def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if w not in _STOP and len(w) > 1}


def score_reference(ref: dict, file_info: dict) -> float:
    """Similarity in 0..1 between a draft reference and a file on disk."""
    rt, ft = _tokens(ref.get("title")), _tokens(file_info.get("title"))
    fn = _tokens(file_info.get("name"))
    fs = _tokens(file_info.get("text_sample"))
    if not rt:
        return 0.0

    # Best-of, not sum: a catalogued title and a descriptive filename are
    # alternative evidence for the same fact, not two independent facts.
    #
    # Coverage of the *reference* rather than Jaccard. A filename like
    # "meschke-spears_digging-for-roots_65-NDLR-343_1989.pdf" carries author,
    # volume, page and year tokens the reference never mentions; under Jaccard
    # those extras dilute a real match toward nothing.
    def cover(a: set, b: set) -> float:
        return len(a & b) / len(a) if a and b else 0.0

    overlap = max(cover(rt, ft), cover(rt, fn), cover(rt, fs) * 0.8)
    base = overlap

    # Character similarity only once a token is shared. Two unrelated legal
    # titles ("Journal of the Constitutional Convention" vs "Federal
    # Taxation") run ~0.3 on SequenceMatcher purely from common letters, which
    # is enough to clear a match threshold on its own.
    if rt & (ft | fn):
        base = max(base, SequenceMatcher(
            None, (ref.get("title") or "").lower()[:120],
            (file_info.get("title") or "").lower()[:120]).ratio() * 0.9)

    if ref.get("year") and file_info.get("year"):
        base += 0.10 if str(ref["year"]) == str(file_info["year"]) else -0.10
    if ref.get("author"):
        surname = str(ref["author"]).split()[-1].lower()
        if surname and (surname in (file_info.get("name") or "").lower()
                        or surname in (file_info.get("title") or "").lower()):
            base += 0.10
    return max(0.0, min(1.0, base))


#: A measured offset must be at least this confident before it may veto an
#: otherwise-good title match.
VETO_CONFIDENCE = 0.7

#: How much page-containment moves a candidate's score.
_PAGE_BONUS = 0.35
_PAGE_PENALTY = 0.25


def match(references: list[dict], files: list[dict],
          threshold: float = 0.34, verify_pages: bool = True) -> dict:
    """Match draft references to files, weighing the cited printed page.

    Returns ``{"matched", "unmatched_references", "unmatched_files"}``.

    Page-containment is the signal that title similarity cannot supply: three
    volumes of one set share a title almost exactly, and only one of them holds
    the cited page. So a file whose measured offset admits the page is promoted,
    and one that excludes it is demoted.

    It is a *ranking* signal rather than a veto, because the measurement can be
    wrong. A 23-page offprint beginning at printed page 922 yielded an offset of
    +16 from a stray footnote sequence (22 on one page, 23 on the next), and an
    earlier hard veto used that to reject the article from its own file. A veto
    now requires ``VETO_CONFIDENCE``; below that the check is recorded as
    unverified and the title decides.
    """
    matched, unmatched_refs = [], []
    used: set[str] = set()

    for ref in references:
        page = ref.get("printed_page")
        scored = []
        rejected = []
        for f in files:
            base = score_reference(ref, f)
            if base < threshold * 0.5:
                continue
            adj, loc_info = base, None
            if verify_pages and page and pdfsource is not None and base >= threshold:
                loc = pdfsource.locate(Path(f["path"]))
                conf = loc.get("confidence") or 0.0
                if loc.offset is not None:
                    holds = loc.contains(int(page))
                    loc_info = {
                        "offset": loc.offset, "confidence": conf,
                        "pdf_page": loc.pdf_page(int(page)) if holds else None,
                        "verified": conf >= VETO_CONFIDENCE,
                    }
                    # Three tiers, keyed to how much the measurement is worth.
                    # A weak measurement that merely fails to place the page is
                    # not evidence against the file — it is no evidence at all,
                    # and penalising on it drops a correct match below
                    # threshold. Only a confident exclusion may reject.
                    if holds:
                        adj = min(1.0, base + (_PAGE_BONUS if conf >= VETO_CONFIDENCE
                                               else _PAGE_BONUS / 2))
                    elif conf >= VETO_CONFIDENCE:
                        rejected.append({
                            "file": f["name"], "score": round(base, 3),
                            "reason": (f"cannot hold printed page {page}: "
                                       f"measured offset {loc.offset:+d} over "
                                       f"{loc['pages']} pages "
                                       f"(confidence {conf})"),
                        })
                        continue
                    elif conf >= 0.6:
                        adj = max(0.0, base - _PAGE_PENALTY)
            scored.append((adj, base, f, loc_info))

        scored.sort(key=lambda t: t[0], reverse=True)
        if scored and scored[0][0] >= threshold:
            adj, base, f, loc_info = scored[0]
            used.add(f["path"])
            matched.append({
                "reference": ref, "file": f["path"], "file_name": f["name"],
                "score": round(adj, 3), "title_score": round(base, 3),
                "pdf_page": (loc_info or {}).get("pdf_page"),
                "offset": (loc_info or {}).get("offset"),
                "offset_confidence": (loc_info or {}).get("confidence"),
                "page_verified": bool((loc_info or {}).get("verified")
                                      and (loc_info or {}).get("pdf_page")),
                "rejected_candidates": rejected,
            })
        else:
            unmatched_refs.append({
                "reference": ref,
                "best_score": round(scored[0][0], 3) if scored else 0.0,
                "rejected_candidates": rejected,
            })

    return {
        "matched": matched,
        "unmatched_references": unmatched_refs,
        "unmatched_files": [f for f in files if f["path"] not in used],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(prog="authorities",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_inv = sub.add_parser("inventory", help="identify candidate authority PDFs")
    p_inv.add_argument("dir", type=Path)
    p_inv.add_argument("--manifest", type=Path)
    p_inv.add_argument("--json", action="store_true")

    p_can = sub.add_parser("candidates",
                           help="draft spans that look like authority references")
    p_can.add_argument("draft", type=Path)
    p_can.add_argument("--cites", type=Path,
                       help="cite_check.py JSON, to skip spans jetcite claimed")
    p_can.add_argument("--json", action="store_true")

    p_m = sub.add_parser("match", help="match references to files")
    p_m.add_argument("--refs", required=True, type=Path)
    p_m.add_argument("--dir", required=True, type=Path)
    p_m.add_argument("--manifest", type=Path)
    p_m.add_argument("--no-verify-pages", action="store_true")
    p_m.add_argument("--json", action="store_true")

    a = ap.parse_args()

    def load_manifest(p):
        if not p:
            return None
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    if a.cmd == "inventory":
        res = inventory(a.dir, manifest=load_manifest(a.manifest))
        if a.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            for r in res:
                print(f"{r['name']}")
                print(f"  title [{r['source']}]: {r['title'][:96]}")
                if r["year"]:
                    print(f"  year: {r['year']}")
        print(f"\n{len(res)} candidate authority PDF(s)", file=sys.stderr)
        return 0

    if a.cmd == "candidates":
        text = a.draft.read_text(encoding="utf-8")
        claimed = []
        if a.cites and a.cites.exists():
            try:
                for c in json.loads(a.cites.read_text(encoding="utf-8")):
                    pos = c.get("position")
                    if isinstance(pos, int):
                        claimed.append((pos, pos + len(c.get("cite_text") or "")))
            except (OSError, ValueError, TypeError):
                pass
        res = candidates_from_draft(text, claimed_spans=claimed)
        if a.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            for r in res:
                print(f"[{r['signal']}] {r['text'][:110]}")
        print(f"\n{len(res)} candidate span(s)", file=sys.stderr)
        return 0

    if a.cmd == "match":
        refs = json.loads(a.refs.read_text(encoding="utf-8"))
        files = inventory(a.dir, manifest=load_manifest(a.manifest))
        res = match(refs, files, verify_pages=not a.no_verify_pages)
        if a.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            for m in res["matched"]:
                pg = (f" → PDF p.{m['pdf_page']}"
                      + ("" if m["page_verified"] else " (page unverified)")
                      ) if m["pdf_page"] else (
                      "  [cited page not confirmed]" if m["reference"].get("printed_page") else "")
                print(f"MATCH {m['score']:.2f}  "
                      f"{m['reference'].get('title', '')[:60]}"
                      f"\n            {m['file_name']}{pg}")
                for r in m["rejected_candidates"]:
                    print(f"            rejected {r['file']}: {r['reason']}")
            for u in res["unmatched_references"]:
                print(f"NO MATCH   {u['reference'].get('title', '')[:60]} "
                      f"(best {u['best_score']:.2f})")
                for r in u["rejected_candidates"]:
                    print(f"            rejected {r['file']}: {r['reason']}")
        print(f"\n{len(res['matched'])} matched, "
              f"{len(res['unmatched_references'])} unmatched reference(s), "
              f"{len(res['unmatched_files'])} unused file(s)", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

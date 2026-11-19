#!/usr/bin/env python3
"""
Citation Checker — thin wrapper around jetcite that outputs the legacy
JSON schema expected by Pass 3B
(references/pass-instructions/pass3b-citations.md).

Usage:
    python3 cite_check.py --file opinion.md
    python3 cite_check.py --file opinion.md --sources-dir <TMPDIR>/sources --fetch
    echo "N.D.C.C. § 12.1-32-01" | python3 cite_check.py
    echo "42 U.S.C. § 1983" | python3 cite_check.py

Output: JSON array of citation records with URLs and, when a sources
directory is given, the path of each authority's text inside it.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate jetcite: bundled lib/, pip install, or bail with instructions.
# ---------------------------------------------------------------------------
_BUNDLED_LIB = Path(__file__).resolve().parent / "lib"

if _BUNDLED_LIB.is_dir():
    sys.path.insert(0, str(_BUNDLED_LIB))

try:
    from jetcite import Citation, CitationType, scan_text
    from jetcite.fetch import fetch_text
    from jetcite.legacy import (
        CASE_TYPES,
        add_parallel_info,
        to_legacy_dict,
    )
except ImportError as e:
    _jetcite_dir = _BUNDLED_LIB / "jetcite"
    if not _jetcite_dir.is_dir():
        print(
            "ERROR: jetcite not found. Expected bundled copy at:\n"
            f"  {_jetcite_dir}\n"
            "Run 'make vendor-jetcite' to re-vendor, or install via pip:\n"
            "  pip install git+https://github.com/jet52/jetcite.git",
            file=sys.stderr,
        )
    else:
        print(
            f"ERROR: jetcite found at {_jetcite_dir} but failed to import:\n"
            f"  {e}\n"
            "Install the skill dependencies:\n"
            f"  pip install -r {Path(__file__).resolve().parent / 'requirements.txt'}",
            file=sys.stderr,
        )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Per-run source text
#
# The text of a cited authority is kept only for the run that needs it, in a
# sources directory the caller names (normally <TMPDIR>/sources). Nothing is
# read from or written to a shared tree: through v2 this was ~/refs, which
# most users do not have, and which on a machine that does have one may be
# somebody's primary source files.
# ---------------------------------------------------------------------------

def source_path(normalized: str, sources_dir: str | Path) -> Path:
    """Where one authority's text lives inside a run's sources directory."""
    slug = re.sub(r"[^A-Za-z0-9.]+", "_", re.sub(r"\s+", "", normalized))
    return Path(sources_dir).expanduser() / f"{slug}.md"


def write_source(path: Path, text: str, meta: dict) -> None:
    """Write one authority's text and its provenance sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    meta = {"fetched": datetime.now(timezone.utc).isoformat(), **meta}
    path.with_suffix(path.suffix + ".meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")


def source_trust(path: str | Path) -> dict:
    """What a file in the sources directory may be relied on for.

      origin         "ndlaw-corpus", "web-fetch", or "unknown" (no sidecar).
      fetched        ISO timestamp, or None.
      pairing_basis  "asserted-by-source" when the fetch reached this opinion
                     only through a parallel cite the draft itself paired.
      confirms       False when the file must not stand as verification of
                     its own citation.
    """
    try:
        meta = json.loads(Path(str(path) + ".meta.json").expanduser()
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    basis = (meta.get("pairing") or {}).get("basis")
    origin = meta.get("origin") or "unknown"
    return {
        "origin": origin,
        "fetched": meta.get("fetched"),
        "pairing_basis": basis,
        "confirms": origin in ("ndlaw-corpus", "web-fetch") and basis is None,
    }


def fetch_source(cite: Citation, sources_dir: str | Path,
                 timeout: float = 15.0) -> Path | None:
    """Fetch one authority's text from the web into the sources directory."""
    got = fetch_text(cite, timeout=timeout)
    if got is None:
        return None
    path = source_path(cite.normalized, sources_dir)
    meta = {"citation": cite.normalized, "source_url": got.source_url,
            "origin": "web-fetch"}
    if got.via_parallel:
        meta["pairing"] = {"resolved_from": got.via_parallel,
                           "basis": "asserted-by-source"}
    try:
        write_source(path, got.text, meta)
    except OSError:
        return None
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_opinion(text: str, sources_dir: str | Path | None = None,
                 fetch_missing: bool = False,
                 include_pin_cites: bool = True,
                 include_occurrences: bool = True) -> list[dict]:
    """Scan opinion text for all citations. Returns legacy-format dicts.

    ``sources_dir`` is this run's sources directory. Each first-occurrence
    entry gets ``local_path`` (where its text would sit there) and
    ``local_exists`` (whether it does: ndlaw_export.py or an earlier step of
    the same run put it there). With no sources_dir both are None / False.
    If fetch_missing is True, case citations with no text there yet are
    fetched from their web source into it.

    Pin-cite short forms ("491 F.3d at 363", "Goss at 365", "Id. ¶ 14")
    appear as entries with cite_type "pin_cite", linked to their parent full
    cite via parent_normalized (None = unresolved — e.g. a digit-transposed
    volume; flagged with pin_warning for Pass 3B). Pin entries carry no text
    of their own ("pin_cite" is not in CASE_TYPES, so the fetch loop skips
    them); verification reads the parent's text via
    parent_local_path / parent_local_exists.

    Repeat full-form cites of every type — second and later appearances,
    e.g. a short cite written out as "Olson, 2024 ND 156, ¶ 12", or
    "N.D.R.Ev. 702(b)" after an earlier "N.D.R.Ev. 702" — appear as entries
    with is_repeat=True linked to the first occurrence via parent_normalized,
    so each proposition and pinpoint is individually verifiable. A rule or
    statute subdivision ("(b)", "(1)(a)") travels in ``pinpoint``; the bare
    provision is the authority. Like pins, repeats carry no text of their
    own and are skipped by the fetch loop; they get
    parent_local_path / parent_local_exists instead.
    """
    citations = scan_text(text, include_pin_cites=include_pin_cites,
                          include_occurrences=include_occurrences)

    entries = [to_legacy_dict(c) for c in citations]
    add_parallel_info(entries, citations)

    for entry in entries:
        entry["local_path"] = None
        entry["local_exists"] = False
        if (sources_dir is not None and entry["cite_type"] != "pin_cite"
                and not entry.get("is_repeat")):
            path = source_path(entry["normalized"], sources_dir)
            entry["local_path"] = str(path)
            entry["local_exists"] = path.is_file()

    if fetch_missing and sources_dir is not None:
        norm_to_cite = {c.normalized: c for c in citations if not c.is_repeat}
        for entry in entries:
            if (entry.get("cite_type") in CASE_TYPES
                    and not entry.get("is_repeat")
                    and not entry.get("local_exists")
                    and entry.get("url")):
                cite = norm_to_cite.get(entry["normalized"])
                if cite is None:
                    continue
                if fetch_source(cite, sources_dir) is not None:
                    entry["local_exists"] = True

    annotate_short_forms(entries)
    return entries


def annotate_short_forms(entries: list[dict]) -> None:
    """Attach parent context to pin-cite and repeat-occurrence entries.

    Resolved pins and repeats get ``parent_local_path``/``parent_local_exists``
    copied from the first-occurrence entry so Pass 3B reads the parent's
    text when verifying the page/paragraph. Unresolved pins get
    ``pin_warning`` — an explicit short form with no matching antecedent is
    a drafting defect worth surfacing in the redline.
    """
    by_norm = {}
    for e in entries:
        if e["cite_type"] != "pin_cite" and not e.get("is_repeat"):
            by_norm.setdefault(e["normalized"], e)
    for e in entries:
        is_pin = e["cite_type"] == "pin_cite"
        if not is_pin and not e.get("is_repeat"):
            continue
        parent_norm = e.get("parent_normalized")
        if parent_norm is None:
            if is_pin:
                unparsed = e.get("unparsed_antecedent")
                if unparsed:
                    # Id. after a brief/record/transcript cite: correct usage,
                    # just not an authority jetcite parses. A note, not a defect.
                    e["pin_note"] = (
                        f"Id. refers to the preceding {unparsed} citation; "
                        "not a parsed authority, nothing to verify"
                    )
                else:
                    e["pin_warning"] = (
                        "unresolved short form: no earlier full citation matches"
                    )
            continue
        parent = by_norm.get(parent_norm)
        if parent is not None:
            e["parent_local_path"] = parent.get("local_path")
            e["parent_local_exists"] = parent.get("local_exists", False)


# Backward-compatible alias (pre-occurrence name)
annotate_pin_cites = annotate_short_forms


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parse legal citations and build URLs; optionally fetch "
                    "case text into a per-run sources directory."
    )
    parser.add_argument("--file", "-f", help="Scan a file for all citations")
    parser.add_argument("--sources-dir",
                        help="This run's sources directory (e.g. "
                             "<TMPDIR>/sources): where ndlaw_export.py and "
                             "--fetch put authority text. Omit for none.")
    parser.add_argument("--json", action="store_true", default=True,
                        help="Output as JSON (default)")
    parser.add_argument("--fetch", action="store_true",
                        help="Fetch case text not already in --sources-dir "
                             "from its web source into it")
    parser.add_argument("--pin-cites", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Include pin-cite short forms linked to their "
                             "parent cites (default: on; --no-pin-cites to disable)")
    args = parser.parse_args()
    if args.fetch and not args.sources_dir:
        parser.error("--fetch requires --sources-dir")

    if args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
        results = scan_opinion(text, sources_dir=args.sources_dir, fetch_missing=args.fetch,
                               include_pin_cites=args.pin_cites)
    else:
        # stdin mode — one citation per line. Pin-cite linking needs document
        # context (the parent full cite), so single-line scans skip pins.
        results = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            found = scan_opinion(line, sources_dir=args.sources_dir, fetch_missing=args.fetch,
                                 include_pin_cites=False)
            results.extend(found)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

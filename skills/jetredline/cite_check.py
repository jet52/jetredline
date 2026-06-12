#!/usr/bin/env python3
"""
Citation Checker — thin wrapper around jetcite that outputs the legacy
JSON schema expected by SKILL.md Pass 3B.

Usage:
    python3 cite_check.py --file opinion.md
    echo "N.D.C.C. § 12.1-32-01" | python3 cite_check.py
    echo "42 U.S.C. § 1983" | python3 cite_check.py

Output: JSON array of citation records with local paths and URLs.
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate jetcite: bundled lib/, pip install, or bail with instructions.
# ---------------------------------------------------------------------------
_BUNDLED_LIB = Path(__file__).resolve().parent / "lib"

if _BUNDLED_LIB.is_dir():
    sys.path.insert(0, str(_BUNDLED_LIB))

try:
    from jetcite import Citation, CitationType, scan_text
    from jetcite.cache import fetch_and_cache
    from jetcite.legacy import (
        CASE_TYPES,
        add_parallel_info,
        to_legacy_dict,
    )
except ImportError:
    print(
        "ERROR: jetcite import failed. Bundled copy expected at:\n"
        f"  {_BUNDLED_LIB / 'jetcite'}\n"
        "Ensure httpx is installed:  pip install httpx[socks]\n"
        "Or install jetcite via pip:\n"
        "  pip install git+https://github.com/jet52/jetcite.git",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_opinion(text: str, refs_dir: str = "~/refs", cache_missing: bool = False,
                 include_pin_cites: bool = True,
                 include_occurrences: bool = True) -> list[dict]:
    """Scan opinion text for all citations. Returns legacy-format dicts.

    If cache_missing is True, fetches and caches all case citations that
    are not already in the local refs directory.

    Pin-cite short forms ("491 F.3d at 363", "Goss at 365", "Id. ¶ 14")
    appear as entries with cite_type "pin_cite", linked to their parent full
    cite via parent_normalized (None = unresolved — e.g. a digit-transposed
    volume; flagged with pin_warning for Pass 3B). Pin entries carry no local
    file of their own ("pin_cite" is not in CASE_TYPES, so the cache loop
    skips them); verification reads the parent's cached opinion via
    parent_local_path / parent_local_exists.

    Repeat full-form case cites — second and later appearances, e.g. a short
    cite written out as "Olson, 2024 ND 156, ¶ 12" — appear as entries with
    is_repeat=True linked to the first occurrence via parent_normalized, so
    each proposition and pinpoint is individually verifiable. Like pins,
    repeats carry no local file of their own and are skipped by the cache
    loop; they get parent_local_path / parent_local_exists instead.
    """
    refs = Path(refs_dir).expanduser()
    citations = scan_text(text, refs_dir=refs, include_pin_cites=include_pin_cites,
                          include_occurrences=include_occurrences)

    entries = [to_legacy_dict(c, refs) for c in citations]
    add_parallel_info(entries, citations)

    if cache_missing:
        norm_to_cite = {c.normalized: c for c in citations if not c.is_repeat}
        for entry in entries:
            if (entry.get("cite_type") in CASE_TYPES
                    and not entry.get("is_repeat")
                    and not entry.get("local_exists")
                    and entry.get("url")):
                cite = norm_to_cite.get(entry["normalized"])
                if cite is None:
                    continue
                cached = fetch_and_cache(cite, refs_dir=refs, timeout=15.0)
                if cached is not None:
                    entry["local_path"] = str(cached)
                    entry["local_exists"] = True

    annotate_short_forms(entries)
    return entries


def annotate_short_forms(entries: list[dict]) -> None:
    """Attach parent context to pin-cite and repeat-occurrence entries.

    Resolved pins and repeats get ``parent_local_path``/``parent_local_exists``
    copied from the first-occurrence entry so Pass 3B reads the parent's
    cached opinion when verifying the page/paragraph. Unresolved pins get
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
        description="Parse legal citations, resolve local files, build URLs."
    )
    parser.add_argument("--file", "-f", help="Scan a file for all citations")
    parser.add_argument("--refs-dir", default="~/refs",
                        help="Override refs directory (default: ~/refs)")
    parser.add_argument("--json", action="store_true", default=True,
                        help="Output as JSON (default)")
    parser.add_argument("--cache", action="store_true",
                        help="Auto-fetch and cache missing case citations")
    parser.add_argument("--pin-cites", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Include pin-cite short forms linked to their "
                             "parent cites (default: on; --no-pin-cites to disable)")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
        results = scan_opinion(text, refs_dir=args.refs_dir, cache_missing=args.cache,
                               include_pin_cites=args.pin_cites)
    else:
        # stdin mode — one citation per line. Pin-cite linking needs document
        # context (the parent full cite), so single-line scans skip pins.
        results = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            found = scan_opinion(line, refs_dir=args.refs_dir, cache_missing=args.cache,
                                 include_pin_cites=False)
            results.extend(found)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

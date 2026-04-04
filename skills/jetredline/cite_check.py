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

def scan_opinion(text: str, refs_dir: str = "~/refs", cache_missing: bool = False) -> list[dict]:
    """Scan opinion text for all citations. Returns legacy-format dicts.

    If cache_missing is True, fetches and caches all case citations that
    are not already in the local refs directory.
    """
    refs = Path(refs_dir).expanduser()
    citations = scan_text(text, refs_dir=refs)

    entries = [to_legacy_dict(c, refs) for c in citations]
    add_parallel_info(entries, citations)

    if cache_missing:
        norm_to_cite = {c.normalized: c for c in citations}
        for entry in entries:
            if (entry.get("cite_type") in CASE_TYPES
                    and not entry.get("local_exists")
                    and entry.get("url")):
                cite = norm_to_cite.get(entry["normalized"])
                if cite is None:
                    continue
                cached = fetch_and_cache(cite, refs_dir=refs, timeout=15.0)
                if cached is not None:
                    entry["local_path"] = str(cached)
                    entry["local_exists"] = True

    return entries


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
    args = parser.parse_args()

    if args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
        results = scan_opinion(text, refs_dir=args.refs_dir, cache_missing=args.cache)
    else:
        # stdin mode — one citation per line
        results = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            found = scan_opinion(line, refs_dir=args.refs_dir, cache_missing=args.cache)
            results.extend(found)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

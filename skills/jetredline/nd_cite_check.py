#!/usr/bin/env python3
"""
Citation Checker — thin wrapper around jetcite that outputs the legacy
JSON schema expected by SKILL.md Pass 3B.

Usage:
    python3 nd_cite_check.py --file opinion.md
    echo "N.D.C.C. § 12.1-32-01" | python3 nd_cite_check.py
    echo "42 U.S.C. § 1983" | python3 nd_cite_check.py

Output: JSON array of citation records with local paths and URLs.
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate jetcite: pip install, skill directory, or bail with instructions.
# ---------------------------------------------------------------------------
_JETCITE_SKILL = Path.home() / ".claude" / "skills" / "jetcite-skill" / "src"

try:
    from jetcite import Citation, CitationType, scan_text
    from jetcite.cache import _citation_path
except ImportError:
    if _JETCITE_SKILL.is_dir():
        sys.path.insert(0, str(_JETCITE_SKILL))
        try:
            from jetcite import Citation, CitationType, scan_text
            from jetcite.cache import _citation_path
        except ImportError:
            pass
    if "jetcite" not in sys.modules:
        print(
            "ERROR: jetcite is not installed.\n"
            "Install it as a Claude skill:\n"
            "  https://github.com/jet52/jetcite\n"
            "Or install via pip:\n"
            "  pip install git+https://github.com/jet52/jetcite.git",
            file=sys.stderr,
        )
        sys.exit(1)

# ---------------------------------------------------------------------------
# Cite-type mapping: jetcite generic types → legacy specific strings
# ---------------------------------------------------------------------------

from jetcite.cache import _ND_REPORTERS, _FEDERAL_REPORTERS


def _legacy_cite_type(c: Citation) -> str:
    """Map jetcite CitationType + jurisdiction + components to legacy cite_type."""
    if c.cite_type == CitationType.CASE:
        if c.jurisdiction == "nd" and "year" in c.components and "number" in c.components:
            return "nd_case"
        reporter = c.components.get("reporter", "")
        if reporter == "U.S.":
            return "us_supreme_court"
        if reporter in _ND_REPORTERS:
            return "nd_reporter"
        if reporter in _FEDERAL_REPORTERS:
            return "federal_reporter"
        # State neutral: has year+number but no reporter (or abbreviation)
        if "reporter" not in c.components:
            return "state_neutral"
        return "state_reporter"

    if c.cite_type == CitationType.STATUTE:
        if c.jurisdiction == "nd":
            if "section" in c.components:
                return "ndcc"
            return "ndcc_chapter"
        return "usc"

    if c.cite_type == CitationType.CONSTITUTION:
        if c.jurisdiction == "nd":
            return "nd_const"
        if "amendment" in c.components:
            return "us_const_amendment"
        return "us_const_article"

    if c.cite_type == CitationType.REGULATION:
        if c.jurisdiction == "nd":
            return "ndac"
        return "cfr"

    if c.cite_type == CitationType.COURT_RULE:
        if c.jurisdiction == "nd":
            return "nd_court_rule"
        return "federal_rule"

    return c.cite_type.value


# ---------------------------------------------------------------------------
# Search hint generation
# ---------------------------------------------------------------------------

def _search_hint(c: Citation, legacy_type: str) -> str:
    """Build a search-friendly hint string."""
    comp = c.components

    if legacy_type == "nd_case":
        return f"{comp['year']}ND{comp['number']}"

    if legacy_type == "ndcc":
        t = f"{comp['title']}.{comp['title_dec']}" if comp.get("title_dec") else comp["title"]
        ch = f"{comp['chapter']}.{comp['chapter_dec']}" if comp.get("chapter_dec") else comp["chapter"]
        s = f"{comp['section']}.{comp['section_dec']}" if comp.get("section_dec") else comp["section"]
        return f"{t}-{ch}-{s}"

    if legacy_type == "ndcc_chapter":
        t = f"{comp['title']}.{comp['title_dec']}" if comp.get("title_dec") else comp["title"]
        ch = f"{comp['chapter']}.{comp['chapter_dec']}" if comp.get("chapter_dec") else comp["chapter"]
        return f"{t}-{ch}"

    if legacy_type == "nd_const":
        return f"art {comp['article']} sec {comp['section']}"

    if legacy_type == "ndac":
        parts = [comp.get(f"part{i}", "") for i in range(1, 5) if comp.get(f"part{i}")]
        return "-".join(parts)

    if legacy_type in ("usc", "cfr"):
        label = "USC" if legacy_type == "usc" else "CFR"
        return f"{comp['title']} {label} {comp['section']}"

    if legacy_type == "us_supreme_court":
        return f"{comp['volume']} US {comp['page']}"

    if legacy_type in ("us_const_article", "us_const_amendment"):
        if "amendment" in comp:
            return f"amendment {comp['amendment']}"
        hint = f"article {comp['article']}"
        if "section" in comp:
            hint += f" section {comp['section']}"
        return hint

    if legacy_type in ("state_case", "federal_reporter"):
        return f"{comp.get('volume', '')} {comp.get('reporter', '')} {comp.get('page', '')}"

    # Fallback: use normalized
    return c.normalized


# ---------------------------------------------------------------------------
# Primary URL extraction
# ---------------------------------------------------------------------------

def _primary_url(c: Citation) -> str | None:
    """Get the primary non-local URL from a citation's sources."""
    for s in c.sources:
        if s.name != "local":
            return s.url
    return None


# ---------------------------------------------------------------------------
# Convert jetcite Citation → legacy dict
# ---------------------------------------------------------------------------

def _to_legacy(c: Citation, refs_dir: Path) -> dict:
    """Convert a jetcite Citation to the legacy JSON dict format."""
    legacy_type = _legacy_cite_type(c)
    url = _primary_url(c)

    entry = {
        "cite_text": c.raw_text.strip(),
        "cite_type": legacy_type,
        "normalized": c.normalized,
        "url": url,
        "search_hint": _search_hint(c, legacy_type),
    }

    # Local path resolution
    rel = _citation_path(c)
    if rel is not None:
        full = refs_dir / rel
        entry["local_path"] = str(full)
        entry["local_exists"] = full.is_file()
    else:
        entry["local_path"] = None
        entry["local_exists"] = False

    return entry


# ---------------------------------------------------------------------------
# Parallel citation handling
# ---------------------------------------------------------------------------

def _add_parallel_info(entries: list[dict], citations: list[Citation]) -> None:
    """Add parallel_cite and preferred fields to legacy entries."""
    norm_to_entry = {e["normalized"]: e for e in entries}

    for cite in citations:
        if not cite.parallel_cites:
            continue
        entry = norm_to_entry.get(cite.normalized)
        if entry is None:
            continue

        # Legacy format uses singular parallel_cite (first one)
        entry["parallel_cite"] = cite.parallel_cites[0]

        # Mark preferred based on local availability
        if entry.get("local_exists"):
            entry["preferred"] = True

        # Also mark the parallel's preferred status
        parallel_entry = norm_to_entry.get(cite.parallel_cites[0])
        if parallel_entry and parallel_entry.get("local_exists"):
            parallel_entry["preferred"] = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_opinion(text: str, refs_dir: str = "~/refs") -> list[dict]:
    """Scan opinion text for all citations. Returns legacy-format dicts."""
    refs = Path(refs_dir).expanduser()
    citations = scan_text(text, refs_dir=refs)

    entries = [_to_legacy(c, refs) for c in citations]
    _add_parallel_info(entries, citations)

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
    args = parser.parse_args()

    if args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")
        results = scan_opinion(text, refs_dir=args.refs_dir)
    else:
        # stdin mode — one citation per line
        results = []
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            found = scan_opinion(line, refs_dir=args.refs_dir)
            results.extend(found)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Legacy JSON format for citation consumers (jetmemo, jetredline).

Maps jetcite's generic Citation model to the legacy dict format expected
by SKILL.md agent routing. This module is the single source of truth for
cite_type strings and search hint formatting — consumers should import
from here rather than maintaining their own mapping functions.

Cite type taxonomy:
  Cases:
    neutral_cite     — medium-neutral citations (2024 ND 156, 2022-Ohio-4635)
    regional_reporter — regional reporters (N.W.2d, P.3d, S.W.3d, etc.)
    us_supreme_court — U.S. Reports (505 U.S. 377)
    federal_reporter — federal reporters (F.3d, F. Supp. 3d, S. Ct., etc.)

  Authorities:
    statute          — statutes (N.D.C.C., U.S.C.)
    statute_chapter  — statute chapter reference without section
    regulation       — regulations (N.D.A.C., C.F.R.)
    constitution     — constitutions (U.S. Const., N.D. Const.)
    court_rule       — court rules (N.D.R.Civ.P., Fed. R. Civ. P.)
"""

from __future__ import annotations

from pathlib import Path

from jetcite.models import Citation, CitationType

# Federal case reporters — used to distinguish federal_reporter from regional_reporter
FEDERAL_REPORTERS = frozenset({
    "U.S.", "S. Ct.", "L. Ed.", "L. Ed. 2d",
    "F.", "F.2d", "F.3d", "F.4th",
    "F. Supp.", "F. Supp. 2d", "F. Supp. 3d",
    "B.R.", "F.R.D.", "Fed. Cl.", "M.J.",
    "Vet. App.", "T.C.", "F. App\u2019x", "F. App'x",
})

# All case cite types (eligible for auto-caching)
CASE_TYPES = frozenset({
    "neutral_cite", "regional_reporter", "federal_reporter", "us_supreme_court",
})

# All authority cite types
AUTHORITY_TYPES = frozenset({
    "statute", "statute_chapter", "regulation", "constitution", "court_rule",
})


def legacy_cite_type(c: Citation) -> str:
    """Map a jetcite Citation to a legacy cite_type string.

    Uses CitationType, jurisdiction, and components to produce a generic
    classification string used for agent routing and display.
    """
    if c.cite_type == CitationType.CASE:
        # Neutral citations: have year+number, no reporter
        if "year" in c.components and "number" in c.components and "reporter" not in c.components:
            return "neutral_cite"
        reporter = c.components.get("reporter", "")
        if reporter == "U.S.":
            return "us_supreme_court"
        if reporter in FEDERAL_REPORTERS:
            return "federal_reporter"
        return "regional_reporter"

    if c.cite_type == CitationType.STATUTE:
        if "section" in c.components or "part1" in c.components:
            return "statute"
        return "statute_chapter"

    if c.cite_type == CitationType.CONSTITUTION:
        return "constitution"

    if c.cite_type == CitationType.REGULATION:
        return "regulation"

    if c.cite_type == CitationType.COURT_RULE:
        return "court_rule"

    return c.cite_type.value


def search_hint(c: Citation, cite_type: str | None = None) -> str:
    """Build a search-friendly hint string from a citation.

    The hint is a compact, human-readable representation useful for
    searching court websites and legal databases.
    """
    if cite_type is None:
        cite_type = legacy_cite_type(c)
    comp = c.components

    if cite_type == "neutral_cite":
        year = comp.get("year", "")
        number = comp.get("number", "")
        # Use jurisdiction abbreviation (e.g., ND, OH, WY)
        jur = c.jurisdiction.upper() if c.jurisdiction else ""
        return f"{year}{jur}{number}"

    if cite_type == "statute":
        if c.jurisdiction == "nd":
            t = f"{comp['title']}.{comp['title_dec']}" if comp.get("title_dec") else comp.get("title", "")
            ch = f"{comp['chapter']}.{comp['chapter_dec']}" if comp.get("chapter_dec") else comp.get("chapter", "")
            s = f"{comp['section']}.{comp['section_dec']}" if comp.get("section_dec") else comp.get("section", "")
            return f"{t}-{ch}-{s}"
        # Federal / other statutes
        return f"{comp.get('title', '')} {c.jurisdiction.upper()} {comp.get('section', '')}"

    if cite_type == "statute_chapter":
        t = f"{comp['title']}.{comp['title_dec']}" if comp.get("title_dec") else comp.get("title", "")
        ch = f"{comp['chapter']}.{comp['chapter_dec']}" if comp.get("chapter_dec") else comp.get("chapter", "")
        return f"{t}-{ch}"

    if cite_type == "constitution":
        if "amendment" in comp:
            return f"amendment {comp['amendment']}"
        hint = f"article {comp.get('article', '')}"
        if "section" in comp:
            hint += f" section {comp['section']}"
        return hint

    if cite_type == "regulation":
        if c.jurisdiction == "nd":
            parts = [comp.get(f"part{i}", "") for i in range(1, 5) if comp.get(f"part{i}")]
            return "-".join(parts)
        return f"{comp.get('title', '')} CFR {comp.get('section', '')}"

    if cite_type == "us_supreme_court":
        return f"{comp.get('volume', '')} US {comp.get('page', '')}"

    if cite_type in ("federal_reporter", "regional_reporter"):
        return f"{comp.get('volume', '')} {comp.get('reporter', '')} {comp.get('page', '')}"

    if cite_type == "court_rule":
        rule_num = comp.get("rule_number") or ".".join(comp.get("parts", []))
        return rule_num

    # Fallback
    return c.normalized


def primary_url(c: Citation) -> str | None:
    """Get the primary non-local URL from a citation's sources."""
    for s in c.sources:
        if s.name != "local":
            return s.url
    return None


def to_legacy_dict(c: Citation, refs_dir: Path) -> dict:
    """Convert a jetcite Citation to the legacy JSON dict format.

    This is the canonical conversion used by both jetmemo and jetredline.
    """
    from jetcite.cache import citation_path

    ct = legacy_cite_type(c)
    url = primary_url(c)

    entry = {
        "cite_text": c.raw_text.strip(),
        "cite_type": ct,
        "normalized": c.normalized,
        "jurisdiction": c.jurisdiction,
        "url": url,
        "search_hint": search_hint(c, ct),
        "pinpoint": c.pinpoint,
    }

    rel = citation_path(c)
    if rel is not None:
        full = refs_dir / rel
        entry["local_path"] = str(full)
        entry["local_exists"] = full.is_file()
    else:
        entry["local_path"] = None
        entry["local_exists"] = False

    return entry


def add_parallel_info(entries: list[dict], citations: list[Citation]) -> None:
    """Add parallel_cite and preferred fields to legacy entries."""
    norm_to_entry = {e["normalized"]: e for e in entries}

    for cite in citations:
        if not cite.parallel_cites:
            continue
        entry = norm_to_entry.get(cite.normalized)
        if entry is None:
            continue

        entry["parallel_cite"] = cite.parallel_cites[0]

        if entry.get("local_exists"):
            entry["preferred"] = True

        parallel_entry = norm_to_entry.get(cite.parallel_cites[0])
        if parallel_entry and parallel_entry.get("local_exists"):
            parallel_entry["preferred"] = True

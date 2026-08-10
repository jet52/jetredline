"""Federal case reporter citation patterns."""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.courtlistener import courtlistener_url
from jetcite.sources.justia import us_reports_url
from jetcite.sources.usreports import us_reports_official_pdf

# The 1880s-1900s house style suffixed reporter names with "Rep." -- "112 U. S.
# Rep. 377", "82 Fed. Rep. 277", "17 Sup. Ct. Rep. 748".  The archaic forms are
# folded into the patterns below rather than given their own matcher so they
# inherit the same source construction as their modern spellings (U.S. Reports
# in particular must still reach Justia and the official-print PDF).
# The group sits BEFORE the mandatory whitespace so the unspaced print form is
# reached too.  It is OPTIONAL everywhere it appears below: 2.10.0 shipped it
# mandatory on "Fed." and "Sup. Ct." and thereby missed 855 bare "Fed." and
# 1,677 bare "Sup. Ct." sites.  What keeps these patterns honest is the digit
# on both sides -- "5 Fed. Cas. 563" and "9 Sup. Ct. Rules" are refused because
# a reporter name, not a page number, follows.
_REP = r'(?:\s*Rep\.)?'

# U.S. Reports: 505 U.S. 377 (also West's spaced "260 U. S. 22")
_US_REPORTS = re.compile(r'(\d+)\s+U\.\s?S\.' + _REP + r'\s+(\d+)')

# Federal Reporter, modern series (mandatory): 491 F.3d 355, 731 F.2d 909, 12 F.4th 100
_FEDERAL = re.compile(r'(\d+)\s+F\.\s?(2d|3d|4th)\s+(\d+)')

# Federal Reporter, first series (1880-1924): 200 F. 100, archaic "82 Fed. Rep.
# 277".  Negative lookahead refuses "F. 3d", "F. Supp.", "F. App'x" so the
# engine can't backtrack into the modern-series suffix and produce a truncated
# page.  "Fed. Rep." needs its own branch because `F\.` cannot reach the "F" of
# "Fed." -- and it requires the "Rep.", since a bare "Fed." is prose here.
_FEDERAL_FIRST = re.compile(
    r"(\d+)\s+(?:F\.(?!\s?(?:\d+(?:d|th)|Supp\.|App[’']x))\s+|Fed\." + _REP + r"\s*)(\d+)"
)


def _normalize_reporter(base: str, edition: str | None) -> str:
    """Normalize reporter name, collapsing 'F. 3d' to 'F.3d' etc."""
    if edition:
        return f"{base}{edition}"
    return base

# S. Ct.: 140 S. Ct. 1731, plus "1 Sup. Ct. 389" / "17 Sup. Ct. Rep. 748" and
# "10 S. C. Rep. 873".
#
# The "Rep." is optional on "Sup. Ct." but MANDATORY on "S. C." -- and that
# asymmetry is the whole point.  "S. C. Rep." is the Supreme Court Reporter,
# but a BARE "S. C." is South Carolina, so dropping the requirement there would
# silently re-point every South Carolina cite at the U.S. Supreme Court.
# regional.py's state pattern matches the unspaced "S.C." and so cannot reach
# the spaced form today, which is exactly why this branch is spelled out here
# rather than left to look like a state cite.
_S_CT = re.compile(
    r'(\d+)\s+(?:S\.\s?Ct\.|Sup\.\s*Ct\.' + _REP + r'|S\.\s?C\.\s*Rep\.)\s+(\d+)')

# F. Supp. 2d, F. Supp. 3d (mandatory series)
_F_SUPP = re.compile(r'(\d+)\s+F\.\s?Supp\.\s?(2d|3d)\s+(\d+)')

# F. Supp. first series (1932-1988): 100 F. Supp. 200
_F_SUPP_FIRST = re.compile(r'(\d+)\s+F\.\s?Supp\.(?!\s?[23]d)\s+(\d+)')

# L. Ed., L. Ed. 2d
_L_ED = re.compile(r'(\d+)\s+L\.\s?Ed\.\s?(?:(2d)\s+)?(\d+)')

# B.R.
_BR = re.compile(r'(\d+)\s+B\.\s?R\.\s+(\d+)')

# F.R.D.
_FRD = re.compile(r'(\d+)\s+F\.\s?R\.\s?D\.\s+(\d+)')

# Fed. Cl.
_FED_CL = re.compile(r'(\d+)\s+Fed\.\s?Cl\.\s+(\d+)')

# M.J.
_MJ = re.compile(r'(\d+)\s+M\.\s?J\.\s+(\d+)')

# Vet. App.
_VET_APP = re.compile(r'(\d+)\s+Vet\.\s?App\.\s+(\d+)')

# T.C.
_TC = re.compile(r'(\d+)\s+T\.\s?C\.\s+(\d+)')

# F. App'x (handles curly and straight apostrophe)
_F_APPX = re.compile(r"(\d+)\s+F\.\s?App[\u2019']x\s+(\d+)")


def _make_reporter_name(base: str, edition: str | None) -> str:
    if edition:
        return f"{base} {edition}"
    return base


class FederalCaseMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results = []

        # U.S. Reports -> Justia (fetchable), plus a link-only official-print
        # PDF (LOC per-case scan, or the Court's bound volume). Appended last
        # so fetch_and_cache never downloads it.
        for m in _US_REPORTS.finditer(text):
            volume, page = m.group(1), m.group(2)
            sources = [
                Source("justia", us_reports_url(volume, page)),
                Source("courtlistener", courtlistener_url("U.S.", volume, page)),
            ]
            official = us_reports_official_pdf(volume, page)
            if official:
                sources.append(Source("official_pdf", official))
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} U.S. {page}",
                components={"volume": volume, "reporter": "U.S.", "page": page},
                sources=sources,
                position=m.start(),
            ))

        # Federal Reporter (modern series: F.2d, F.3d, F.4th)
        for m in _FEDERAL.finditer(text):
            volume, edition, page = m.group(1), m.group(2), m.group(3)
            reporter = _normalize_reporter("F.", edition)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} {reporter} {page}",
                components={"volume": volume, "reporter": reporter, "page": page},
                sources=[Source("courtlistener",
                                courtlistener_url(reporter, volume, page))],
                position=m.start(),
            ))

        # Federal Reporter (first series, no edition marker)
        for m in _FEDERAL_FIRST.finditer(text):
            volume, page = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} F. {page}",
                components={"volume": volume, "reporter": "F.", "page": page},
                sources=[Source("courtlistener",
                                courtlistener_url("F.", volume, page))],
                position=m.start(),
            ))

        # S. Ct.
        for m in _S_CT.finditer(text):
            volume, page = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} S. Ct. {page}",
                components={"volume": volume, "reporter": "S. Ct.", "page": page},
                sources=[Source("courtlistener",
                                courtlistener_url("S. Ct.", volume, page))],
                position=m.start(),
            ))

        # F. Supp. 2d / F. Supp. 3d (modern series)
        for m in _F_SUPP.finditer(text):
            volume, edition, page = m.group(1), m.group(2), m.group(3)
            reporter = _make_reporter_name("F. Supp.", edition)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} {reporter} {page}",
                components={"volume": volume, "reporter": reporter, "page": page},
                sources=[Source("courtlistener",
                                courtlistener_url(reporter, volume, page))],
                position=m.start(),
            ))

        # F. Supp. first series (1932-1988)
        for m in _F_SUPP_FIRST.finditer(text):
            volume, page = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} F. Supp. {page}",
                components={"volume": volume, "reporter": "F. Supp.", "page": page},
                sources=[Source("courtlistener",
                                courtlistener_url("F. Supp.", volume, page))],
                position=m.start(),
            ))

        # L. Ed.
        for m in _L_ED.finditer(text):
            volume, edition, page = m.group(1), m.group(2), m.group(3)
            reporter = _make_reporter_name("L. Ed.", edition)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} {reporter} {page}",
                components={"volume": volume, "reporter": reporter, "page": page},
                sources=[Source("courtlistener",
                                courtlistener_url(reporter, volume, page))],
                position=m.start(),
            ))

        # Simple two-group reporters
        for pattern, reporter_name in [
            (_BR, "B.R."), (_FRD, "F.R.D."), (_FED_CL, "Fed. Cl."),
            (_MJ, "M.J."), (_VET_APP, "Vet. App."), (_TC, "T.C."),
            (_F_APPX, "F. App'x"),
        ]:
            for m in pattern.finditer(text):
                volume, page = m.group(1), m.group(2)
                results.append(Citation(
                    raw_text=m.group(0),
                    cite_type=CitationType.CASE,
                    jurisdiction="us",
                    normalized=f"{volume} {reporter_name} {page}",
                    components={"volume": volume, "reporter": reporter_name,
                                "page": page},
                    sources=[Source("courtlistener",
                                    courtlistener_url(reporter_name, volume, page))],
                    position=m.start(),
                ))

        return results


register(7, FederalCaseMatcher())

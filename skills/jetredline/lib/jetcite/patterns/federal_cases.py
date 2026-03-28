"""Federal case reporter citation patterns."""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.courtlistener import courtlistener_url
from jetcite.sources.justia import us_reports_url

# U.S. Reports: 505 U.S. 377
_US_REPORTS = re.compile(r'(\d+)\s+U\.S\.\s+(\d+)')

# Federal Reporter: F., F.2d, F.3d, F.4th
_FEDERAL = re.compile(r'(\d+)\s+F\.\s?(?:(2d|3d|4th)\s+)?(\d+)')


def _normalize_reporter(base: str, edition: str | None) -> str:
    """Normalize reporter name, collapsing 'F. 3d' to 'F.3d' etc."""
    if edition:
        return f"{base}{edition}"
    return base

# S. Ct.: 140 S. Ct. 1731
_S_CT = re.compile(r'(\d+)\s+S\.\s?Ct\.\s+(\d+)')

# F. Supp., F. Supp. 2d, F. Supp. 3d
_F_SUPP = re.compile(r'(\d+)\s+F\.\s?Supp\.\s?(?:(2d|3d)\s+)?(\d+)')

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

        # U.S. Reports -> Justia
        for m in _US_REPORTS.finditer(text):
            volume, page = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="us",
                normalized=f"{volume} U.S. {page}",
                components={"volume": volume, "reporter": "U.S.", "page": page},
                sources=[
                    Source("justia", us_reports_url(volume, page)),
                    Source("courtlistener", courtlistener_url("U.S.", volume, page)),
                ],
                position=m.start(),
            ))

        # Federal Reporter
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

        # F. Supp.
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

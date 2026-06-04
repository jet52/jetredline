"""Medium-neutral state case citation patterns."""

import re

from jetcite.cleanup import preprocess_document_text
from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.courtlistener import courtlistener_neutral_url
from jetcite.sources.ndcourts import nd_opinion_url

# Inter-token gap inside a single neutral citation: horizontal whitespace,
# tolerating at most ONE line break (a soft wrap) but never a blank line. This
# stops a number on the far side of a page/paragraph break — e.g. a page-number
# footer — from being captured as the opinion number. Page furniture is stripped
# upstream by preprocess_document_text; this is the defense-in-depth backstop.
# See TODO.md, "Plan: Page-break citation splice."
_WS = r'(?:[^\S\n]*\n[^\S\n]*|[^\S\n]+)'

# ND neutral: 2024 ND 156
_ND_NEUTRAL = re.compile(
    r'([12]\d{3})' + _WS + r'ND' + _WS + r'(\d{1,3})'
    r'(?:,?\s*(?:¶¶?\s*(\d+(?:\s*[-–]\s*\d+)?)))?'  # optional pinpoint
)

# Ohio: 2018-Ohio-3237
_OHIO_NEUTRAL = re.compile(r'(\d{4})-Ohio-(\d+)')

# New Mexico: 2009-NMSC-006
_NM_NEUTRAL = re.compile(r'(\d{4})-(NM(?:SC|CA))-(\d+)')

# Illinois: 2011 IL 102345 or 2011 IL App (1st) 101234
_IL_NEUTRAL = re.compile(r'(\d{4})' + _WS + r'IL(?:' + _WS + r'App(?:' + _WS + r'\([^)]+\))?)?' + _WS + r'(\d+)')

# Standard neutral citations: YYYY {abbrev} NNN
# Arkansas, Colorado, Guam, Maine, Montana, N. Mariana Is., Oklahoma,
# South Dakota, Utah, Vermont, Wisconsin, Wyoming, Arizona, New Hampshire
_STANDARD_NEUTRAL = re.compile(
    r'([12]\d{3})' + _WS +
    r'(Ark\.(?:\s+App\.)?|CO|Guam|ME|MT|MP|N\.H\.|OK|S\.D\.|UT(?:\s+App)?|VT|WI|WY|AZ)'
    + _WS + r'(\d+)'
)

# North Carolina: 2021-NCSC-57 or 2021-NCCA-57
_NC_NEUTRAL = re.compile(r'(\d{4})-(NC(?:SC|CA))-(\d+)')

# Mississippi: 2017-CA-01472-SCT
_MS_NEUTRAL = re.compile(r'(\d{4})-((?:CA|CT|SA|KA|IA)-\d+-(?:SCT|COA))')

# Pennsylvania: 1999 PA Super 1
_PA_NEUTRAL = re.compile(r'(\d{4})' + _WS + r'PA' + _WS + r'(?:Super' + _WS + r')?(\d+)')

# Puerto Rico: 2015 TSPR 148
_PR_NEUTRAL = re.compile(r'(\d{4})' + _WS + r'TSPR' + _WS + r'(\d+)')

# Louisiana: 93-2345 (La. 7/15/94) - more complex format, skip for now


class NeutralCitationMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        # Strip page furniture (footers, running headers) so a citation split
        # across a page break rejoins before matching. Idempotent, so this is
        # safe even when scan_text has already preprocessed the text.
        text = preprocess_document_text(text)
        results = []

        # ND opinions: start with the ndcourts.gov search URL. The direct
        # opinion PDF URL is resolved later (network) by scanner.scan_text when
        # resolve=True, so matching stays pure and offline-safe.
        for m in _ND_NEUTRAL.finditer(text):
            year, number = m.group(1), m.group(2)
            pinpoint = m.group(3)
            sources = [Source("ndcourts", nd_opinion_url(year, number))]
            sources.append(Source("courtlistener",
                                  courtlistener_neutral_url("ND", year, number)))
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="nd",
                normalized=f"{year} ND {number}",
                components={"year": year, "number": number},
                pinpoint=f"¶ {pinpoint}" if pinpoint else None,
                sources=sources,
                position=m.start(),
            ))

        # Ohio
        for m in _OHIO_NEUTRAL.finditer(text):
            year, number = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="oh",
                normalized=f"{year}-Ohio-{number}",
                components={"year": year, "number": number},
                sources=[Source("courtlistener",
                                courtlistener_neutral_url("Ohio", year, number))],
                position=m.start(),
            ))

        # New Mexico
        for m in _NM_NEUTRAL.finditer(text):
            year, court, number = m.group(1), m.group(2), m.group(3)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="nm",
                normalized=f"{year}-{court}-{number}",
                components={"year": year, "court": court, "number": number},
                sources=[Source("courtlistener",
                                courtlistener_neutral_url(court, year, number))],
                position=m.start(),
            ))

        # Illinois
        for m in _IL_NEUTRAL.finditer(text):
            year, number = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="il",
                normalized=f"{year} IL {number}",
                components={"year": year, "number": number},
                sources=[Source("courtlistener",
                                courtlistener_neutral_url("IL", year, number))],
                position=m.start(),
            ))

        # North Carolina
        for m in _NC_NEUTRAL.finditer(text):
            year, court, number = m.group(1), m.group(2), m.group(3)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="nc",
                normalized=f"{year}-{court}-{number}",
                components={"year": year, "court": court, "number": number},
                sources=[Source("courtlistener",
                                courtlistener_neutral_url(court, year, number))],
                position=m.start(),
            ))

        # Pennsylvania
        for m in _PA_NEUTRAL.finditer(text):
            year, number = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="pa",
                normalized=f"{year} PA Super {number}",
                components={"year": year, "number": number},
                sources=[Source("courtlistener",
                                courtlistener_neutral_url("PA%20Super", year, number))],
                position=m.start(),
            ))

        # Puerto Rico
        for m in _PR_NEUTRAL.finditer(text):
            year, number = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction="pr",
                normalized=f"{year} TSPR {number}",
                components={"year": year, "number": number},
                sources=[Source("courtlistener",
                                courtlistener_neutral_url("TSPR", year, number))],
                position=m.start(),
            ))

        # Standard neutral citations (Ark., CO, ME, MT, etc.)
        for m in _STANDARD_NEUTRAL.finditer(text):
            year, abbrev, number = m.group(1), m.group(2), m.group(3)
            # Map abbreviation to jurisdiction
            jur_map = {
                "CO": "co", "ME": "me", "MT": "mt", "OK": "ok",
                "VT": "vt", "WI": "wi", "WY": "wy", "AZ": "az",
                "Guam": "gu", "MP": "mp", "N.H.": "nh",
            }
            # Handle Ark., S.D., UT variants
            if abbrev.startswith("Ark"):
                jur = "ar"
            elif abbrev.startswith("S.D"):
                jur = "sd"
            elif abbrev.startswith("UT"):
                jur = "ut"
            else:
                jur = jur_map.get(abbrev, abbrev.lower())

            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CASE,
                jurisdiction=jur,
                normalized=f"{year} {abbrev} {number}",
                components={"year": year, "abbreviation": abbrev, "number": number},
                sources=[Source("courtlistener",
                                courtlistener_neutral_url(abbrev, year, number))],
                position=m.start(),
            ))

        return results


register(5, NeutralCitationMatcher())

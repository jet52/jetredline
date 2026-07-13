"""Arizona-specific citation patterns: A.R.S., A.A.C., Ariz. Constitution, and
Arizona court rules.

Court rules have no citation-derivable official URL (Arizona serves rule text
through an opaque azcourts.gov viewer), so a recognized rule cite links to the
official rules index rather than a specific rule. Opinions are not matched here:
they are keyed by docket (not by cite) and Arizona has no medium-neutral
citation; they are linked incidentally via the Pacific Reporter matcher
(regional.py) routed to CourtListener.
"""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.azcourts import az_court_rule_url
from jetcite.sources.azleg import ars_section_url, az_constitution_url
from jetcite.sources.azsos import aac_chapter_url

# ---------------------------------------------------------------------------
# A.R.S. statutes: A.R.S. § 13-1105, Ariz. Rev. Stat. Ann. § 12-821.01
# ---------------------------------------------------------------------------
# The label is matched case-sensitively (statutes are cited "A.R.S." / "Ariz.
# Rev. Stat."), and a preceding-letter guard blocks false hits like "cars 1-2".
_ARS = re.compile(
    r'(?<![A-Za-z])'
    r'(?:A\.?\s?R\.?\s?S\.?|Ariz\.?\s+Rev\.?\s+Stat\.?(?:\s+Ann\.?)?)'
    r'\s*(?:§§?\s*|[Ss]ections?\s+|[Ss]ec\.?\s+)?'
    r'(\d+)-(\d+)(?:\.(\d+))?'
    r'(?:\([A-Za-z0-9]+\))*'
)

# ---------------------------------------------------------------------------
# A.A.C. administrative code: A.A.C. R20-6-201, Ariz. Admin. Code R20-6-201
# ---------------------------------------------------------------------------
_AAC = re.compile(
    r'(?<![A-Za-z])'
    r'(?:A\.?\s?A\.?\s?C\.?|Ariz\.?\s*Admin\.?\s*Code)'
    r'\s*(?:§\s*)?'
    r'R?\s*(\d+)-(\d+)-(\d+(?:\.\d+)?)'
)

# ---------------------------------------------------------------------------
# Arizona Constitution: Ariz. Const. art. 2, § 4 (art. 4 has Parts)
# ---------------------------------------------------------------------------
_AZ_CONST = re.compile(
    r'Ariz\.?\s*Const(?:itution)?\.?\s*,?\s*'
    r'(?:art\.?|[Aa]rticle)\s*([IVXLC]+|\d+)'
    r'(?:\s*,?\s*(?:pt\.?|[Pp]art)\s*(\d+))?'
    r'\s*,?\s*(?:§§?|[Ss]ec(?:tion)?s?\.?)\s*(\d+)',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Arizona court rules: Ariz. R. Civ. P. 12, Ariz. R. Evid. 401, etc.
# The family must be one or more known rule-set tokens (this both parses the
# family and prevents "Ariz. Rev. Stat." from being mis-read as a rule). The
# rule number is captured only for the normalized form; every rule set links to
# the same official rules index (no citation-derivable per-rule URL exists).
# ---------------------------------------------------------------------------
_FAM_TOKEN = r'(?:Civ|Crim|Evid|Fam|Prob|Sup|Juv|App|Ct|Law|P)\.?'
_AZ_RULE = re.compile(
    r'Ariz\.?\s*R\.?\s+'
    r'(' + _FAM_TOKEN + r'(?:\s*' + _FAM_TOKEN + r'){0,3})'
    r'\s+(\d+(?:\.\d+)?)'
    r'(?:\([A-Za-z0-9]+\))*'
)


def _az_family(raw: str) -> str:
    """Normalize a court-rule family token run to a canonical abbreviation."""
    r = raw.lower()
    if "app" in r:
        return "Civ. App. P."
    if "crim" in r:
        return "Crim. P."
    if "civ" in r:
        return "Civ. P."
    if "evid" in r:
        return "Evid."
    if "fam" in r:
        return "Fam. Law P."
    if "prob" in r:
        return "Prob. P."
    if "juv" in r:
        return "P. Juv. Ct."
    if "sup" in r:
        return "Sup. Ct."
    return re.sub(r"\s+", " ", raw.strip())


class AZMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results: list[Citation] = []
        self._match_ars(text, results)
        self._match_aac(text, results)
        self._match_const(text, results)
        self._match_rules(text, results)
        # Keep the longest match at any given start position.
        by_pos: dict[int, Citation] = {}
        for cite in results:
            if (cite.position not in by_pos
                    or len(cite.raw_text) > len(by_pos[cite.position].raw_text)):
                by_pos[cite.position] = cite
        return sorted(by_pos.values(), key=lambda c: c.position)

    def _match_ars(self, text: str, results: list[Citation]):
        for m in _ARS.finditer(text):
            title, section, section_dec = m.group(1), m.group(2), m.group(3)
            section_full = f"{section}.{section_dec}" if section_dec else section
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.STATUTE,
                jurisdiction="az",
                normalized=f"A.R.S. § {title}-{section_full}",
                components={
                    "title": title, "section": section, "section_dec": section_dec,
                },
                sources=[Source("azleg",
                                ars_section_url(title, section, section_dec))],
                position=m.start(),
            ))

    def _match_aac(self, text: str, results: list[Citation]):
        for m in _AAC.finditer(text):
            title, chapter, section = m.group(1), m.group(2), m.group(3)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.REGULATION,
                jurisdiction="az",
                normalized=f"Ariz. Admin. Code R{title}-{chapter}-{section}",
                components={"title": title, "chapter": chapter, "section": section},
                sources=[Source("azsos", aac_chapter_url(title, chapter))],
                position=m.start(),
            ))

    def _match_const(self, text: str, results: list[Citation]):
        for m in _AZ_CONST.finditer(text):
            article, part, section = m.group(1), m.group(2), m.group(3)
            arabic = article if article.isdigit() else None
            if arabic is None:
                from jetcite.patterns.base import roman_to_int
                arabic = str(roman_to_int(article))
            if part:
                normalized = f"Ariz. Const. art. {arabic}, pt. {part}, § {section}"
            else:
                normalized = f"Ariz. Const. art. {arabic}, § {section}"
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="az",
                normalized=normalized,
                components={"article": arabic, "part": part, "section": section},
                sources=[Source("azleg",
                                az_constitution_url(article, section, part))],
                position=m.start(),
            ))

    def _match_rules(self, text: str, results: list[Citation]):
        for m in _AZ_RULE.finditer(text):
            family = _az_family(m.group(1))
            rule = m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.COURT_RULE,
                jurisdiction="az",
                normalized=f"Ariz. R. {family} {rule}",
                components={"family": family, "rule": rule},
                sources=[Source("azcourts", az_court_rule_url())],
                position=m.start(),
            ))


register(4, AZMatcher())

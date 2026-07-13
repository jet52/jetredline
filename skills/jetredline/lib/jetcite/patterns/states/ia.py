"""Iowa-specific citation patterns: Iowa Code, Iowa Admin. Code, Iowa Court
Rules, and Iowa Constitution.

Opinions are not matched here: Iowa has no medium-neutral citation and the
Judicial Branch keys opinions by opaque CMS id, not by cite. Modern Iowa
opinions appear only in N.W.2d, already linked via the regional reporter matcher
(regional.py) routed to CourtListener.
"""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.ialegis import (
    IOWA_CONSTITUTION_URL,
    iowa_admin_rule_url,
    iowa_code_url,
    iowa_court_rule_url,
)

# ---------------------------------------------------------------------------
# Iowa Code: Iowa Code § 707.2 (chapter.section); chapter-only: ch. 707
# ---------------------------------------------------------------------------
_IOWA_CODE_SECTION = re.compile(
    r'Iowa\s+Code(?:\s+Ann\.?)?\s*'
    r'(?:§§?\s*|[Ss]ections?\s+|[Ss]ec\.?\s+)?'
    r'(\d+[A-Z]?)\.(\d+[A-Z]?)'
    r'(?:\([A-Za-z0-9]+\))*'
)

_IOWA_CODE_CHAPTER = re.compile(
    r'Iowa\s+Code(?:\s+Ann\.?)?\s+'
    r'ch(?:apter|\.)\s*'
    r'(\d+[A-Z]?)'
    r'(?![.\d])',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Iowa Administrative Code: Iowa Admin. Code r. 657-8.1 (agency-rule)
# ---------------------------------------------------------------------------
_IOWA_ADMIN = re.compile(
    r'Iowa\s+Admin\.?\s*Code(?:\s+Ann\.?)?\s*'
    r'(?:r\.?\s*|rule\s+|§\s*)?'
    r'(\d+)-(\d+\.\d+)'
    r'(?:\([A-Za-z0-9]+\))*'
)

# ---------------------------------------------------------------------------
# Iowa Court Rules: Iowa R. Civ. P. 1.302, Iowa R. App. P. 6.904, etc.
# The integer before the dot in the rule number is the chapter (Civ->1,
# Crim->2, Evid->5, App->6), which is what the whole-chapter PDF is keyed on.
# ---------------------------------------------------------------------------
_IOWA_COURT_RULE = re.compile(
    r'Iowa\s+R\.?\s*([A-Za-z][A-Za-z.\' ]{0,20}?)\s*(\d+)\.(\d+)'
)

# ---------------------------------------------------------------------------
# Iowa Constitution: Iowa Const. art. I, § 8
# ---------------------------------------------------------------------------
_IOWA_CONST = re.compile(
    r'Iowa\s+Const(?:itution)?\.?\s*,?\s*'
    r'(?:art\.?|[Aa]rticle)\s*([IVXLC]+|\d+)'
    r'\s*,?\s*(?:§§?|[Ss]ec(?:tion)?s?\.?)\s*(\d+)',
    re.IGNORECASE,
)


def _iowa_family(raw: str) -> str:
    """Normalize a court-rule family token to a canonical Bluebook abbreviation."""
    r = raw.lower()
    if "civ" in r:
        return "Civ. P."
    if "crim" in r:
        return "Crim. P."
    if "evid" in r:
        return "Evid."
    if "app" in r:
        return "App. P."
    if "juv" in r:
        return "Juv. P."
    return "Ct."


class IAMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results: list[Citation] = []
        self._match_code(text, results)
        self._match_admin(text, results)
        self._match_rules(text, results)
        self._match_const(text, results)
        # Keep the longest match at any given start position.
        by_pos: dict[int, Citation] = {}
        for cite in results:
            if (cite.position not in by_pos
                    or len(cite.raw_text) > len(by_pos[cite.position].raw_text)):
                by_pos[cite.position] = cite
        return sorted(by_pos.values(), key=lambda c: c.position)

    def _match_code(self, text: str, results: list[Citation]):
        for m in _IOWA_CODE_SECTION.finditer(text):
            chapter, section = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.STATUTE,
                jurisdiction="ia",
                normalized=f"Iowa Code § {chapter}.{section}",
                components={"chapter": chapter, "section": section},
                sources=[Source("ialegis", iowa_code_url(chapter, section))],
                position=m.start(),
            ))

        for m in _IOWA_CODE_CHAPTER.finditer(text):
            chapter = m.group(1)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.STATUTE,
                jurisdiction="ia",
                normalized=f"Iowa Code ch. {chapter}",
                components={"chapter": chapter},
                sources=[Source("ialegis", iowa_code_url(chapter))],
                position=m.start(),
            ))

    def _match_admin(self, text: str, results: list[Citation]):
        for m in _IOWA_ADMIN.finditer(text):
            agency, rule = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.REGULATION,
                jurisdiction="ia",
                normalized=f"Iowa Admin. Code r. {agency}-{rule}",
                components={"agency": agency, "rule": rule},
                sources=[Source("ialegis", iowa_admin_rule_url(agency, rule))],
                position=m.start(),
            ))

    def _match_rules(self, text: str, results: list[Citation]):
        for m in _IOWA_COURT_RULE.finditer(text):
            family = _iowa_family(m.group(1))
            chapter, rule = m.group(2), m.group(3)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.COURT_RULE,
                jurisdiction="ia",
                normalized=f"Iowa R. {family} {chapter}.{rule}",
                components={"family": family, "chapter": chapter, "rule": rule},
                sources=[Source("ialegis", iowa_court_rule_url(chapter))],
                position=m.start(),
            ))

    def _match_const(self, text: str, results: list[Citation]):
        for m in _IOWA_CONST.finditer(text):
            article, section = m.group(1).upper(), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="ia",
                normalized=f"Iowa Const. art. {article}, § {section}",
                components={"article": article, "section": section},
                sources=[Source("ialegis", IOWA_CONSTITUTION_URL)],
                position=m.start(),
            ))


register(4, IAMatcher())

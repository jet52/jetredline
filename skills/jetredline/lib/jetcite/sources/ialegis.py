"""legis.iowa.gov URL generation for Iowa statutes, admin code, and court rules.

URL patterns were verified live by fetching and matching the document text
(see SCOPE-az-ia.md):
  Iowa Code § 707.2        -> https://www.legis.iowa.gov/docs/code/707.2.pdf
  Iowa Admin. Code r. 657-8.1 -> https://www.legis.iowa.gov/docs/aco/rule/657.8.1.pdf
  Iowa R. Civ. P. 1.302    -> https://www.legis.iowa.gov/docs/ACO/CourtRulesChapter/1.pdf

The Iowa Constitution is published only as a whole-document codified PDF at an
opaque publication id; there is no per-article/section URL, so all Iowa
Constitution citations resolve to that single document.
"""

from __future__ import annotations

# Official codified Iowa Constitution PDF (whole document; opaque publication id).
IOWA_CONSTITUTION_URL = "https://www.legis.iowa.gov/docs/publications/icnst/402726.pdf"


def iowa_code_url(chapter: str, section: str | None = None) -> str:
    """Generate a legis.iowa.gov URL for an Iowa Code section or chapter PDF.

    A section citation ("707.2") maps directly to the file basename. A
    chapter-only citation (no section) links to the whole-chapter PDF.
    """
    if section:
        return f"https://www.legis.iowa.gov/docs/code/{chapter}.{section}.pdf"
    return f"https://www.legis.iowa.gov/docs/code/{chapter}.pdf"


def iowa_admin_rule_url(agency: str, rule: str) -> str:
    """Generate a legis.iowa.gov URL for an Iowa Administrative Code rule PDF.

    The citation "657-8.1" (agency 657, rule 8.1) maps to
    ``/docs/aco/rule/657.8.1.pdf`` (hyphen -> dot). Rule-level only; the chapter
    endpoint serves the wrong document and is deliberately not used.
    """
    return f"https://www.legis.iowa.gov/docs/aco/rule/{agency}.{rule}.pdf"


def iowa_court_rule_url(chapter: str) -> str:
    """Generate a legis.iowa.gov URL for an Iowa Court Rules chapter PDF.

    Iowa court rules are numbered ``{chapter}.{rule}``; the integer chapter maps
    to a whole-chapter PDF. There is no rule-level in-document anchor.
    """
    return f"https://www.legis.iowa.gov/docs/ACO/CourtRulesChapter/{chapter}.pdf"

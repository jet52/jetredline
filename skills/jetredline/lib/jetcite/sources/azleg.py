"""azleg.gov URL generation for Arizona statutes and constitution.

URL patterns were verified live (see SCOPE-az-ia.md):
  A.R.S. § 13-1105     -> https://www.azleg.gov/ars/13/01105.htm
  A.R.S. § 12-821.01   -> https://www.azleg.gov/ars/12/00821-01.htm
  Ariz. Const. art. 2, § 4        -> https://www.azleg.gov/const/2/4.htm
  Ariz. Const. art. 4, pt. 2, § 2 -> https://www.azleg.gov/const/4/2.p2.htm
"""

from __future__ import annotations

from jetcite.patterns.base import roman_to_int


def ars_section_url(title: str, section: str, section_dec: str | None = None) -> str:
    """Generate an azleg.gov URL for an A.R.S. section.

    The section base is zero-padded to five digits; a decimal component is
    appended after a dash (dot -> dash), matching azleg's file naming.
    """
    base = section.zfill(5)
    file = f"{base}-{section_dec}" if section_dec else base
    return f"https://www.azleg.gov/ars/{title}/{file}.htm"


def az_constitution_url(article: str, section: str, part: str | None = None) -> str:
    """Generate an azleg.gov URL for an Arizona Constitution section.

    ``article`` may be arabic or roman; it is normalized to arabic. Article 4 is
    split into Parts, whose sections take a ``.p{part}`` suffix. A part is only
    used when supplied by the citation.
    """
    art = article if article.isdigit() else str(roman_to_int(article))
    if part:
        return f"https://www.azleg.gov/const/{art}/{section}.p{part}.htm"
    return f"https://www.azleg.gov/const/{art}/{section}.htm"

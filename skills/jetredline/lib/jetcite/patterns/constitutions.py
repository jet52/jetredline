"""U.S. Constitution and state constitution citation patterns."""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.constitutioncenter import (
    us_constitution_amendment_url,
    us_constitution_article_url,
)

# U.S. Const. art. III, § 2
_US_CONST_ART_SEC = re.compile(
    r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?[.\s]*'
    r'(?:art\.|[Aa]rticle)\s*([IVX]+)[,\s]*(?:§|[Ss]ec(?:tion)?\.?)\s*(\d+)',
    re.IGNORECASE,
)

# Article III of the U.S. Constitution
_US_CONST_ART_OF = re.compile(
    r'[Aa]rticle\s+([IVX]+)\s+of\s+the\s+'
    r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?',
    re.IGNORECASE,
)

# U.S. Const. amend. XIV
_US_CONST_AMEND = re.compile(
    r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?[.\s]*'
    r'(?:amend\.|[Aa]mendment)\s*([IVX]+)'
    r'(?:[,\s]*(?:§|[Ss]ec(?:tion)?\.?)\s*(\d+))?',
    re.IGNORECASE,
)

# Amendment XIV to the U.S. Constitution
_US_CONST_AMEND_TO = re.compile(
    r'[Aa]mendment\s+([IVX]+)\s+to\s+the\s+'
    r'U(?:nited)?[\s.]*S(?:tates)?[\s.]*Const(?:itution)?',
    re.IGNORECASE,
)


class USConstitutionMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results = []

        for m in _US_CONST_ART_SEC.finditer(text):
            article, section = m.group(1), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="us",
                normalized=f"U.S. Const. art. {article.upper()}, § {section}",
                components={"article": article.upper(), "section": section},
                sources=[Source("constitutioncenter",
                                us_constitution_article_url(article, section))],
                position=m.start(),
            ))

        for m in _US_CONST_ART_OF.finditer(text):
            article = m.group(1)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="us",
                normalized=f"U.S. Const. art. {article.upper()}",
                components={"article": article.upper()},
                sources=[Source("constitutioncenter",
                                us_constitution_article_url(article))],
                position=m.start(),
            ))

        for m in _US_CONST_AMEND.finditer(text):
            amendment = m.group(1)
            section = m.group(2)
            normalized = f"U.S. Const. amend. {amendment.upper()}"
            components = {"amendment": amendment.upper()}
            if section:
                normalized += f", § {section}"
                components["section"] = section
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="us",
                normalized=normalized,
                components=components,
                sources=[Source("constitutioncenter",
                                us_constitution_amendment_url(amendment))],
                position=m.start(),
            ))

        for m in _US_CONST_AMEND_TO.finditer(text):
            amendment = m.group(1)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="us",
                normalized=f"U.S. Const. amend. {amendment.upper()}",
                components={"amendment": amendment.upper()},
                sources=[Source("constitutioncenter",
                                us_constitution_amendment_url(amendment))],
                position=m.start(),
            ))

        return results


register(1, USConstitutionMatcher())

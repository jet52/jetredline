"""Federal statute citation patterns: U.S.C. and C.F.R."""

import re

from jetcite.enumeration import EnumSpec, expand_enumerations
from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.ecfr import cfr_url
from jetcite.sources.govinfo import usc_url

# 42 U.S.C. § 1983
_USC = re.compile(
    r'(\d+)\s*U[\s.]*S[\s.]*C(?:ode)?[,.\s]*(?:§§?\s*|[Ss]ec(?:tion)?\.?\s+)(\d+[a-z]?)'
    r'(?:[-–](\d+[a-z]?))?'  # optional range: §§ 1983-1985
    r'((?:\([^)]+\))*)',  # optional subsections: (a)(1)
    re.IGNORECASE,
)

# 29 C.F.R. § 1910.1200
_CFR = re.compile(
    r'(\d+)\s*C[\s.]*F[\s.]*R(?:eg)?[,.\s]*(?:§§?\s*|[Ss]ec(?:tion)?\.?\s+)?(\d+(?:\.\d+)*)'
    r'((?:\([^)]+\))*)',  # optional subsections
    re.IGNORECASE,
)


class FederalStatuteMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results = []

        for m in _USC.finditer(text):
            title, section = m.group(1), m.group(2)
            subsection = m.group(4) or ""
            normalized = f"{title} U.S.C. § {section}"
            if subsection:
                normalized += subsection
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.STATUTE,
                jurisdiction="us",
                normalized=normalized,
                components={"title": title, "section": section,
                            "subsection": subsection or None},
                sources=[Source("govinfo", usc_url(title, section))],
                position=m.start(),
            ))

        for m in _CFR.finditer(text):
            title, section = m.group(1), m.group(2)
            subsection = m.group(3) or ""
            normalized = f"{title} C.F.R. § {section}"
            if subsection:
                normalized += subsection
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.REGULATION,
                jurisdiction="us",
                normalized=normalized,
                components={"title": title, "section": section,
                            "subsection": subsection or None},
                sources=[Source("ecfr", cfr_url(title, section))],
                position=m.start(),
            ))

        # Recover the tail members of an enumerated list —
        # "42 U.S.C. §§ 1983, 1985, and 1988". The title is stated once and
        # inherited; only the section number varies, so these are arity-1
        # lists whose members carry the anchor's title.
        results.extend(expand_enumerations(text, results, self._usc_spec()))
        results.extend(expand_enumerations(text, results, self._cfr_spec()))
        return results

    def _usc_spec(self) -> EnumSpec:
        def groups_of(c: Citation) -> list[str] | None:
            if c.jurisdiction != "us" or c.cite_type != CitationType.STATUTE:
                return None
            return [str(c.components["section"])]

        def build(anchor, groups, raw, pos) -> Citation | None:
            title = anchor.components["title"]
            section = groups[0]
            return Citation(
                raw_text=raw,
                cite_type=CitationType.STATUTE,
                jurisdiction="us",
                normalized=f"{title} U.S.C. § {section}",
                components={"title": title, "section": section, "subsection": None},
                sources=[Source("govinfo", usc_url(title, section))],
                position=pos,
            )

        # U.S.C. sections run to four digits with an optional letter suffix
        # ("1981a"), which the dash-numbered default grammar cannot express.
        return EnumSpec(1, build, groups_of, group_re=r"\d+[a-z]?")

    def _cfr_spec(self) -> EnumSpec:
        def groups_of(c: Citation) -> list[str] | None:
            if c.jurisdiction != "us" or c.cite_type != CitationType.REGULATION:
                return None
            return [str(c.components["section"])]

        def build(anchor, groups, raw, pos) -> Citation | None:
            title = anchor.components["title"]
            section = groups[0]
            return Citation(
                raw_text=raw,
                cite_type=CitationType.REGULATION,
                jurisdiction="us",
                normalized=f"{title} C.F.R. § {section}",
                components={"title": title, "section": section, "subsection": None},
                sources=[Source("ecfr", cfr_url(title, section))],
                position=pos,
            )

        return EnumSpec(1, build, groups_of, group_re=r"\d+(?:\.\d+)*")


register(2, FederalStatuteMatcher())

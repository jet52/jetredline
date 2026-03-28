"""North Dakota-specific citation patterns: NDCC, NDAC, ND Constitution, ND Court Rules."""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.ndconst import nd_constitution_url
from jetcite.sources.ndcourts import nd_court_rule_url, nd_local_rule_url
from jetcite.sources.ndlegis import ndac_url, ndcc_chapter_url, ndcc_section_url

# ---------------------------------------------------------------------------
# NDCC Section: N.D.C.C. § 12.1-32-01
# ---------------------------------------------------------------------------
_NDCC_SECTION = re.compile(
    r'(?:(?:N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*[,.\s]{0,3}'
    r'(?:[^\s\d]{0,3}|[Ss]ection|[Ss]ec)\s{0,4})'
    r'|(?:(?:[Ss]ection|[Ss]ec\.?)\s+))'
    r'(\d{1,2})(?:\.(\d+))?'
    r'[^.\w]{1,2}(\d{1,2})(?:\.(\d+))?'
    r'[^.\w](\d{1,2})(?:\.(\d+))?'
    r'(?:\([^)]+\))?'
    r'(?:[,\s]*(?:of\s+the\s+)?'
    r'(?:North\s+Dakota\s+Century\s+Code|N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*)|\W|$)',
    re.IGNORECASE,
)

# NDCC Chapter: NDCC ch. 14-02
_NDCC_CHAPTER = re.compile(
    r'(?:(?:N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*[,.\s]{0,3}'
    r'(?:ch\.|ch|chapter)\s+)'
    r'|(?:(?<!C\.\s)(?<!\w)(?:[Cc]hapter|[Cc]h\.?)\s+))'
    r'(\d{1,2})(?:\.(\d+))?'
    r'[^.\w]{1,2}(\d{1,2})(?:\.(\d+))?',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# NDAC: N.D.A.C. § 43-02-05-01
# ---------------------------------------------------------------------------
_NDAC_SECTION = re.compile(
    r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]*[^\s\d]{0,3}\s*'
    r'(\d{1,2}(?:\.\d+)?)[^.\w]{1,2}(\d{2}(?:\.\d+)?)[^.\w]{1,2}'
    r'(\d{2}(?:\.\d+)?)[^.\w]{1,2}(\d{2}(?:\.\d+)?)',
    re.IGNORECASE,
)

_NDAC_CHAPTER = re.compile(
    r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]{0,2}'
    r'(?:Ch\.|ch\.|Ch|ch)\s*'
    r'(\d{1,2}(?:\.\d+)?)[^.\w]{1,2}(\d{2}(?:\.\d+)?)[^.\w]{1,2}(\d{2}(?:\.\d+)?)',
    re.IGNORECASE,
)

_NDAC_REVERSE = re.compile(
    r'(\d{2}(?:\.\d+)?)[^.\w]{1,2}(\d{2}(?:\.\d+)?)[^.\w]{1,2}'
    r'(\d{2}(?:\.\d+)?)[^.\w]{1,2}(\d{2}(?:\.\d+)?)'
    r'(?:(?:\([a-z\d]*\))*|\D)(?:,\s{0,3})'
    r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# ND Constitution: N.D. Const. art. I, § 20
# ---------------------------------------------------------------------------
_ND_CONST_SHORT = re.compile(
    r'N(?:orth)?[\s.]*D(?:akota)?[\s.]*Const(?:itution)?[.\s]*'
    r'(?:art\.|[Aa]rticle)\s*([IVX]+)[,\s]*(?:§|[Ss]ec(?:tion)?\.?)\s*(\d+)',
    re.IGNORECASE,
)

_ND_CONST_LONG = re.compile(
    r'(?:Article|Art\.?)\s+([IVX]+)[,\s]+(?:section|sec\.?)\s+(\d+)'
    r'(?:(?:\([a-z\d]*\))*|\D)\s+of\s+the\s+'
    r'N(?:orth)?\s*D(?:akota)?\s*Const(?:itution)?',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# ND Court Rules
# ---------------------------------------------------------------------------

# N.D.R.Ct. 3-part: Rule 8.3.1
_NDRCT_3 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2}))',
    re.IGNORECASE,
)

# N.D.R.Ct. 2-part: Rule 11.10
_NDRCT_2 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2}))',
    re.IGNORECASE,
)

# N.D. Sup. Ct. Admin. R. 2-part
_ADMIN_2 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
    r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
    r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2}))',
    re.IGNORECASE,
)

# N.D. Sup. Ct. Admin. R. 1-part
_ADMIN_1 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
    r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
    r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*(?:Rule\s+)?(\d{1,2})(?![.\d]))',
    re.IGNORECASE,
)

# N.D.R.Ev. (3-4 digit rule numbers)
_NDREV = re.compile(
    r'(?:(?:Rule\s+)?(\d{3,4})'
    r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[.\s]*(?:Rule\s+)?(\d{3,4}))',
    re.IGNORECASE,
)

# Procedural rules: N.D.R.Civ.P., N.D.R.Crim.P., N.D.R.App.P., N.D.R.Juv.P.
_PROC_RULES = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^.\d])[,\s]*'
    r'(?:North\s+Dakota\s+Rules?\s+of\s+(Civil|Criminal|Appellate|Juvenile)\s+Procedure'
    r'|N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*'
    r'P(?:rocedure)?[\s.]*))',
    re.IGNORECASE,
)

# Also match "N.D.R.Civ.P. Rule 12" (rule set first)
_PROC_RULES_PREFIX = re.compile(
    r'N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*'
    r'P(?:rocedure)?[.\s]*(?:Rule\s+)?(\d{1,2})',
    re.IGNORECASE,
)

# N.D.R. Prof. Conduct
_PROF_CONDUCT = re.compile(
    r'(?:(?:Rule\s+)?(\d)\.(\d+)'
    r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[.\s]*(?:Rule\s+)?(\d)\.(\d+))',
    re.IGNORECASE,
)

# N.D.R. Lawyer Discipl.
_LAWYER_DISCIPL = re.compile(
    r'(?:(?:Rule\s+)?(\d)\.(\d+)'
    r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[.\s]*(?:Rule\s+)?(\d)\.(\d+))',
    re.IGNORECASE,
)

# N.D. Code Jud. Conduct (Canon:Rule format)
_JUD_CONDUCT_CANON = re.compile(
    r'Canon\s+(\d)\s*:\s*Rule\s+(\d)\.(\d+)'
    r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
    r'N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct',
    re.IGNORECASE,
)

# N.D. Code Jud. Conduct (Rule X.Y format)
_JUD_CONDUCT_RULE = re.compile(
    r'N[\s.]*D[\s.]*Code[\s.]*Jud(?:icial)?[\s.]*Conduct[.\s]*'
    r'(?:Rule\s+)?(\d)\.(\d+)',
    re.IGNORECASE,
)

# N.D.R. Juv. P. decimal
_JUV_DECIMAL = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|\D)[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Juv(?:enile)?[\s.]*P(?:rocedure)?[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Juv(?:enile)?[\s.]*P(?:rocedure)?[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2}))',
    re.IGNORECASE,
)

# N.D.R. Continuing Legal Ed.
_CLE = re.compile(
    r'(?:N[\s.]*D[\s.]*R[\s.]*Continuing[\s.]*Legal[\s.]*Ed[.\s]*(?:Rule\s+)?(\d+)'
    r'|(?:Rule\s+)?(\d+)[,\s]*N[\s.]*D[\s.]*R[\s.]*Continuing[\s.]*Legal[\s.]*Ed)',
    re.IGNORECASE,
)

# N.D. Admission to Practice R. decimal
_ADMISSION_DEC = re.compile(
    r'(?:N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R[.\s]*(?:Rule\s+)?(\d+)\.(\d+)'
    r'|(?:Rule\s+)?(\d+)\.(\d+)[,\s]*N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R)',
    re.IGNORECASE,
)

# N.D. Admission to Practice R. simple
_ADMISSION = re.compile(
    r'(?:N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R[.\s]*(?:Rule\s+)?(\d+)(?![.\d])'
    r'|(?:Rule\s+)?(\d+)(?![.\d])[,\s]*N[\s.]*D[\s.]*Admission[\s.]*to[\s.]*Practice[\s.]*R)',
    re.IGNORECASE,
)

# N.D. Stds. Imposing Lawyer Sanctions
_SANCTIONS = re.compile(
    r'(?:N[\s.]*D[\s.]*Stds?[\s.]*Imposing[\s.]*Lawyer[\s.]*Sanctions[.\s]*(\d+)'
    r'|(\d+)[,\s]*N[\s.]*D[\s.]*Stds?[\s.]*Imposing[\s.]*Lawyer[\s.]*Sanctions)',
    re.IGNORECASE,
)

# Local Rules
_LOCAL = re.compile(r'Local[\s.]*Rule[\s.]*(\d{1,4}(?:-\d+)?)', re.IGNORECASE)

# N.D.R. Proc. R.
_PROC_R = re.compile(
    r'(?:N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R[.\s]*(?:Rule\s+)?(\d+)'
    r'|(?:Rule\s+)?(\d+)[,\s]*N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R)',
    re.IGNORECASE,
)

# N.D.R. Local Ct. P.R.
_LOCAL_CT = re.compile(
    r'(?:N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R[.\s]*(?:Rule\s+)?(\d+)'
    r'|(?:Rule\s+)?(\d+)[,\s]*N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R)',
    re.IGNORECASE,
)

# N.D.R. Jud. Conduct Commission decimal
_JUD_COMM_DEC = re.compile(
    r'(?:N[\s.]*D[\s.]*R[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*Comm(?:ission)?[.\s]*'
    r'(?:Rule\s+)?(\d+)\.(\d+)'
    r'|(?:Rule\s+)?(\d+)\.(\d+)[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*Comm(?:ission)?)',
    re.IGNORECASE,
)

# N.D.R. Jud. Conduct Commission simple
_JUD_COMM = re.compile(
    r'(?:N[\s.]*D[\s.]*R[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*Comm(?:ission)?[.\s]*'
    r'(?:Rule\s+)?(\d+)(?![.\d])'
    r'|(?:Rule\s+)?(\d+)(?![.\d])[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Jud(?:icial)?[\s.]*Conduct[\s.]*Comm(?:ission)?)',
    re.IGNORECASE,
)

# Student Practice Rules (Roman numeral)
_STUDENT = re.compile(
    r'(?:Limited\s+Practice\s+of\s+Law\s+by\s+Law\s+Students|'
    r'N[\s.]*D[\s.]*Student[\s.]*Practice[\s.]*R(?:ule)?)'
    r'[.\s]*(?:§\s*)?([IVX]+)',
    re.IGNORECASE,
)

_PROC_MAP = {
    "civil": "ndrcivp", "civ": "ndrcivp",
    "criminal": "ndrcrimp", "crim": "ndrcrimp",
    "appellate": "ndrapp", "app": "ndrapp",
    "juvenile": "ndrjuvp", "juv": "ndrjuvp",
}


def _first_groups(m, *pairs):
    """From alternating regex groups, return the first non-None pair."""
    for pair in pairs:
        values = [m.group(i) for i in pair]
        if values[0] is not None:
            return values
    return [None] * len(pairs[0])


class NDMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results = []
        self._match_ndcc(text, results)
        self._match_ndac(text, results)
        self._match_nd_const(text, results)
        self._match_nd_rules(text, results)
        # Deduplicate: when two matches start at the same position,
        # keep the one with the longer raw_text (more specific match).
        by_pos: dict[int, Citation] = {}
        for cite in results:
            if cite.position not in by_pos or len(cite.raw_text) > len(by_pos[cite.position].raw_text):
                by_pos[cite.position] = cite
        return list(by_pos.values())

    def _match_ndcc(self, text: str, results: list[Citation]):
        for m in _NDCC_SECTION.finditer(text):
            title, title_dec = m.group(1), m.group(2)
            chapter, chapter_dec = m.group(3), m.group(4)
            section, section_dec = m.group(5), m.group(6)

            title_full = f"{title}.{title_dec}" if title_dec else title
            chapter_full = f"{chapter}.{chapter_dec}" if chapter_dec else chapter
            section_full = f"{section}.{section_dec}" if section_dec else section
            normalized = f"N.D.C.C. § {title_full}-{chapter_full}-{section_full}"

            url = ndcc_section_url(title, chapter, section,
                                   title_dec, chapter_dec, section_dec)
            sources = [Source("ndlegis", url)] if url else []

            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.STATUTE,
                jurisdiction="nd",
                normalized=normalized,
                components={
                    "title": title, "title_dec": title_dec,
                    "chapter": chapter, "chapter_dec": chapter_dec,
                    "section": section, "section_dec": section_dec,
                },
                sources=sources,
                position=m.start(),
            ))

        for m in _NDCC_CHAPTER.finditer(text):
            title, title_dec = m.group(1), m.group(2)
            chapter, chapter_dec = m.group(3), m.group(4)

            title_full = f"{title}.{title_dec}" if title_dec else title
            chapter_full = f"{chapter}.{chapter_dec}" if chapter_dec else chapter
            normalized = f"N.D.C.C. ch. {title_full}-{chapter_full}"

            url = ndcc_chapter_url(title, chapter, title_dec, chapter_dec)
            sources = [Source("ndlegis", url)] if url else []

            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.STATUTE,
                jurisdiction="nd",
                normalized=normalized,
                components={
                    "title": title, "title_dec": title_dec,
                    "chapter": chapter, "chapter_dec": chapter_dec,
                },
                sources=sources,
                position=m.start(),
            ))

    def _match_ndac(self, text: str, results: list[Citation]):
        for m in _NDAC_SECTION.finditer(text):
            p1, p2, p3, p4 = m.group(1), m.group(2), m.group(3), m.group(4)
            normalized = f"N.D.A.C. § {p1}-{p2}-{p3}-{p4}"
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.REGULATION,
                jurisdiction="nd",
                normalized=normalized,
                components={"part1": p1, "part2": p2, "part3": p3, "part4": p4},
                sources=[Source("ndlegis", ndac_url(p1, p2, p3))],
                position=m.start(),
            ))

        for m in _NDAC_CHAPTER.finditer(text):
            p1, p2, p3 = m.group(1), m.group(2), m.group(3)
            normalized = f"N.D.A.C. ch. {p1}-{p2}-{p3}"
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.REGULATION,
                jurisdiction="nd",
                normalized=normalized,
                components={"part1": p1, "part2": p2, "part3": p3},
                sources=[Source("ndlegis", ndac_url(p1, p2, p3))],
                position=m.start(),
            ))

        for m in _NDAC_REVERSE.finditer(text):
            p1, p2, p3 = m.group(1), m.group(2), m.group(3)
            normalized = f"N.D.A.C. § {p1}-{p2}-{p3}-{m.group(4)}"
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.REGULATION,
                jurisdiction="nd",
                normalized=normalized,
                components={"part1": p1, "part2": p2, "part3": p3, "part4": m.group(4)},
                sources=[Source("ndlegis", ndac_url(p1, p2, p3))],
                position=m.start(),
            ))

    def _match_nd_const(self, text: str, results: list[Citation]):
        for m in _ND_CONST_SHORT.finditer(text):
            article, section = m.group(1).upper(), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="nd",
                normalized=f"N.D. Const. art. {article}, § {section}",
                components={"article": article, "section": section},
                sources=[Source("ndconst", nd_constitution_url(article, section))],
                position=m.start(),
            ))

        for m in _ND_CONST_LONG.finditer(text):
            article, section = m.group(1).upper(), m.group(2)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="nd",
                normalized=f"N.D. Const. art. {article}, § {section}",
                components={"article": article, "section": section},
                sources=[Source("ndconst", nd_constitution_url(article, section))],
                position=m.start(),
            ))

    def _match_nd_rules(self, text: str, results: list[Citation]):
        # N.D.R.Ct. 3-part
        for m in _NDRCT_3.finditer(text):
            parts = _first_groups(m, (1, 2, 3), (4, 5, 6))
            if parts[0]:
                results.append(self._rule_cite(m, "ndrct", "N.D.R.Ct.", parts))

        # N.D.R.Ct. 2-part
        for m in _NDRCT_2.finditer(text):
            parts = _first_groups(m, (1, 2), (3, 4))
            if parts[0]:
                results.append(self._rule_cite(m, "ndrct", "N.D.R.Ct.", parts))

        # Admin rules 2-part
        for m in _ADMIN_2.finditer(text):
            parts = _first_groups(m, (1, 2), (3, 4))
            if parts[0]:
                results.append(self._rule_cite(
                    m, "ndsupctadminr", "N.D. Sup. Ct. Admin. R.", parts))

        # Admin rules 1-part
        for m in _ADMIN_1.finditer(text):
            part = m.group(1) or m.group(2)
            if part:
                results.append(self._rule_cite(
                    m, "ndsupctadminr", "N.D. Sup. Ct. Admin. R.", [part]))

        # Evidence rules
        for m in _NDREV.finditer(text):
            rule = m.group(1) or m.group(2)
            if rule:
                results.append(self._rule_cite(m, "ndrev", "N.D.R.Ev.", [rule]))

        # Procedural rules (suffix pattern)
        for m in _PROC_RULES.finditer(text):
            rule_num = m.group(1)
            proc_type = (m.group(2) or m.group(3)).lower()
            rule_set = _PROC_MAP.get(proc_type)
            if rule_set and rule_num:
                display = {
                    "ndrcivp": "N.D.R.Civ.P.",
                    "ndrcrimp": "N.D.R.Crim.P.",
                    "ndrapp": "N.D.R.App.P.",
                    "ndrjuvp": "N.D.R.Juv.P.",
                }.get(rule_set, rule_set)
                results.append(self._rule_cite(m, rule_set, display, [rule_num]))

        # Procedural rules (prefix pattern)
        for m in _PROC_RULES_PREFIX.finditer(text):
            proc_type = m.group(1).lower()
            rule_num = m.group(2)
            rule_set = _PROC_MAP.get(proc_type)
            if rule_set and rule_num:
                display = {
                    "ndrcivp": "N.D.R.Civ.P.",
                    "ndrcrimp": "N.D.R.Crim.P.",
                    "ndrapp": "N.D.R.App.P.",
                    "ndrjuvp": "N.D.R.Juv.P.",
                }.get(rule_set, rule_set)
                results.append(self._rule_cite(m, rule_set, display, [rule_num]))

        # Professional Conduct
        for m in _PROF_CONDUCT.finditer(text):
            parts = _first_groups(m, (1, 2), (3, 4))
            if parts[0]:
                results.append(self._rule_cite(
                    m, "ndrprofconduct", "N.D.R. Prof. Conduct", parts))

        # Lawyer Discipline
        for m in _LAWYER_DISCIPL.finditer(text):
            parts = _first_groups(m, (1, 2), (3, 4))
            if parts[0]:
                results.append(self._rule_cite(
                    m, "ndrlawyerdiscipl", "N.D.R. Lawyer Discipl.", parts))

        # Judicial Conduct (Canon:Rule)
        for m in _JUD_CONDUCT_CANON.finditer(text):
            canon = m.group(1)
            results.append(self._rule_cite(
                m, "ndcodejudconduct", "N.D. Code Jud. Conduct", [f"canon-{canon}"]))

        # Judicial Conduct (Rule X.Y)
        for m in _JUD_CONDUCT_RULE.finditer(text):
            parts = [m.group(1), m.group(2)]
            results.append(self._rule_cite(
                m, "ndcodejudconduct", "N.D. Code Jud. Conduct", parts))

        # Juvenile Procedure decimal
        for m in _JUV_DECIMAL.finditer(text):
            parts = _first_groups(m, (1, 2), (3, 4))
            if parts[0]:
                results.append(self._rule_cite(m, "ndrjuvp", "N.D.R.Juv.P.", parts))

        # Continuing Legal Ed.
        for m in _CLE.finditer(text):
            rule = m.group(1) or m.group(2)
            if rule:
                results.append(self._rule_cite(
                    m, "ndrcontinuinglegaled", "N.D.R. Continuing Legal Ed.", [rule]))

        # Admission to Practice (decimal)
        for m in _ADMISSION_DEC.finditer(text):
            parts = _first_groups(m, (1, 2), (3, 4))
            if parts[0]:
                results.append(self._rule_cite(
                    m, "admissiontopracticer", "N.D. Admission to Practice R.", parts))

        # Admission to Practice (simple)
        for m in _ADMISSION.finditer(text):
            rule = m.group(1) or m.group(2)
            if rule:
                results.append(self._rule_cite(
                    m, "admissiontopracticer", "N.D. Admission to Practice R.", [rule]))

        # Lawyer Sanctions
        for m in _SANCTIONS.finditer(text):
            rule = m.group(1) or m.group(2)
            if rule:
                results.append(self._rule_cite(
                    m, "ndstdsimposinglawyersanctions",
                    "N.D. Stds. Imposing Lawyer Sanctions",
                    [rule, "0"]))

        # Local Rules
        for m in _LOCAL.finditer(text):
            rule = m.group(1)
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.COURT_RULE,
                jurisdiction="nd",
                normalized=f"Local Rule {rule}",
                components={"rule_set": "local", "rule": rule},
                sources=[Source("ndcourts", nd_local_rule_url(rule))],
                position=m.start(),
            ))

        # N.D.R. Proc. R.
        for m in _PROC_R.finditer(text):
            rule = m.group(1) or m.group(2)
            if rule:
                results.append(self._rule_cite(
                    m, "ndrprocr", "N.D.R. Proc. R.", [rule]))

        # N.D.R. Local Ct. P.R.
        for m in _LOCAL_CT.finditer(text):
            rule = m.group(1) or m.group(2)
            if rule:
                results.append(self._rule_cite(
                    m, "ndrlocalctpr", "N.D.R. Local Ct. P.R.", [rule]))

        # Judicial Conduct Commission (decimal)
        for m in _JUD_COMM_DEC.finditer(text):
            parts = _first_groups(m, (1, 2), (3, 4))
            if parts[0]:
                results.append(self._rule_cite(
                    m, "rjudconductcomm", "N.D.R. Jud. Conduct Commission", parts))

        # Judicial Conduct Commission (simple)
        for m in _JUD_COMM.finditer(text):
            rule = m.group(1) or m.group(2)
            if rule:
                results.append(self._rule_cite(
                    m, "rjudconductcomm", "N.D.R. Jud. Conduct Commission", [rule]))

        # Student Practice Rules
        for m in _STUDENT.finditer(text):
            roman = m.group(1).upper()
            results.append(self._rule_cite(
                m, "rltdpracticeoflawbylawstudents",
                "N.D. Student Practice R.", [roman]))

    def _rule_cite(self, m, rule_set: str, display: str,
                   parts: list[str]) -> Citation:
        parts_str = ".".join(parts)
        return Citation(
            raw_text=m.group(0),
            cite_type=CitationType.COURT_RULE,
            jurisdiction="nd",
            normalized=f"{display} {parts_str}",
            components={"rule_set": rule_set, "parts": parts},
            sources=[Source("ndcourts", nd_court_rule_url(rule_set, parts))],
            position=m.start(),
        )


register(4, NDMatcher())

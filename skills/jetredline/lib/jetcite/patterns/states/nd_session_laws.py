"""North Dakota Session Laws: reporter-style citation forms.

    2019 N.D. Sess. Laws ch. 404, § 2      the form the ND Supreme Court prints
    1975 N.D.Sess.Laws ch. 615             (spacing varies with the era)
    1987 N.D. Laws ch. 194
    N.D. Sess. Laws 1937, ch. 159
    S.L. 2019, ch. 404, § 4                the Century Code's own form
    S.L. 2021 (sp.), ch. 553               a special session, as the Code writes it
    1937 S.L., ch. 249
    S.L.N.D. 1945, ch. 106  /  ch. 176, SLND 1947

Every form names North Dakota, or is the Century Code's `S.L.`, so none needs
a jurisdiction guard. The PROSE forms ("chapter 67 of the Session Laws of
1897", "Laws of 1907, chapter 58") name no state — in a North Dakota opinion
they are often Minnesota's, Dakota Territory's or Congress's — and are
deliberately not matched here.

Normalized form: ``2019 N.D. Sess. Laws ch. 404`` (Bluebook; the act section,
when cited, goes in ``pinpoint`` as ``§ 2`` and in ``components``). A special
session cited as such normalizes to ``2021 N.D. Sess. Laws Spec. Sess. ch. 553``
only when the source said "Spec. Sess."; the Code's ``(sp.)`` is recorded in
``components["special"]`` and left out of the normalized string, because from
2001 on a special session continues the regular session's chapter numbers and
the year and chapter identify the act.
"""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher

_YEAR = r'(1[89]\d\d|20\d\d)'
# The chapter number must not run on into a dash: "Chapter 40–45, N.D.R.C. 1943" is a
# chapter of the Revised Code, not chapter 40 of a session.
_DASH = '‐‑‒–—―−-'
_CH = rf'[Cc]h(?:s?\.|apters?)\s*(\d{{1,4}})(?![\d{_DASH}])'
# an act-section pinpoint: ", § 2" / ", sec. 2" / ", §§ 2, 3" (first only)
_SEC = r'(?:,?\s*(?:§§?|[Ss]ec(?:s?\.|tions?))\s*(\d{1,3})(?![\d-]))?'
_ND = r'N\.\s?D\.\s?'

# 2019 N.D. Sess. Laws ch. 404  |  1987 N.D. Laws ch. 194  |  1919 N.D. Sess. Laws Spec. Sess. ch. 4
_YEAR_FIRST = re.compile(
    rf'(?<![\d-]){_YEAR}\s+{_ND}(?:Sess\.\s?)?Laws,?\s*(Spec\.\s?Sess\.,?\s*)?{_CH}{_SEC}')
# N.D. Sess. Laws 1937, ch. 159
_YEAR_AFTER = re.compile(rf'(?<![\w.]){_ND}(?:Sess\.\s?)?Laws,?\s+{_YEAR},?\s*{_CH}{_SEC}')
# S.L. 2019, ch. 404  |  S.L.1905, Ch. 34  |  S.L. 2021 (sp.), ch. 553
_CODE = re.compile(rf'(?<![\w.])S\.\s?L\.\s?{_YEAR}\s*(\(sp\.\))?,?\s*{_CH}{_SEC}')
# 1937 S.L., ch. 249
_CODE_YEAR_FIRST = re.compile(rf'(?<![\d-]){_YEAR}\s+S\.\s?L\.,?\s*{_CH}{_SEC}')
# S.L.N.D. 1945, ch. 106  |  SLND 1945, ch. 106
_SLND = re.compile(rf'(?<![\w.])(?:S\.\s?L\.\s?N\.\s?D\.|SLND),?\s*{_YEAR},?\s*{_CH}{_SEC}')
# ch. 176, S.L.N.D. 1947  |  Chapter 176, SLND 1947  |  ch. 249, S.L. 1937
_CH_FIRST = re.compile(
    rf'(?<![\w.]){_CH},?\s*(?:of\s+(?:the\s+)?)?(?:S\.\s?L\.\s?N\.\s?D\.|SLND|S\.\s?L\.),?\s*{_YEAR}(?![\d-])')

# ndlegis serves one full-book PDF per regular session from the 55th Assembly (1997)
_FIRST_FULL_BOOK = 1997


def session_laws_url(year: int, special: bool = False) -> str | None:
    """The ndlegis full book for a regular session, 1997 on; None otherwise.

    A special session's volume sits under its own path and (2026) may be one
    of two, so no URL is guessed for it."""
    if special or year < _FIRST_FULL_BOOK or year % 2 == 0:
        return None
    assembly = 55 + (year - _FIRST_FULL_BOOK) // 2
    return f"https://ndlegis.gov/assembly/{assembly}-{year}/session-laws/sl{year}.pdf"


class NDSessionLawMatcher(BaseMatcher):
    """North Dakota Session Laws, reporter-style forms only."""

    def find_all(self, text: str) -> list[Citation]:
        # Every form's matches, then left to right, first come first kept. Order
        # matters in a run: "Chapter 277 S.L.1935, Chapter 280 S.L.1935" is two
        # chapter-first cites, and read year-first from the middle it pairs 1935
        # with chapter 280 by luck and, one step on, 1937 with a chapter of 1939.
        # Whichever form opens the run governs it.
        cands = []
        for m in _YEAR_FIRST.finditer(text):
            cands.append((m, m.group(1), m.group(3), m.group(4), "spec" if m.group(2) else None))
        for m in _YEAR_AFTER.finditer(text):
            cands.append((m, m.group(1), m.group(2), m.group(3), None))
        for m in _SLND.finditer(text):
            cands.append((m, m.group(1), m.group(2), m.group(3), None))
        for m in _CODE.finditer(text):
            cands.append((m, m.group(1), m.group(3), m.group(4), "sp" if m.group(2) else None))
        for m in _CODE_YEAR_FIRST.finditer(text):
            cands.append((m, m.group(1), m.group(2), m.group(3), None))
        for m in _CH_FIRST.finditer(text):
            cands.append((m, m.group(2), m.group(1), None, None))
        cands.sort(key=lambda c: (c[0].start(), -(c[0].end() - c[0].start())))

        out: list[Citation] = []
        last_end = -1
        for m, year, chapter, section, special_form in cands:
            if m.start() < last_end:
                continue
            last_end = m.end()
            y, ch = int(year), int(chapter)
            spec_sess = special_form == "spec"
            url = session_laws_url(y, special=bool(special_form))
            out.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.SESSION_LAW,
                jurisdiction="nd",
                normalized=f"{y} N.D. Sess. Laws {'Spec. Sess. ' if spec_sess else ''}ch. {ch}",
                components={"year": str(y), "chapter": str(ch), "section": section,
                            "special": bool(special_form)},
                pinpoint=f"§ {section}" if section else None,
                sources=[Source("ndlegis", url)] if url else [],
                position=m.start(),
            ))
        return out


register(4, NDSessionLawMatcher())

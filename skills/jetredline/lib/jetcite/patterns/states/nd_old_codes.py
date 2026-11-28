"""North Dakota and Dakota Territory codes before the Century Code.

    Section 49-0604, NDRC 1943        the Revised Code of 1943 (title-chapter+section)
    Sec. 34-0203, N.D.R.C. 1943  |  R.C.N.D. 1943  |  RCND 1943
    section 5841, C. L. 1913          the Compiled Laws of 1913
    section 8102, Comp. Laws Supp. 1925   the 1925 Supplement to them
    section 4018, R. C. 1905          the Revised Codes of 1905, 1899 and 1895
    section 5630, Rev. Codes 1899  |  section 1988 of the Revised Codes of 1899
    Sections 1640, 1643, Comp. Laws 1887   the Compiled Laws of Dakota Territory
    Rev. Codes 1899, § 5274  |  R.C. 1895, §§ 8178, 8179, 8269     (code first)

Normalized to the North Dakota Supreme Court's traditional abbreviations:

    N.D.R.C. 1943 § 49-0604       N.D.C.L. 1913 § 5841
    N.D.C.L. Supp. 1925 § 6877a1  N.D.R.C. 1905 § 4018  (1899, 1895 alike)
    Dakota C.L. 1887 § 1640

Each code is named by its year, and only the years North Dakota (or the
Territory) published a code are read, which is most of what keeps another
state's code out: Montana's Revised Codes are 1907, 1921 and 1935, Idaho's
1908, South Dakota's 1903 and 1919. South Dakota did publish Compiled Laws in
1913, so a form that does not name North Dakota ("Comp. Laws 1913", "Rev.
Codes 1905") is refused when another jurisdiction is named ON the code:
"S. D. Comp. Laws 1913", "the Montana Rev. Codes 1895", "Comp. Laws 1913 of
South Dakota". A state named elsewhere in the sentence does not count. The
session-law guard (nearest jurisdiction in the sentence) was tried here first
and was wrong at every site read: these opinions say "Kansas has so held under
a statute like section 9374, Rev. Codes 1905", and the section is North
Dakota's. The Compiled Laws of 1887 are never refused: they are the
Territory's, and South Dakota's courts cite the same book.

A list ("sections 1640, 1643", "§§ 8178, 8179 and 8269", "sections 2966 to
2971") yields one citation per number printed; the numbers between the ends of
a range are not supplied. A supplement to the 1943 code ("1957 Supp. NDRC
1943") keeps the 1943 normalized form and records the supplement's year in
``components["supplement"]``: the numbering is the 1943 code's.

A chapter of the 1943 code ("Chapter 32-15, NDRC 1943") normalizes to
``N.D.R.C. 1943 ch. 32-15``, with ``components["chapter"]`` and no
``"section"``. Its number is title-dash-chapter, the shape the Century Code
kept, so a Century Code chapter printed under the old label (as some opinions
of the 1960s and 1970s do) is read as a 1943 chapter: the text alone does not
tell them apart.

Not read here: the separately numbered codes of 1877 (Civil Code, Code of
Civil Procedure, ...), sub-code cites ("section 46, Civil Code 1887"), and
chapters of the codes before 1943, whose numbers restart in each sub-code.
"""

import re

from jetcite.models import Citation, CitationType
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.patterns.states.nd_session_laws import _AFTER_FOREIGN, _STATES

_DASH = '‐‑‒–—―−-'
_B = r'(?<![\w.])'                      # a code name does not continue another token
_OF_ND = r'(?:,?\s+(?:of\s+)?(?:the\s+State\s+of\s+)?(?:North\s+Dakota|N\.\s?D\.))?'
_OF = r',?\s*(?:(?:of|for)\s+)?(?:the\s+year\s+)?'

# --- code names; each ends at its year -----------------------------------
# NDRC | N.D.R.C. | N. D. R. C. | RCND | R.C.N.D.  (the State is named)
_RC_ND = r'(?:N\.?\s?D\.?\s?R\.?\s?C\.?|R\.?\s?C\.?\s?(?:of\s+)?N\.?\s?D\.?)'
# R. C. | R.C. | Rev. Codes | Revised Code[s] | N.D. Rev. Code   (State optional)
_RC_BARE = r'(?:R\.\s?C\.|(?:N\.\s?D\.\s?|North\s+Dakota\s+)?Rev(?:ised|\.)\s+Codes?)'
_CL_ND = r'(?:N\.?\s?D\.?\s?C\.?\s?L\.?|C\.?\s?L\.?\s?(?:of\s+)?N\.?\s?D\.?)'
_CL_BARE = r'(?:C\.\s?L\.|(?:N\.\s?D\.\s?|North\s+Dakota\s+|Dak(?:ota|\.)\s+)?Comp(?:iled|\.)\s?Laws)'
_SUPP = r'Supp(?:lement|l?\.)'
_RC = rf'(?:{_RC_ND}|{_RC_BARE})'
_CL = rf'(?:{_CL_ND}|{_CL_BARE})'
_CL_PLAIN = rf'(?:{_CL_ND}|{_CL_BARE})'
_RC_PLAIN = rf'(?:{_RC_ND}|{_RC_BARE})'

_CODE = (
    rf'{_B}(?P<code>'
    # 1925 Supplement [to the Compiled Laws of 1913] | Supp. 1925 | Comp. Laws Supp. 1925
    # Supplement to the Compiled Laws of 1913 (no other supplement to them was published)
    rf'(?P<supp>(?:1925\s+{_SUPP}(?:\s+to\s+(?:the\s+)?{_CL_PLAIN}{_OF_ND}{_OF}(?:1913)?)?'
    rf'|(?:{_CL_PLAIN}{_OF_ND}{_OF}(?:1913,?\s*)?)?{_SUPP},?\s*(?:(?:of|for)\s+)?1925'
    rf'|{_SUPP}\s+to\s+(?:the\s+)?{_CL_PLAIN}{_OF_ND}{_OF}1913)(?!\d))'
    # 1957 Supp. [to] NDRC 1943 | NDRC 1943, 1957 Supp. | NDRC 1953 Supp.
    rf'|(?P<s43a>19[4-5]\d)\s+{_SUPP},?\s*(?:to\s+(?:the\s+)?)?{_RC_PLAIN}{_OF_ND}{_OF}1943(?!\d)'
    rf'|{_RC_PLAIN}{_OF_ND}{_OF}(?:1943,?\s*)?(?P<s43b>19[4-5]\d)\s+{_SUPP}'
    rf'|{_RC}{_OF_ND}{_OF}(?P<rc_year>1895|1899|1905|1943)(?!\d)'
    rf'|{_CL}{_OF_ND}{_OF}(?P<cl_year>1887|1913)(?!\d)'
    rf')'
)

# --- section numbers ------------------------------------------------------
# 1943: title, dash, chapter+section ("49-0604"); a supplement adds a digit ("57-02011")
_N43 = rf'\d{{1,2}}[{_DASH}]\d{{4,5}}(?![\d{_DASH}])'
# the consecutively numbered codes: "5841", and the 1925 Supplement's "6877a1"
_NINT = (rf'(?:\d{{3,5}}|\d{{1,2}}(?![{_DASH}]\d{{4,5}}(?!\d)))'
         rf'(?:[a-z]\d{{0,3}})?(?![\dA-Za-z])(?!\s+Supp)')
_NUM = rf'(?:{_N43}|{_NINT})'
_SUBDIV = r'(?:\s?\(\w{1,3}\))*'
_JOIN = rf'(?:\s*,\s*(?:and\s+|to\s+)?|\s+and\s+|\s+to\s+|\s*[{_DASH}]\s*|\s+or\s+)'
# a list is all of one shape: "15-5116, 1925 Supp." does not run on into the year
_LIST = (rf'(?P<list>{_N43}{_SUBDIV}(?:{_JOIN}{_N43}{_SUBDIV}){{0,11}}'
         rf'|{_NINT}{_SUBDIV}(?:{_JOIN}{_NINT}{_SUBDIV}){{0,11}})')
# "s 7655" and "ss 7655" are how one reporter lineage prints the section sign
_SEC = r'(?:§§?\s*|[Ss]ec(?:s?\.|tions?)\s*|(?<![A-Za-z])ss?\.?\s+(?=\d))'
# between the numbers and the code: "et seq.", a subdivision, a star page
_TAIL = (r'(?:,?\s*et\s+seq\.?)?(?:,?\s*(?:both\s+)?inclusive)?\)?'
         r'(?:,?\s*(?:[Ss]ub-?\s?sec(?:tions?|s?\.)|[Ss]ubd(?:ivisions?|ivs?\.?|s?\.)|[Pp]ars?\.|[Pp]aragraphs?|[Ss]ection)'
         r'\s*\d{1,2}(?:\s*(?:,|and)\s*\d{1,2}){0,3})?'
         r'\s*,?\s*(?:\[\*{1,2}\d+\]\s*)?')

# section 5841, C. L. 1913 | section 1988 of the Revised Codes of 1899 | Sec. 34-0203, 1949 Supp. NDRC 1943
_TRAILING = re.compile(
    rf'{_SEC}{_LIST}{_TAIL}(?:of\s+(?:(?:the|our)\s+Code\s*)?)?[(\[]?(?:the\s+)?{_CODE}')
# Rev. Codes 1899, § 5274 | R.C. 1895, §§ 8178, 8179, 8269 | Compiled Laws of 1887 (sections 1640-1643)
_LEADING = re.compile(rf'{_CODE}\s*,?\s*\(?\s*{_SEC}{_LIST}')
# NDRC 1943, 65-0904 | R.C.1943, 61-2115: the 1943 number's shape is its own sign
_L43 = rf'(?P<list>{_N43}{_SUBDIV}(?:{_JOIN}{_N43}{_SUBDIV}){{0,11}})'
_LEADING_BARE = re.compile(rf'{_CODE}\s*,?\s*{_L43}')
# 28-0741 N.D.R.C. 1943 | 14-0902, Revised Code 1943 | 65-0103, NDRC 1953 Supp.
_TRAILING_BARE = re.compile(rf'(?<![\w.§{_DASH}]){_L43}{_TAIL}{_CODE}')
# C.L.1913, § 157 (1925 Supp.): the section as the Supplement carries it
_SUPP_AFTER = re.compile(r'\s*\(1925\s+Supp(?:lement|l?\.)\)')
# Chapter 32-15, NDRC 1943 | Chapters 24-01 and 24-07, NDRC 1943 | Chapter 40-05 of the NDRC 1943
_C43 = rf'\d{{1,2}}[{_DASH}]\d{{2}}(?![\d{_DASH}])(?!\.\d)'
_CLIST = rf'(?P<list>{_C43}(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s+through\s+|\s+to\s+){_C43}){{0,7}})'
_CHAP = r'(?<![A-Za-z])[Cc]h(?:ap(?:ter)?s?|s)?\.?\s*'
_CH_TRAILING = re.compile(rf'{_CHAP}{_CLIST}\s*,?\s*(?:\[\*{{1,2}}\d+\]\s*)?(?:of\s+)?[(\[]?(?:the\s+)?{_CODE}')
# NDRC 1943, Chapter 15-51
_CH_LEADING = re.compile(rf'{_CODE}\s*,?\s*\(?\s*{_CHAP}{_CLIST}')
_C43_RE = re.compile(_C43)
_NAMES_ND = re.compile(r'N\.?\s?D\.?|North\s+Dakota')
_FOREIGN_BEFORE = re.compile(rf'(?<![A-Za-z.])(?:{_STATES}|U\.\s?S\.|United\s+States)(?:\'s)?,?\s+(?:the\s+)?$')

_NUM_RE = re.compile(_NUM)
_ANY_YEAR = re.compile(r'1887|1895|1899|1905|1913|1925|19[45]\d')
_IS43 = re.compile(rf'\d{{1,2}}[{_DASH}]\d{{4,5}}$')


def _code_of(m: re.Match) -> tuple[str, str, str | None]:
    """(normalized prefix, code key, supplement year) for a match."""
    g = m.groupdict()
    if g["supp"]:
        return "N.D.C.L. Supp. 1925", "ndcl1925supp", "1925"
    if g["s43a"] or g["s43b"]:
        return "N.D.R.C. 1943", "ndrc1943", g["s43a"] or g["s43b"]
    if g["rc_year"]:
        return f"N.D.R.C. {g['rc_year']}", f"ndrc{g['rc_year']}", None
    if g["cl_year"] == "1887":
        return "Dakota C.L. 1887", "dakcl1887", None
    return "N.D.C.L. 1913", "ndcl1913", None


def _foreign(text: str, m: re.Match, key: str) -> bool:
    """True when another jurisdiction is named on the code itself."""
    if key == "dakcl1887" or _NAMES_ND.search(m.group("code")):
        return False
    if _AFTER_FOREIGN.match(text[m.end("code"):m.end("code") + 40]):
        return True
    return bool(_FOREIGN_BEFORE.search(text[max(0, m.start("code") - 30):m.start("code")]))


def _fits(m: re.Match) -> bool:
    """The numbers have the shape of the code's own: a 1943 section is
    title-dash-number and no other code's is."""
    return bool(_IS43.match(_NUM_RE.match(m.group("list")).group(0))) == (_code_of(m)[1] == "ndrc1943")


def chapter_spans_1943(text: str) -> list[tuple[int, int]]:
    """Spans of the chapter cites this module reads as the 1943 code's.

    The Century Code matcher asks before it reads a bare "Chapter 27-16" as its
    own: followed by "NDRC 1943" the chapter is the old code's, and a Century
    Code chapter beside it would be a second authority the text never cites.
    """
    return [(m.start(), m.end())
            for pat in (_CH_TRAILING, _CH_LEADING) for m in pat.finditer(text)
            if _code_of(m)[1] == "ndrc1943"]


class NDOldCodeMatcher(BaseMatcher):
    """Sections of the North Dakota and Dakota Territory codes of 1887-1943."""

    def find_all(self, text: str) -> list[Citation]:
        if not _ANY_YEAR.search(text):          # every form ends at a code's year
            return []
        trailing = list(_TRAILING.finditer(text))
        leading = list(_LEADING.finditer(text))
        # "chapter 147, section 6 (Comp. Laws Supp. 1925, § 5192a6)": the code's
        # own section follows it, so the number before it is something else's
        # (an act section). Not so in a run of sections each ahead of its code
        # ("§ 6458, Comp. Laws 1913, § 5891, Rev. Codes 1905"), where the
        # section after the code opens the next citation.
        starts = sorted(m.start() for m in trailing if _fits(m))
        code_first = {m.start("code") for m in leading
                      if not any(m.end("code") <= s <= m.start("list") for s in starts)}
        trailing = [m for m in trailing if m.start("code") not in code_first]
        cands = ([(m, 0) for m in trailing] + [(m, 1) for m in leading]
                 + [(m, 2) for m in _LEADING_BARE.finditer(text)]
                 + [(m, 3) for m in _TRAILING_BARE.finditer(text)])
        # Leftmost first, so whichever form opens a run governs it: in
        # "§ 6458, Comp. Laws 1913, § 5891, Rev. Codes 1905" the middle section
        # belongs to the code after it, and in "Comp. Laws 1913, § 6458, Rev.
        # Codes 1905, § 5891" to the code before it.
        cands.sort(key=lambda c: (c[0].start(), c[1]))
        out: list[Citation] = []
        last_end = -1
        chapters = sorted(list(_CH_TRAILING.finditer(text)) + list(_CH_LEADING.finditer(text)),
                          key=lambda m: m.start())
        for m in chapters:
            prefix, key, supplement = _code_of(m)
            if key != "ndrc1943":
                continue
            cands.append((m, 4))
        cands.sort(key=lambda c: (c[0].start(), c[1]))
        for m, kind in cands:
            if m.start() < last_end:
                continue
            prefix, key, supplement = _code_of(m)
            if kind == 1 and key == "ndcl1913" and _SUPP_AFTER.match(text, m.end()):
                prefix, key, supplement = "N.D.C.L. Supp. 1925", "ndcl1925supp", "1925"
            if kind == 4:
                last_end = m.end()
                base = m.start("list")
                for i, n in enumerate(_C43_RE.finditer(m.group("list"))):
                    chapter = re.sub(rf'[{_DASH}]', '-', n.group(0))
                    out.append(Citation(
                        raw_text=m.group(0),
                        cite_type=CitationType.STATUTE,
                        jurisdiction="nd",
                        normalized=f"{prefix} ch. {chapter}",
                        components={"code": key, "chapter": chapter, "supplement": supplement},
                        sources=[],
                        position=m.start() if i == 0 else base + n.start(),
                    ))
                continue
            is43 = key == "ndrc1943"
            # The number's shape must be the code's own: a 1943 section is
            # title-dash-number and no other code's is.
            nums = [n for n in _NUM_RE.finditer(m.group("list"))
                    if bool(_IS43.match(n.group(0))) == is43]
            if not nums:
                continue
            if _foreign(text, m, key):
                last_end = m.end()          # read, and another jurisdiction's code
                continue
            last_end = m.end()
            base = m.start("list")
            for i, n in enumerate(nums):
                section = re.sub(rf'[{_DASH}]', '-', n.group(0))
                out.append(Citation(
                    raw_text=m.group(0),
                    cite_type=CitationType.STATUTE,
                    jurisdiction="nd",
                    normalized=f"{prefix} § {section}",
                    components={"code": key, "section": section, "supplement": supplement},
                    sources=[],
                    position=m.start() if i == 0 else base + n.start(),
                ))
        return out


register(4, NDOldCodeMatcher())

"""North Dakota Session Laws: reporter-style citation forms.

    2019 N.D. Sess. Laws ch. 404, § 2      the form the ND Supreme Court prints
    1975 N.D.Sess.Laws ch. 615             (spacing varies with the era)
    1987 N.D. Laws ch. 194
    N.D. Sess. Laws 1937, ch. 159
    S.L. 2019, ch. 404, § 4                the Century Code's own form
    S.L. 2021 (sp.), ch. 553               a special session, as the Code writes it
    1937 S.L., ch. 249
    S.L.N.D. 1945, ch. 106  /  ch. 176, SLND 1947

Every form above names North Dakota, or is the Century Code's `S.L.`, so none
needs a jurisdiction guard.

The PROSE forms name no state:

    chapter 67 of the Session Laws of 1897     the Court's form through the 1960s
    chapter 70, Laws 1907  /  c. 62, Laws 1890
    Laws 1925, c. 169  /  Laws of 1907, chapter 58  /  Sess. Laws 1923, c. 215
    chapters 91 and 93 of the Laws of 1921     (one citation per chapter)
    2009 Sess. Laws ch. 637
    chapter 240 of the 1937 Session Laws

They are read as North Dakota's (or, through 1889, Dakota Territory's) unless
the text just before them is speaking of another jurisdiction: see
``_foreign_context``. A hand read of 160 sites in North Dakota Supreme Court
opinions (2026-11-19) found another state's laws at none of 90 sites with no
other jurisdiction named nearby, and at 8 of 40 with one named; the guard is
built on that sample. A consumer that is NOT reading North Dakota documents
should drop citations whose ``components["form"]`` is ``"prose"``.

"Laws 1889" in prose is the last TERRITORIAL session (the State's first
session, begun November 1889, is cited "Laws 1890"), so it normalizes to
``1889 Dakota Terr. Sess. Laws ch. N``. Earlier territorial years keep the
North Dakota form, as the reporter-style forms do: no State session shares
those years.

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
# "Sess. Laws" / "Session Laws" / "Laws" (and the singular "Sess. Law")
_SESS = r'(?:Sess(?:ion|\.)\s?)?Laws?'

# 2019 N.D. Sess. Laws ch. 404  |  1987 N.D. Laws ch. 194  |  1919 N.D. Sess. Laws Spec. Sess. ch. 4
_YEAR_FIRST = re.compile(
    rf'(?<![\d-]){_YEAR}\s+{_ND}{_SESS},?\s*(Spec\.\s?Sess\.,?\s*)?{_CH}{_SEC}')
# N.D. Sess. Laws 1937, ch. 159
_YEAR_AFTER = re.compile(rf'(?<![\w.]){_ND}{_SESS},?\s+{_YEAR},?\s*{_CH}{_SEC}')
# S.L. 2019, ch. 404  |  S.L.1905, Ch. 34  |  S.L. 2021 (sp.), ch. 553
_CODE = re.compile(rf'(?<![\w.])S\.\s?L\.\s?{_YEAR}\s*(\(sp\.\))?,?\s*{_CH}{_SEC}')
# 1937 S.L., ch. 249
_CODE_YEAR_FIRST = re.compile(rf'(?<![\d-]){_YEAR}\s+S\.\s?L\.,?\s*{_CH}{_SEC}')
# S.L.N.D. 1945, ch. 106  |  SLND 1945, ch. 106
_SLND = re.compile(rf'(?<![\w.])(?:S\.\s?L\.\s?N\.\s?D\.|SLND),?\s*{_YEAR},?\s*{_CH}{_SEC}')
# ch. 176, S.L.N.D. 1947  |  Chapter 176, SLND 1947  |  ch. 249, S.L. 1937
_CH_FIRST = re.compile(
    rf'(?<![\w.]){_CH},?\s*(?:of\s+(?:the\s+)?)?(?:S\.\s?L\.\s?N\.\s?D\.|SLND|S\.\s?L\.),?\s*{_YEAR}(?![\d-])')

# ---- prose forms (no state named) -------------------------------------------
# "chapter" / "chap." / "ch." / "c." — never the tail of another word ("Sec. 2202")
_PCH_WORD = r'(?<![A-Za-z])(?:[Cc]h(?:ap)?(?:s?\.|ters?)|[Cc]\.)'
_PNUM = rf'\d{{1,4}}(?![\d{_DASH}])'
# one chapter, or a list: "chapters 91 and 93", "chapters 12, 14, and 20"
_PLIST = rf'({_PNUM}(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+){_PNUM}){{0,5}})'
_PLAWS = r'(?:(?:Session|Sess\.|Special\s+Session|Spec\.\s?Sess\.)\s+)?Laws'
_OF_ND = r'(?:\s*,?\s*of\s+(?:the\s+State\s+of\s+)?North\s+Dakota)?'
# chapter 70, Laws of 1907 | chapter 67 of the Session Laws of 1897 | c. 62, Laws 1890
# chapter 223, Session Laws of North Dakota for the year 1919
_P_CH_FIRST = re.compile(
    rf'{_PCH_WORD}\s*{_PLIST},?\s*(?:of\s+)?(?:the\s+)?{_PLAWS}{_OF_ND}'
    rf'\s*,?\s*(?:(?:of|for)\s+)?(?:the\s+year\s+)?{_YEAR}(?![\d-])')
# Laws 1925, c. 169 | Laws of 1907, chapter 58 | Sess. Laws 1923, c. 215 | Laws 1887, p. 39, c. 11
# Not when the chapter opens a chapter-first cite of its own:
# "chapters 91 and 93 of the Laws of 1921, chapters 179 and 299 of the Laws of 1923".
_P_LAWS_FIRST = re.compile(
    rf'(?<![\w.]){_PLAWS}\s*(?:of\s+)?{_YEAR},?\s*(?:p\.\s*\d+,\s*)?{_PCH_WORD}\s*({_PNUM})'
    rf'(?!(?:\s+and\s+\d+|\s*,\s*\d+)*\s*,?\s*(?:of\s+)?(?:the\s+)?{_PLAWS})' + _SEC)
# chapter 240 of the 1937 Session Laws | Chapter 22, § 6, of the 1973 Session Laws
# chapter 14 of the 1944 Special Session Laws | chapters 154 and 161 of the 1949 Session Laws
# Without this form a run of them was read year-first from the middle
# ("... the 1937 Session Laws, chapter 227 of the 1939 Session Laws" as 1937 ch. 227).
_P_CH_YEAR_MID = re.compile(
    rf'{_PCH_WORD}\s*{_PLIST}(?:,?\s*(?:§§?|[Ss]ec(?:s?\.|tions?))\s*(\d{{1,3}})(?![\d-]))?,?\s*'
    rf'(?:of|in)\s+(?:the\s+)?{_YEAR}\s+(?:N\.\s?D\.\s?|North\s+Dakota\s+)?'
    rf'(?:Session|Sess\.|Special\s+Session|Spec\.\s?Sess\.)\s+Laws(?![A-Za-z])')
# 2009 Sess. Laws ch. 637 | 1935 Session Laws, ch. 174
_P_YEAR_FIRST = re.compile(
    rf'(?<![\d-]){_YEAR}\s+(?:Session|Sess\.)\s+Laws?,?\s*{_PCH_WORD}\s*({_PNUM})' + _SEC)

# "Comp. Laws 1913, c. 5" and its kin are compilations, not session laws.
_NOT_SESSION = re.compile(
    r'(?:Comp(?:iled|\.)|Rev(?:ised|\.)|Gen(?:eral|\.)|Pub(?:lic|\.)|Priv(?:ate|\.)|Code|Codes|'
    r'Consol(?:idated|\.)|Howell|Supp(?:lement|\.))\s*$')

# Dakota Territory's first session; an earlier year cannot be Dakota's.
_FIRST_DAKOTA_YEAR = 1862
_LAST_TERRITORIAL_YEAR = 1889

_STATES = (
    r'Alabama|Ala\.|Alaska|Arizona|Ariz\.|Arkansas|Ark\.|California|Cal(?:if)?\.|Colorado|Colo\.|'
    r'Connecticut|Conn\.|Delaware|Del\.|Florida|Fla\.|Georgia|Ga\.|Hawaii|Idaho|Illinois|Ill\.|'
    r'Indiana|Ind\.|Iowa|Kansas|Kan(?:s)?\.|Kentucky|Ky\.|Louisiana|La\.|Maine|Me\.|Maryland|Md\.|'
    r'Massachusetts|Mass\.|Michigan|Mich\.|Minnesota|Minn\.|Mississippi|Miss\.|Missouri|Mo\.|'
    r'Montana|Mont\.|Nebraska|Neb(?:r)?\.|Nevada|Nev\.|New\s+Hampshire|N\.\s?H\.|New\s+Jersey|N\.\s?J\.|'
    r'New\s+Mexico|N\.\s?M\.|New\s+York|N\.\s?Y\.|North\s+Carolina|N\.\s?C\.|Ohio|Oklahoma|Okla?\.|'
    r'Oregon|Or(?:e)?\.|Pennsylvania|Pa\.|Rhode\s+Island|R\.\s?I\.|South\s+Carolina|S\.\s?C\.|'
    r'South\s+Dakota|S\.\s?D\.|Tennessee|Tenn\.|Texas|Tex\.|Utah|Vermont|Vt\.|Virginia|Va\.|'
    r'Washington|Wash\.|West\s+Virginia|W\.\s?Va\.|Wisconsin|Wis\.|Wyoming|Wyo\.|'
    r'England|English|Canada|Manitoba|Saskatchewan|Ontario'
)
# Congress and "United States" are left out on purpose: a federal act is not
# cited by chapter and "Laws" of a year, and a State act is constantly
# discussed beside the federal Constitution or a federal statute.
_FOREIGN = re.compile(rf'(?<![A-Za-z.])(?:{_STATES})(?![A-Za-z])|\bof\s+that\s+state\b')
# The end of the previous sentence. The word before the period must be a
# whole word, a number or a closing bracket, so "Revised Codes Mont. 1921" and
# "(Minn. Laws 1921" do not read as sentence ends.
_SENTENCE_END = re.compile(
    r'(?:[a-z]{4,}|\d|[)\]])[.?!]["\')\]”’]*(?:\[\w{1,5}\])?\s+(?=[A-Z"\'(\[“‘*]|$)')
# "North Dakota", "N. D.", "this state", "our" statute, and Dakota Territory
_HOME = re.compile(
    r'North\s+Dakota|(?<![A-Za-z.])N\.\s?D\.|\b[Tt]his\s+[Ss]tate\b|\b[Oo]ur\s+(?:statute|legislature|law|act|code)'
    r'|Dakota\s+[Tt]erritory|[Tt]erritory\s+of\s+Dakota|\b[Tt]erritorial\b|\bLegislative\s+Assembly\b')
# a reporter citation ("101 Cal. 442", "140 N. Y. 484", "75 N.Y.S. 976", "44 Iowa, 192"):
# a state named there is where a CASE was decided, not whose laws are cited
_REPORTER_CITE = re.compile(r'\b\d{1,3}\s+(?:[A-Z][A-Za-z]*\.?\s?){1,4}(?:\(\w[\w. ]*\)\s?)?,?\s*\d{1,4}\b')
_AFTER_HOME = re.compile(r'\s*,?\s*(?:\(|of\s+(?:the\s+)?(?:[Ss]tate\s+of\s+)?)?(?:North\s+Dakota|Dakota\s+Territory)')
_AFTER_FOREIGN = re.compile(rf'\s*,?\s*(?:\(|of\s+(?:the\s+)?(?:[Ss]tate\s+of\s+)?)(?:{_STATES})(?![A-Za-z])')
_CONTEXT = 140


def _foreign_context(text: str, start: int, end: int) -> bool:
    """True when a prose citation at text[start:end] reads as another
    jurisdiction's laws.

    The nearest jurisdiction named before the citation, in its own sentence
    (140 characters at most), decides: "the Minnesota workmen's compensation statute (Laws 1921, c. 82",
    "Revised Codes Mont. 1921, as amended by Laws 1923, c. 9", "the hawkers'
    act of that state (Laws 1889, c. 298)". States named inside a reporter
    citation are set aside first, since a North Dakota statute is often
    discussed beside a foreign case. "... of North Dakota" or "... of
    Minnesota" straight after the citation settles it either way."""
    after = text[end:end + 60]
    if _AFTER_HOME.match(after) or "North Dakota" in text[start:end]:
        return False
    if _AFTER_FOREIGN.match(after):
        return True
    pre = text[max(0, start - _CONTEXT):start]
    # only the sentence the citation sits in: a state named in the sentence
    # before is usually where a party lived or a case was decided
    ends = [m.end() for m in _SENTENCE_END.finditer(pre)]
    if ends:
        pre = pre[ends[-1]:]
    pre = _REPORTER_CITE.sub(lambda m: " " * len(m.group(0)), pre)
    last_foreign = max((m.end() for m in _FOREIGN.finditer(pre)), default=-1)
    last_home = max((m.end() for m in _HOME.finditer(pre)), default=-1)
    return last_foreign > last_home


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
    """North Dakota Session Laws: reporter-style forms, and the prose forms
    where nothing nearby says another jurisdiction's laws are meant."""

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
        # Prose forms. A chapter list yields one candidate per chapter, all on
        # the one span.
        for m in _P_CH_FIRST.finditer(text):
            for ch in re.findall(r'\d+', m.group(1)):
                cands.append((m, m.group(2), ch, None, "prose"))
        for m in _P_CH_YEAR_MID.finditer(text):
            chs = re.findall(r'\d+', m.group(1))
            for ch in chs:
                cands.append((m, m.group(3), ch, m.group(2) if len(chs) == 1 else None, "prose"))
        for m in _P_LAWS_FIRST.finditer(text):
            if _NOT_SESSION.search(text[max(0, m.start() - 16):m.start()]):
                continue
            cands.append((m, m.group(1), m.group(2), m.group(3), "prose"))
        for m in _P_YEAR_FIRST.finditer(text):
            cands.append((m, m.group(1), m.group(2), m.group(3), "prose"))
        # leftmost first; at one start the longer span, and a reporter-style
        # reading before a prose one
        cands.sort(key=lambda c: (c[0].start(), -(c[0].end() - c[0].start()), c[4] == "prose"))

        out: list[Citation] = []
        last_end = -1
        kept_span = None
        for m, year, chapter, section, special_form in cands:
            prose = special_form == "prose"
            span = (m.start(), m.end())
            # the later chapters of a list share the span of the first
            if m.start() < last_end and not (prose and span == kept_span):
                continue
            y, ch = int(year), int(chapter)
            if prose and span != kept_span:
                if y < _FIRST_DAKOTA_YEAR or _foreign_context(text, m.start(), m.end()):
                    last_end = max(last_end, m.end())   # read, and not North Dakota's
                    kept_span = None
                    continue
            last_end = m.end()
            kept_span = span if prose else None
            if prose:
                special_form = None
            spec_sess = special_form == "spec"
            territorial = prose and y == _LAST_TERRITORIAL_YEAR
            url = session_laws_url(y, special=bool(special_form))
            if territorial:
                normalized = f"{y} Dakota Terr. Sess. Laws ch. {ch}"
            else:
                normalized = f"{y} N.D. Sess. Laws {'Spec. Sess. ' if spec_sess else ''}ch. {ch}"
            out.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.SESSION_LAW,
                jurisdiction="nd",
                normalized=normalized,
                components={"year": str(y), "chapter": str(ch), "section": section,
                            "special": bool(special_form),
                            "form": "prose" if prose else "reporter",
                            "territorial": territorial},
                pinpoint=f"§ {section}" if section else None,
                sources=[Source("ndlegis", url)] if url else [],
                position=m.start(),
            ))
        return out


register(4, NDSessionLawMatcher())

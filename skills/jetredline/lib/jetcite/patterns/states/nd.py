"""North Dakota-specific citation patterns: NDCC, NDAC, ND Constitution, ND Court Rules."""

import re

from jetcite.models import Citation, CitationType, Source
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher
from jetcite.sources.ndconst import (
    OLD_SECTION_MAX,
    nd_constitution_old_url,
    nd_constitution_url,
)
from jetcite.sources.ndcourts import nd_court_rule_url, nd_local_rule_url
from jetcite.sources.ndlegis import ndac_url, ndcc_chapter_url, ndcc_section_url

# Inter-group separator inside an NDCC/NDAC section number: a single dash
# (ASCII hyphen-minus, the Unicode hyphen/dash family, or a minus sign) flanked
# by optional whitespace. Tolerating the whitespace lets a section number that
# the court's PDF wraps across a line — e.g. "28-32-\n46" or "28-32- 46" — still
# parse as one cite. Requiring an actual dash (not the old loose ``[^.\w]``) also
# drops a latent false positive where a comma between numbers was read as a
# separator. (Hardened 2026-06-20.)
_SEP = r'\s*[-‐‑‒–—―−]\s*'

# ---------------------------------------------------------------------------
# NDCC Section: N.D.C.C. § 12.1-32-01
# ---------------------------------------------------------------------------
_NDCC_SECTION = re.compile(
    r'(?:(?:N[\s.]*D[\s.]*C(?:ent)*[.\s]*C(?:ode)*[,.\s]{0,3}'
    r'(?:[^\s\d]{0,3}|[Ss]ection|[Ss]ec)\s{0,4})'
    r'|(?:(?:[Ss]ection|[Ss]ec\.?)\s+))'
    r'(\d{1,2})(?:\.(\d+))?'
    rf'{_SEP}(\d{{1,2}})(?:\.(\d+))?'
    rf'{_SEP}(\d{{1,2}})(?:\.(\d+))?'
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
    rf'{_SEP}(\d{{1,2}})(?:\.(\d+))?',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# NDAC: N.D.A.C. § 43-02-05-01
# ---------------------------------------------------------------------------
_NDAC_SECTION = re.compile(
    r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]*[^\s\d]{0,3}\s*'
    rf'(\d{{1,2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?){_SEP}'
    rf'(\d{{2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?)',
    re.IGNORECASE,
)

_NDAC_CHAPTER = re.compile(
    r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*[,.\s]{0,2}'
    r'(?:Ch\.|ch\.|Ch|ch)\s*'
    rf'(\d{{1,2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?)',
    re.IGNORECASE,
)

_NDAC_REVERSE = re.compile(
    rf'(\d{{2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?){_SEP}'
    rf'(\d{{2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?)'
    r'(?:(?:\([a-z\d]*\))*|[^\d;])(?:,\s{0,3})'
    r'N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C|Rules|R)*',
    re.IGNORECASE,
)

# NDAC section written in prose with a forward "Section"/"Sec." cue:
#   "Section 75-02-04.1-07(7) of the North Dakota Administrative Code"
#   "Section 75-02-04.1-07"  (bare four-group number)
# A fourth number group distinguishes NDAC (title-article-chapter-section)
# from NDCC (title-chapter-section), so a four-group "Section" cite is NDAC.
# The trailing "Administrative Code" cue is optional; the fourth group alone
# is sufficient. The optional "(n)" is captured as a subsection pinpoint.
_NDAC_SECTION_FWD = re.compile(
    r'(?:[Ss]ection|[Ss]ec\.?)\s+'
    rf'(\d{{1,2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?){_SEP}'
    rf'(\d{{2}}(?:\.\d+)?){_SEP}(\d{{2}}(?:\.\d+)?)'
    r'(?:\(([^)]+)\))?'
    r'(?:[,\s]*(?:of\s+the\s+)?'
    r'(?:North\s+Dakota\s+Admin(?:istrative)?\s+Code'
    r'|N[\s.]*D[\s.]*A(?:dmin)*[.\s]*(?:Code|C))|\W|$)',
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
    r'(?:Article|Art\.?)\s+\[?([IVX]+)\]?[,\s]+(?:section|sec\.?)\s+(\d+)'
    r'(?:(?:\([a-z\d]*\))*|\D)\s+of\s+the\s+'
    r'N(?:orth)?\s*D(?:akota)?\s*Const(?:itution)?',
    re.IGNORECASE,
)

# Pre-1981 (1889 numbering) ND Constitution: sections were numbered
# continuously 1-217 with no article, so old cites are section-only —
# "section 121 of the Constitution," "Section 121, N.D. Const.,"
# "N.D. Const. § 121." Normalized to "N.D. Const. § NNN" (the
# const_crosswalk old_cite format).

# One leading section number plus an optional enumeration tail
# ("185 and 186", "179, 180, and 181"); each number becomes its own cite.
# Old numbering is integer-only (1-217): a DECIMAL continuation means the
# number belongs to something else ("N.D. Const., Section 16.1-11-08,
# N.D.C.C." is a statute cite in a string cite, not old § 16), as does a
# statute-shaped dash chain ("Sec. 11-1002, NDRC 1943" = dash + 4 digits;
# "Section 54-03-01" = dash-separated chain). A section RANGE is kept —
# "Secs. 130, 166–173" cites old § 166 (range tails stay unparsed).
_NOT_STATUTE_NUM = r'(?!\.\d)(?![-–—]\d{4})(?![-–—]\d{1,3}[.\-–—]\d)'
_OLD_SECTION_LIST = (
    rf'(\d{{1,3}})(?!\d){_NOT_STATUTE_NUM}'
    rf'((?:\s*,\s*(?:and\s+)?\d{{1,3}}|\s+and\s+\d{{1,3}})*)(?!\d){_NOT_STATUTE_NUM}'
)

# Optional spelled-out attribution after "Constitution": "of North Dakota",
# "of the State of North Dakota", "of the state", "of 1889".
_OLD_CONST_OF_ND = (
    r'(?:\s+of\s+(?:the\s+)?(?:(?:State\s+of\s+)?North\s+Dakota|state\b|1889))?'
)

# Trailing form: "section(s) N [...] of the [state|North Dakota|1889]
# Constitution [of North Dakota]" / "Section N, N.D. Const." The attribution
# vocabulary is closed (state, our, N.D., 1889, original...), so
# "section 2 of the United States Constitution" cannot match; the lookahead
# additionally rejects "of the Constitution of the United States".
_ND_CONST_OLD_TRAIL = re.compile(
    r'(?:§§?|(?<![A-Za-z])[Ss]ec(?:tion)?s?\.?)\s*'
    rf'{_OLD_SECTION_LIST}'
    r'[,\s]*(?:of\s+)?(?:the\s+|our\s+)?'
    r'(?:(?:1889|original|old|former)\s+)?'
    r'(?:(?:North\s+Dakota|N[.\s]*D[.\s]*|state)\s+)?'
    r'Const(?:itution\b|\.)'
    rf'{_OLD_CONST_OF_ND}'
    r'(?!\s+of\b)'
    # A ROMAN-numbered article right after "Const." means the section numbers
    # belong to a MODERN article-scoped cite read tail-first ("Sections 1
    # and 10, N.D. Const. art. III"); ", Article I" likewise. Arabic-numbered
    # ("Constitution, article 28 of Amendments thereto") is a pre-1981
    # amendment article — a real old-numbering context, kept. A new sentence
    # ("... Constitution. Article VI provides") is not rejected: the no-comma
    # branch requires the abbreviated "Art." form.
    r'(?!\s*,\s*[Aa]rt(?:icle)?\b\.?\s*\[?[IVXLC])(?!\s+[Aa]rt\b\.\s*\[?[IVXLC])',
    re.IGNORECASE,
)

# Leading form: "N.D. Const. § 121", "Constitution, § 121". A bare "Const."
# (no ND marker, not spelled out) is NOT accepted — that shape belongs to
# other jurisdictions' cites ("Iowa Const. ...").
_ND_CONST_OLD_LEAD = re.compile(
    r'(?:N(?:orth)?[\s.]*D(?:akota)?[\s.]*Const(?:itution\b|\.)|Constitution\b)'
    rf'{_OLD_CONST_OF_ND}'
    r'[,\s]*(?:§§?|(?<![A-Za-z])[Ss]ec(?:tion)?s?\.?)\s*'
    rf'{_OLD_SECTION_LIST}'
    # "N.D.Const., section 6, of that same Article" — the section number is
    # scoped to an article named earlier in the sentence, not old numbering.
    r'(?!,?\s*of\s+th(?:at|e)\s+same\s+[Aa]rt)',
    re.IGNORECASE,
)

# Reject an old-form match when the immediately preceding text shows it is
# really an article-scoped cite ("Article II, section 1 of the Constitution",
# including a bracket-altered quotation "article [I], section 1 ...")
# or a federal one ("United States Constitution, § 2"). The article branch
# tolerates an intervening enumeration chain ("Article I, § 3 and § 4 of
# the ..." — the § 4 match is the tail of the SAME article-scoped cite) and
# an intervening star-page marker ("Article VI, [*348] Section 3 of the ...").
_OLD_CONST_BAD_PREFIX = re.compile(
    r'\b(?:[Aa]rt(?:icle)?\.?\s*\[?[IVXLCivxlc\d]+\]?\s*[,.]?'
    # comma/and only — a SEMICOLON ends a string cite, so "U.S. Const.
    # art. 1, § 10; N.D. Const. § 16" must not chain into the ND cite
    r'(?:\s*(?:§§?|[Ss]ec(?:tions?)?\.?)\s*\d+(?:\.\d+)?,?\s*(?:and\s+)?)*'
    r'(?:\s*\[\*\d+\])?'
    r'|U\.?\s*S\.?|United\s+States|[Ff]ed(?:eral)?\.?)\s*$'
)

# A bare-"Constitution" lead match ("Constitution, § 2") preceded by a
# capitalized word is another jurisdiction's constitution ("Montana
# Constitution, § 2, art. 8") — the closed attribution vocabulary can't see
# words the pattern never consumes. Allowlist the capitalized words that
# legitimately precede an ND "Constitution, § N" in running text. A lowercase
# "new"/"proposed"/"revised" marks a REPLACEMENT document ("The new
# constitution § 5" = the post-1981 text, cited article-form elsewhere), not
# the 1889 numbering.
_BARE_CONST_OK_PREFIX = frozenset({"The", "State", "Our", "Said"})
_BARE_CONST_BAD_LOWER = frozenset({"new", "proposed", "revised"})
_CAP_WORD_BEFORE = re.compile(r'([A-Z][a-zA-Z]+)\s+$')
_WORD_BEFORE = re.compile(r'([A-Za-z]+)\s+$')

# ---------------------------------------------------------------------------
# ND Court Rules
# ---------------------------------------------------------------------------

# N.D.R.Ct. 3-part: Rule 8.3.1
# The trailing-form gap between the rule number and the set marker excludes
# ";" throughout: a semicolon is a string-cite boundary, so "2024 ND 4;
# N.D.R.Civ.P. 60(b)" must not read the neutral cite's "4" as a rule number.
_NDRCT_3 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^\d;])[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2})\.(\d{1,2}))',
    re.IGNORECASE,
)

# N.D.R.Ct. 2-part: Rule 11.10
_NDRCT_2 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^.\d;])[,\s]*N[\s.]*D[\s.]*R[\s.]*Ct[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Ct[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2}))',
    re.IGNORECASE,
)

# N.D. Sup. Ct. Admin. R. 2-part
_ADMIN_2 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})\.(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^.\d;])[,\s]*'
    r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
    r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*(?:Rule\s+)?(\d{1,2})\.(\d{1,2}))',
    re.IGNORECASE,
)

# N.D. Sup. Ct. Admin. R. 1-part
_ADMIN_1 = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2})'
    r'(?:(?:\([a-z\d]*\))*|[^.\d;])[,\s]*'
    r'N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[\s.]*'
    r'|N[\s.]*D[\s.]*Sup[\s.]*Ct[\s.]*Admin[\s.]*R[.\s]*(?:Rule\s+)?(\d{1,2})(?![.\d]))',
    re.IGNORECASE,
)

# N.D.R.Ev. (3-4 digit rule numbers)
_NDREV = re.compile(
    r'(?:(?:Rule\s+)?(\d{3,4})'
    r'(?:(?:\([a-z\d]*\))*|[^\d;])[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Ev(?:id|idence)?[.\s]*(?:Rule\s+)?(\d{3,4}))',
    re.IGNORECASE,
)

# Procedural rules: N.D.R.Civ.P., N.D.R.Crim.P., N.D.R.App.P., N.D.R.Juv.P.
_PROC_RULES = re.compile(
    r'(?:(?:Rule\s+)?(\d{1,2}(?:\.\d{1,2})?)'
    r'(?:(?:\([a-z\d]*\))*|[^.\d;])[,\s]*'
    r'(?:North\s+Dakota\s+Rules?\s+of\s+(Civil|Criminal|Appellate|Juvenile)\s+Procedure'
    r'|N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*'
    r'P(?:rocedure)?[\s.]*))',
    re.IGNORECASE,
)

# Also match "N.D.R.Civ.P. Rule 12" (rule set first)
_PROC_RULES_PREFIX = re.compile(
    r'N[\s.]*D[\s.]*R[\s.]*(Civ|Crim|App|Juv)(?:il|inal|ellate|enile)?[\s.]*'
    r'P(?:rocedure)?[.\s]*(?:Rule\s+)?(\d{1,2}(?:\.\d{1,2})?)',
    re.IGNORECASE,
)

# N.D.R. Prof. Conduct
_PROF_CONDUCT = re.compile(
    r'(?:(?:Rule\s+)?(\d)\.(\d+)'
    r'(?:(?:\([a-z\d]*\))*|[^\d;])[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Prof(?:essional)?[\s.]*Conduct[.\s]*(?:Rule\s+)?(\d)\.(\d+))',
    re.IGNORECASE,
)

# N.D.R. Lawyer Discipl.
_LAWYER_DISCIPL = re.compile(
    r'(?:(?:Rule\s+)?(\d)\.(\d+)'
    r'(?:(?:\([a-z\d]*\))*|[^\d;])[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[\s.]*'
    r'|N[\s.]*D[\s.]*R[\s.]*Lawyer[\s.]*Discipl(?:ine)?[.\s]*(?:Rule\s+)?(\d)\.(\d+))',
    re.IGNORECASE,
)

# N.D. Code Jud. Conduct (Canon:Rule format)
_JUD_CONDUCT_CANON = re.compile(
    r'Canon\s+(\d)\s*:\s*Rule\s+(\d)\.(\d+)'
    r'(?:(?:\([a-z\d]*\))*|[^\d;])[,\s]*'
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
    r'(?:(?:\([a-z\d]*\))*|[^\d;])[,\s]*'
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

# N.D. Sup. Ct. Admin. Order — the Supreme Court's administrative orders
# (Order 25 suspended jury trials during COVID-19), a set distinct from
# N.D. Sup. Ct. Admin. R.
#
# Discrimination matters here: "Administrative Order" alone is ordinary prose
# for an AGENCY order in ND opinions ("the State Engineer's Administrative
# Order 10-1", a highway-commissioner licence revocation). Two cues make a
# reference unambiguous, and nothing else is extracted:
#   1. the set is named        — "N.D. Sup. Ct. Admin. Order 25"
#   2. the court owns it       — "this Court's Administrative Order 25",
#                                "Administrative Order No. 1 of this Court"
# A hyphen-suffixed number ("10-1", "2-1979") is an agency docket form and is
# excluded outright. Corpus-verified 2026-07-31: these cues cover every
# genuine reference; bare "Administrative Order 25" repeats inside an opinion
# that already gave a full cite are deliberately left to the full cite rather
# than guessed at.
_ADMIN_ORDER = re.compile(
    r'(?:N[\s.]*D[\s.]*)?Sup(?:reme)?[\s.]*Ct?(?:ourt)?[\s.]*'
    r'Admin(?:istrative)?[\s.]*Order[\s.]*(?:No[\s.]*)?(\d{1,3})(?!\s*-\s*\d)',
    re.IGNORECASE,
)

_ADMIN_ORDER_POSSESSIVE = re.compile(
    r'(?:this\s+Court\'?s?\s+Administrative[\s.]*Order[\s.]*(?:No[\s.]*)?'
    r'(\d{1,3})(?!\s*-\s*\d)'
    r'|Administrative[\s.]*Order[\s.]*(?:No[\s.]*)?(\d{1,3})(?!\s*-\s*\d)'
    r'\s+of\s+this\s+Court)',
    re.IGNORECASE,
)

# N.D.R. Proc. R. — the court writes "N.D.R.Proc.R. § 3.1", so the section
# sign is optional and the number may carry a decimal part.
_PROC_R = re.compile(
    r'(?:N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R[.\s]*(?:§\s*)?(?:Rule\s+)?'
    r'(\d+(?:\.\d+)?)'
    r'|(?:§\s*)?(?:Rule\s+)?(\d+(?:\.\d+)?)[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Proc[\s.]*R)',
    re.IGNORECASE,
)

# N.D.R. Local Ct. Pr.
_LOCAL_CT = re.compile(
    r'(?:N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R?[.\s]*(?:§\s*)?'
    r'(?:Rule\s+)?(\d+(?:\.\d+)?)'
    r'|(?:§\s*)?(?:Rule\s+)?(\d+(?:\.\d+)?)[,\s]*'
    r'N[\s.]*D[\s.]*R[\s.]*Local[\s.]*Ct[\s.]*P[\s.]*R?)',
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

# Ltd. Practice of Law by Law Students R. — the rules print their numbers as
# roman numerals in the headings but the corpus cites them in arabic
# ("Ltd. Practice of Law by Law Students R. 3"), so a roman capture is
# converted. Corpus-verified 2026-07-31: all 118 mentions of this set in ND
# opinions are counsel-appearance lines ("appearing under the Rule on the
# Limited Practice of Law by Law Students"), never a numbered citation — the
# pattern exists so a future numbered cite normalizes correctly, and the
# unnumbered appearance lines correctly yield nothing.
_STUDENT = re.compile(
    r'(?:Limited\s+Practice\s+of\s+Law\s+by\s+Law\s+Students|'
    r'N[\s.]*D[\s.]*Student[\s.]*Practice[\s.]*R(?:ule)?)'
    r'[.\s]*R?[.\s]*(?:§\s*)?([IVX]+|\d{1,2})(?![\d\w])',
    re.IGNORECASE,
)

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}


def _roman_to_arabic(s: str) -> str:
    """'VII' -> '7'. Returns the input unchanged if it is already arabic."""
    if s.isdigit():
        return s
    total = prev = 0
    for ch in reversed(s.upper()):
        v = _ROMAN_VALUES.get(ch)
        if v is None:
            return s
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return str(total)

_PROC_MAP = {
    "civil": "ndrcivp", "civ": "ndrcivp",
    "criminal": "ndrcrimp", "crim": "ndrcrimp",
    "appellate": "ndrappp", "app": "ndrappp",
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
        # Deduplicate in two passes. First, when two matches start at the same
        # position, keep the one with the longer raw_text (more specific match) —
        # this drops, e.g., a truncated NDCC match in favor of the fuller NDAC one.
        by_pos: dict[int, Citation] = {}
        for cite in results:
            if cite.position not in by_pos or len(cite.raw_text) > len(by_pos[cite.position].raw_text):
                by_pos[cite.position] = cite
        # Second, collapse overlapping matches that normalize to the SAME citation
        # (one textual cite parsed two ways, e.g. a forward "Section X" match and a
        # reverse "X, N.D.A.C." match), keeping the longer raw_text. Distinct cites
        # have different normalized forms, and separate occurrences of one cite sit
        # at non-overlapping positions, so both are preserved.
        ordered = sorted(by_pos.values(), key=lambda c: (c.position, -len(c.raw_text)))
        kept: list[Citation] = []
        for cite in ordered:
            start, end = cite.position, cite.position + len(cite.raw_text)
            if any(
                k.normalized == cite.normalized
                and start < k.position + len(k.raw_text)
                and k.position < end
                for k in kept
            ):
                continue
            kept.append(cite)
        return kept

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

        for m in _NDAC_SECTION_FWD.finditer(text):
            p1, p2, p3, p4 = m.group(1), m.group(2), m.group(3), m.group(4)
            subsection = m.group(5)
            normalized = f"N.D.A.C. § {p1}-{p2}-{p3}-{p4}"
            results.append(Citation(
                raw_text=m.group(0),
                cite_type=CitationType.REGULATION,
                jurisdiction="nd",
                normalized=normalized,
                components={"part1": p1, "part2": p2, "part3": p3, "part4": p4},
                pinpoint=f"({subsection})" if subsection else None,
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

        # Pre-1981 (1889 numbering) forms. Article-form matches above take
        # precedence: an old-form match overlapping one is the tail of an
        # article-scoped cite ("Article VI, section 2 of the North Dakota
        # Constitution"), not an old cite.
        modern_spans = [
            (c.position, c.position + len(c.raw_text))
            for c in results
            if c.cite_type == CitationType.CONSTITUTION
        ]
        for pattern in (_ND_CONST_OLD_TRAIL, _ND_CONST_OLD_LEAD):
            for m in pattern.finditer(text):
                self._emit_old_const(m, text, results, modern_spans)

    def _emit_old_const(self, m, text, results, modern_spans):
        start, end = m.start(), m.end()
        if any(s < end and start < e for s, e in modern_spans):
            return
        # A match carrying its own N.D. marker ("N.D. Const. § 16") cannot be
        # scoped by a preceding article or federal reference — "U.S. Const.
        # art. 1, § 10, N.D. Const. § 16" is a string cite whose ND member is
        # real. The prefix guard applies only to bare/section-first forms.
        if m.group(0)[:1].lower() != "n":
            if _OLD_CONST_BAD_PREFIX.search(text, max(0, start - 30), start):
                return
        if m.group(0)[:5].lower() == "const":
            w = _WORD_BEFORE.search(text, max(0, start - 25), start)
            if w and w.group(1) in _BARE_CONST_BAD_LOWER:
                return
            cap = _CAP_WORD_BEFORE.search(text, max(0, start - 25), start)
            if cap and cap.group(1) not in _BARE_CONST_OK_PREFIX:
                return
        # (offset, number) for the lead section and any enumeration tail.
        sections = [(m.start(1), m.group(1))]
        for num in re.finditer(r'\d{1,3}', m.group(2)):
            sections.append((m.start(2) + num.start(), num.group(0)))
        if any(not 1 <= int(n) <= OLD_SECTION_MAX for _, n in sections):
            return
        for pos, n in sections:
            url = nd_constitution_old_url(n)
            results.append(Citation(
                raw_text=m.group(0) if pos == sections[0][0] else text[pos:end],
                cite_type=CitationType.CONSTITUTION,
                jurisdiction="nd",
                normalized=f"N.D. Const. § {n}",
                components={"section": n, "numbering": "1889"},
                sources=[Source("ndconst", url)] if url else [],
                position=m.start() if pos == sections[0][0] else pos,
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
                    "ndrappp": "N.D.R.App.P.",
                    "ndrjuvp": "N.D.R.Juv.P.",
                }.get(rule_set, rule_set)
                parts = rule_num.split(".")
                results.append(self._rule_cite(m, rule_set, display, parts))

        # Procedural rules (prefix pattern)
        for m in _PROC_RULES_PREFIX.finditer(text):
            proc_type = m.group(1).lower()
            rule_num = m.group(2)
            rule_set = _PROC_MAP.get(proc_type)
            if rule_set and rule_num:
                display = {
                    "ndrcivp": "N.D.R.Civ.P.",
                    "ndrcrimp": "N.D.R.Crim.P.",
                    "ndrappp": "N.D.R.App.P.",
                    "ndrjuvp": "N.D.R.Juv.P.",
                }.get(rule_set, rule_set)
                parts = rule_num.split(".")
                results.append(self._rule_cite(m, rule_set, display, parts))

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

        # N.D. Sup. Ct. Admin. Order (named set, then the possessive cue)
        seen_admin_order: set[int] = set()
        for pattern in (_ADMIN_ORDER, _ADMIN_ORDER_POSSESSIVE):
            for m in pattern.finditer(text):
                order = next((g for g in m.groups() if g), None)
                if not order or m.start() in seen_admin_order:
                    continue
                seen_admin_order.add(m.start())
                results.append(self._rule_cite(
                    m, "ndsupctadminorder", "N.D. Sup. Ct. Admin. Order",
                    [order]))

        # N.D.R. Proc. R. and N.D.R. Local Ct. Pr. — unlike the other rule
        # sets, these number their SECTIONS with integers and their
        # subsections with decimals ("Section 3" contains 3.1, 3.2, 3.3), so
        # "N.D.R.Proc.R. § 3.1" is a pinpoint into section 3, not a rule 3.1.
        # Normalizing to the section is what makes the cite resolve; the
        # pinpoint is preserved in components.
        for pattern, rule_set, display in (
                (_PROC_R, "ndrprocr", "N.D.R. Proc. R."),
                (_LOCAL_CT, "ndrlocalctpr", "N.D.R. Local Ct. Pr.")):
            for m in pattern.finditer(text):
                rule = m.group(1) or m.group(2)
                if not rule:
                    continue
                section, _, sub = rule.partition(".")
                cite = self._rule_cite(m, rule_set, display, [section])
                if sub:
                    cite.components["pinpoint"] = rule
                results.append(cite)

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

        # Ltd. Practice of Law by Law Students R.
        for m in _STUDENT.finditer(text):
            results.append(self._rule_cite(
                m, "ltdpracticeoflawbylawstudentsr",
                "Ltd. Practice of Law by Law Students R.",
                [_roman_to_arabic(m.group(1))]))

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


# ---------------------------------------------------------------------------
# Rule-set marker vocabulary — bare "Rule N" short-form attribution
# ---------------------------------------------------------------------------
# Ported from ndcourts-mcp notes.py (rule_set_markers / _SPELLED_MARKERS),
# proven on the opinion corpus in get_notes_of_decisions. A marker is any
# in-text mention of a rule set — compact prefix ("N.D.R.Civ.P.", spacing-
# tolerant) or spelled-out name ("Rules of Civil Procedure") — used by
# scanner._resolve_pin_cites to attribute a bare "Rule 60(b)" to a set.
# Canonical names match this module's normalized display prefixes so an
# attributed set can be compared against full-cite normalized forms. Federal
# sets are in the vocabulary as decoys: a bare "Rule 12" following a
# Fed. R. Civ. P. discussion must not be attributed to the ND set.


def _flex_prefix_pattern(prefix: str) -> str:
    """A regex for a rule-set prefix tolerant of spacing variants.

    'N.D.R.Civ.P.' matches 'N.D.R.Civ.P.', 'N. D. R. Civ. P.'; the spaced
    canonicals ('N.D. Sup. Ct. Admin. R.') also match their compact forms."""
    out = []
    for ch in prefix:
        if ch == ".":
            out.append(r"\.\s*")
        elif ch == " ":
            out.append(r"\s*")
        else:
            out.append(re.escape(ch))
    return "".join(out)


# Spelled-out names for the commonly narrated rule sets (the compact-dotted
# marker for every set is generated from its canonical prefix).
#
# Longest form first: rule_set_markers keeps the longer of two markers that
# start together and drops the contained one, so the state form must be
# offered alongside the bare one. Only Civ.P. carried its spelled-out state
# form; without the rest, "Rule 32(a)(8)(A) of the North Dakota Rules of
# Appellate Procedure" left "North Dakota " sitting in the trailing gap, the
# trailing rung was rejected, and a certificate of compliance — which carries
# that citation in nearly every appellate brief — yielded no rule cite at all.
_SPELLED_MARKERS = {
    "N.D.R.Civ.P.": [r"North Dakota Rules of Civil Procedure",
                     r"Rules of Civil Procedure"],
    "N.D.R.Crim.P.": [r"North Dakota Rules of Criminal Procedure",
                      r"Rules of Criminal Procedure"],
    # Briefs write "North Dakota Rule of Evidence 201" — singular.
    "N.D.R.Ev.": [r"North Dakota Rules? of Evidence",
                  r"Rules? of Evidence"],
    "N.D.R.App.P.": [r"North Dakota Rules of Appellate Procedure",
                     r"Rules of Appellate Procedure"],
    "N.D.R.Ct.": [r"North Dakota Rules of Court",
                  r"Rules of Court"],
    "N.D.R.Juv.P.": [r"North Dakota Rules of Juvenile Procedure",
                     r"Rules of Juvenile Procedure"],
    "N.D. Sup. Ct. Admin. R.": [r"Administrative Rule"],
    "N.D.R. Prof. Conduct": [r"North Dakota Rules of Professional Conduct",
                             r"Rules of Professional Conduct"],
    "N.D. Code Jud. Conduct": [r"North Dakota Code of Judicial Conduct",
                               r"Code of Judicial Conduct"],
    "Fed. R. Civ. P.": [r"Federal Rules of Civil Procedure"],
    "Fed. R. Crim. P.": [r"Federal Rules of Criminal Procedure"],
    "Fed. R. Evid.": [r"Federal Rules of Evidence"],
    "Fed. R. App. P.": [r"Federal Rules of Appellate Procedure"],
    "Fed. R. Bankr. P.": [r"Federal Rules of Bankruptcy Procedure"],
}

_MARKER_RULE_SETS = (
    "N.D.R.Civ.P.", "N.D.R.Crim.P.", "N.D.R.Ev.", "N.D.R.App.P.",
    "N.D.R.Ct.", "N.D.R.Juv.P.", "N.D. Sup. Ct. Admin. R.",
    "N.D.R. Prof. Conduct", "N.D. Code Jud. Conduct",
    "Fed. R. Civ. P.", "Fed. R. Crim. P.", "Fed. R. Evid.",
    "Fed. R. App. P.", "Fed. R. Bankr. P.",
)

RULE_SET_JURISDICTION = {
    prefix: ("us" if prefix.startswith("Fed.") else "nd")
    for prefix in _MARKER_RULE_SETS
}

_MARKER_PATTERNS: list[tuple[str, re.Pattern]] = [
    (canon, re.compile(pat))
    for canon in _MARKER_RULE_SETS
    for pat in [_flex_prefix_pattern(canon)] + _SPELLED_MARKERS.get(canon, [])
]


def rule_set_markers(text: str) -> list[tuple[int, int, str]]:
    """Every rule-set mention in ``text`` as (start, end, canonical_prefix),
    sorted by position. A marker fully contained in a longer one is dropped
    ('Rules of Civil Procedure' inside 'Federal Rules of Civil Procedure')."""
    hits: list[tuple[int, int, str]] = []
    for canon, pat in _MARKER_PATTERNS:
        for m in pat.finditer(text):
            hits.append((m.start(), m.end(), canon))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    kept: list[tuple[int, int, str]] = []
    for s, e, c in hits:
        if kept and s >= kept[-1][0] and e <= kept[-1][1]:
            continue  # contained in the previous (longer) marker
        kept.append((s, e, c))
    return kept


register(4, NDMatcher())

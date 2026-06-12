"""Bluebook pin-cite short-form patterns (back-references to earlier full cites).

Captures the short forms the full-cite matchers deliberately refuse to match
(so they can't truncate — see TODO.md "Federal/Regional reporter citations
split on the volume 'd' suffix"):

  Shape 1 — reporter pin:        491 F.3d at 363; 409 So. 3d at 188;
                                 2024 ND 156 at ¶ 12
  Shape 2 — name + reporter pin: Goss, 491 F.3d at 363 (the reporter pattern
                                 matches; the name comes from
                                 casename.extract_antecedent_name in scanner)
  Shape 3 — bare-name pin:       Goss at 363; Niemeyer, ¶ 12
  Id. forms:                     Id.; Id. at 363; id. ¶ 14; *Id.* at 5

Matching alone does not make a citation entry: candidates carry
``is_pin_cite=True`` and are linked to their parent full cite by
``scanner._resolve_pin_cites``, which drops unresolvable bare-name candidates
(false-positive control) and keeps unresolvable explicit pin syntax as
warnings. ``scan_text`` only surfaces them when called with
``include_pin_cites=True``.
"""

import re

from jetcite.casename import _NOT_A_NAME, _SIGNALS
from jetcite.models import Citation, CitationType
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher

_PAGE = r"(\d+(?:\s*[-–]\s*\d+)?)"
_PARA = r"¶¶?\s*(\d+(?:\s*[-–]\s*\d+)?)"

# Shape 1 — reporter pins. Every pattern requires a reporter token before
# "at", so prose like "argued at 363" cannot anchor, and a full cite like
# "491 F.3d 355" (bare page, no "at") cannot match.
_FED_PIN = re.compile(r"\b(\d+)\s+F\.\s?(2d|3d|4th)\s+at\s+" + _PAGE)
_F_SUPP_PIN = re.compile(r"\b(\d+)\s+F\.\s?Supp\.(?:\s?(2d|3d))?\s+at\s+" + _PAGE)
_US_PIN = re.compile(r"\b(\d+)\s+U\.S\.\s+at\s+" + _PAGE)
_S_CT_PIN = re.compile(r"\b(\d+)\s+S\.\s?Ct\.\s+at\s+" + _PAGE)
_REGIONAL_PIN = re.compile(
    r"\b(\d+)\s+(N\.W\.|N\.E\.|S\.E\.|S\.W\.|So\.|A\.|P\.)\s?([23]d)?\s+at\s+" + _PAGE
)

# Neutral "at ¶" short form. The full-cite pattern in neutral.py also accepts
# "at ¶" now; this candidate matters when the same cite appeared earlier and
# dedup swallows the second full match — the pin entry preserves its pinpoint.
_ND_AT_PIN = re.compile(r"\b([12]\d{3})\s+ND\s+(\d{1,3})\s+at\s+" + _PARA)

# Shape 3 — bare-name candidates. One or two capitalized words (no digits —
# keeps reporter fragments like "F.3d" from qualifying) followed by an
# explicit pin. These are CANDIDATES ONLY: the scanner drops any whose name
# does not resolve against a full cite earlier in the document.
_NAME = r"[A-Z][A-Za-z.'’\-]{2,}(?:\s+[A-Z][A-Za-z.'’\-]+)?"
_NAME_AT_PIN = re.compile(rf"\b({_NAME}),?\s+at\s+" + _PAGE + r"(?=[\s.,;:)\]]|$)")
_NAME_PARA_PIN = re.compile(rf"\b({_NAME}),\s*" + _PARA)

# Id. forms. The backreferenced (?P=mk) tolerates markdown italics (*Id.*)
# from pdf→markdown extraction; the lookbehind blocks word tails ("valid.",
# "said."). Bare Id. (no pin) additionally passes a sentence-context check.
_ID_PIN = re.compile(
    r"(?<![A-Za-z])(?P<mk>[*_]{0,2})(?P<word>[Ii]d\.)(?P=mk)"
    r"(?:\s+at\s+(?:¶¶?\s*(?P<para_at>\d+(?:\s*[-–]\s*\d+)?)"
    r"|(?P<page>\d+(?:\s*[-–]\s*\d+)?))"
    r"|[,\s]+¶¶?\s*(?P<para>\d+(?:\s*[-–]\s*\d+)?))?"
)

# Sentence-context guard for a bare capitalized "Id.": the preceding
# non-space character must end a sentence or open a parenthetical.
_BARE_ID_PRECEDERS = ".;:!?]("

# A bare lowercase "id." must follow an opening paren or a citation signal.
_LOWER_ID_SIGNALS = ("(", "see", "see, e.g.,", "e.g.,", "cf.", "accord",
                     "citing", "quoting", "compare", "but see")


def _normalize_regional(reporter: str, series: str | None) -> str:
    """Match the full-cite reporter conventions: N.W.3d (no space), So. 3d."""
    if not series:
        return reporter
    if reporter == "So.":
        return f"So. {series}"
    return f"{reporter}{series}"


def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _bare_id_allowed(text: str, start: int, word: str) -> bool:
    prefix = text[max(0, start - 24):start].rstrip(" \t\n*_\"'“”‘’")
    if word.startswith("I"):
        return not prefix or prefix[-1] in _BARE_ID_PRECEDERS
    lowered = prefix.lower()
    return any(lowered.endswith(sig) for sig in _LOWER_ID_SIGNALS)


def _name_ok(name: str) -> bool:
    lowered = name.lower().rstrip(".,")
    if lowered in _NOT_A_NAME or lowered in _SIGNALS:
        return False
    first = name.split()[0].lower().rstrip(".,")
    return first not in _NOT_A_NAME and first not in _SIGNALS and len(first) >= 3


def _pin(raw: str, position: int, *, jurisdiction: str = "", components: dict,
         pin_page: str | None = None, pin_paragraph: str | None = None) -> Citation:
    if pin_paragraph:
        pinpoint = f"¶ {pin_paragraph}"
    elif pin_page:
        pinpoint = f"at {pin_page}"
    else:
        pinpoint = None
    return Citation(
        raw_text=raw,
        cite_type=CitationType.CASE,
        jurisdiction=jurisdiction,
        normalized=_collapse(raw),
        components=components,
        pinpoint=pinpoint,
        position=position,
        is_pin_cite=True,
        pin_page=pin_page,
        pin_paragraph=pin_paragraph,
    )


class PinCiteMatcher(BaseMatcher):
    def find_all(self, text: str) -> list[Citation]:
        results: list[Citation] = []

        # U.S. Reports / S. Ct.
        for pattern, reporter in ((_US_PIN, "U.S."), (_S_CT_PIN, "S. Ct.")):
            for m in pattern.finditer(text):
                results.append(_pin(
                    m.group(0), m.start(), jurisdiction="us",
                    components={"shape": "reporter_pin", "volume": m.group(1),
                                "reporter": reporter},
                    pin_page=m.group(2),
                ))

        # F.2d / F.3d / F.4th
        for m in _FED_PIN.finditer(text):
            results.append(_pin(
                m.group(0), m.start(), jurisdiction="us",
                components={"shape": "reporter_pin", "volume": m.group(1),
                            "reporter": f"F.{m.group(2)}"},
                pin_page=m.group(3),
            ))

        # F. Supp. / F. Supp. 2d / F. Supp. 3d
        for m in _F_SUPP_PIN.finditer(text):
            reporter = f"F. Supp. {m.group(2)}" if m.group(2) else "F. Supp."
            results.append(_pin(
                m.group(0), m.start(), jurisdiction="us",
                components={"shape": "reporter_pin", "volume": m.group(1),
                            "reporter": reporter},
                pin_page=m.group(3),
            ))

        # Regional reporters (series optional — covers first series too)
        for m in _REGIONAL_PIN.finditer(text):
            results.append(_pin(
                m.group(0), m.start(),
                components={"shape": "reporter_pin", "volume": m.group(1),
                            "reporter": _normalize_regional(m.group(2), m.group(3))},
                pin_page=m.group(4),
            ))

        # ND neutral "at ¶" short form
        for m in _ND_AT_PIN.finditer(text):
            results.append(_pin(
                m.group(0), m.start(), jurisdiction="nd",
                components={"shape": "reporter_pin", "year": m.group(1),
                            "number": m.group(2)},
                pin_paragraph=m.group(3),
            ))

        # Id. forms
        for m in _ID_PIN.finditer(text):
            page = m.group("page")
            para = m.group("para_at") or m.group("para")
            if not page and not para and not _bare_id_allowed(text, m.start(), m.group("word")):
                continue
            results.append(_pin(
                m.group(0), m.start(),
                components={"shape": "id"},
                pin_page=page, pin_paragraph=para,
            ))

        # Shape 3 — bare-name candidates. Suppress any that overlap a
        # reporter/Id. candidate above (e.g. the "F.3d at 363" tail of a
        # shape-1 pin would otherwise also parse as a name candidate).
        taken = [(c.position, c.position + len(c.raw_text)) for c in results]

        def overlaps(start: int, end: int) -> bool:
            return any(s < end and start < e for s, e in taken)

        for pattern, group_kind in ((_NAME_AT_PIN, "page"), (_NAME_PARA_PIN, "para")):
            for m in pattern.finditer(text):
                if overlaps(m.start(), m.end()):
                    continue
                name = m.group(1)
                words = name.split()
                if len(words) == 2 and words[0].lower().rstrip(".,") in _SIGNALS:
                    name = words[1]  # "See Goss at 363" → "Goss"
                if not _name_ok(name):
                    continue
                kwargs = {"pin_page": m.group(2)} if group_kind == "page" \
                    else {"pin_paragraph": m.group(2)}
                results.append(_pin(
                    m.group(0), m.start(),
                    components={"shape": "name_pin", "name": name},
                    **kwargs,
                ))

        results.sort(key=lambda c: c.position)
        return results


register(20, PinCiteMatcher())

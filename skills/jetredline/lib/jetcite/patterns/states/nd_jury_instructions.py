"""North Dakota Pattern Jury Instructions.

The Pattern Jury Instruction Commission's civil (C-) and criminal (K-) instructions, cited by
number: "NDJI-Civil C-2.05", "N.D.J.I.—Civil C-74.40", "NDJI C - 2.80", "N.D.J.I. K-7.13",
"Pattern Jury Instruction K 21.10", "NDJI-Civil C-74.25 and C-74.40".

Normalized form (ndlaw ruling, 2026-11-24): ``NDJI-Civil C-2.05`` / ``NDJI-Criminal K-18.01``.
The letter fixes the series. From 2003 opinions also write the current number without its
letter under the series word ("N.D.J.I. Civ. No. 17.05", "NDJI-Civil 50.32"); that is read as
the lettered number. A whole number under the series word ("NDJI-CIVIL 1660", "N.D.J.I.Crim.
No. 2001") is the numbering used before the C-/K- scheme (opinions through 1998) and does not
map onto it, so it is not emitted.

Rules, all from reading the ND opinions (2026-11-24):
  * the name must precede the number in its clause: a bare "C-2.05" is as likely an exhibit;
  * the clause ends at a sentence end, a semicolon, a closing parenthesis or a line break;
  * "Pattern Jury Instruction(s)" without "North Dakota" is another body's set when a
    capitalized word other than a sentence opener stands before it ("Fifth Circuit Pattern
    Jury Instructions Civil 11.22", "South Dakota Pattern Jury Instruction 2.05").

No source URL: the instructions are published through a subscription database.
"""

from __future__ import annotations

import re

from jetcite.models import Citation, CitationType
from jetcite.patterns import register
from jetcite.patterns.base import BaseMatcher

SERIES = {"C": "Civil", "K": "Criminal"}

_DASH = "-–—"
_ANCHOR = re.compile(
    r"(?:N\.?\s?D\.?\s?J\.?\s?I\.?(?![A-Za-z])|(?:North\s+Dakota\s+)?Pattern\s+Jury\s+Instructions?)",
    re.IGNORECASE)
_HEAD = re.compile(
    rf"\s*[{_DASH},]?\s*(?:(?P<word>Civil|Criminal|Civ\.?|Crim\.?)\s*[{_DASH},]?\s*)?(?:No\.?\s*)?",
    re.IGNORECASE)
_NUMBER = re.compile(rf"(?<![A-Za-z0-9])(?P<letter>[CK])\s?[{_DASH}]?\s?(?P<num>\d{{1,3}}\.\d{{1,3}})(?!\d)")
_BARE = re.compile(rf"(?<![\w.{_DASH}])(\d{{1,3}}\.\d{{1,3}})(?![\d.]?\d)")
_STOP = re.compile(r"(?<!\d)\.(?!\d)|\.(?=\s|$)|[;)\n]")
_OPENERS = {"See", "The", "A", "An", "In", "Under", "Our", "Its", "Also", "And", "This", "That", "Cf", "But"}
_FOREIGN = re.compile(r"\b(?!(?:" + "|".join(_OPENERS) + r")\b)[A-Z][A-Za-z]*\W*\s*$")


def _word_letter(word: str | None) -> str | None:
    return {"civ": "C", "cri": "K"}.get((word or "")[:3].lower())


def normalize(letter: str, num: str) -> str:
    letter = letter.upper()
    return f"NDJI-{SERIES[letter]} {letter}-{num}"


class NDJuryInstructionMatcher(BaseMatcher):
    """North Dakota Pattern Jury Instructions cited by number."""

    def find_all(self, text: str) -> list[Citation]:
        out: list[Citation] = []
        seen: set[int] = set()
        for a in _ANCHOR.finditer(text):
            name = a.group(0)
            if name[:1] in "Pp" and _FOREIGN.search(text[max(0, a.start() - 30):a.start()]):
                continue
            h = _HEAD.match(text, a.end())
            wl = _word_letter(h.group("word"))
            base = h.end()
            rest = text[base:base + 160]
            stop = _STOP.search(rest)
            window = rest[:stop.start()] if stop else rest
            hits = []
            for m in _NUMBER.finditer(window):
                letter = m.group("letter").upper()
                if wl and wl != letter:
                    continue          # "NDJI-Civil K-1.10": the series word contradicts the letter
                hits.append((m.start(), m.end(), letter, m.group("num")))
            if wl:
                bares = [m for m in _BARE.finditer(window)
                         if not any(s <= m.start() < e for s, e, *_ in hits)]
                if bares and not window[:bares[0].start()].strip():   # must follow the name directly
                    hits += [(m.start(), m.end(), wl, m.group(1)) for m in bares]
            for i, (s, e, letter, num) in enumerate(sorted(hits)):
                start = a.start() if i == 0 else base + s
                if base + s in seen:
                    continue
                seen.add(base + s)
                out.append(Citation(
                    raw_text=text[start:base + e],
                    cite_type=CitationType.JURY_INSTRUCTION,
                    jurisdiction="nd",
                    normalized=normalize(letter, num),
                    components={"series": SERIES[letter].lower(), "letter": letter,
                                "number": f"{letter}-{num}",
                                "form": "lettered" if text[base + s:base + e][:1].upper() in "CK" else "series-word"},
                    position=start,
                ))
        return out


register(5, NDJuryInstructionMatcher())

"""Recover the case name that governs a citation (its "antecedent name").

Given the character offset of a case citation in text, look backward to recover
the party/caption name immediately preceding it — e.g. "Boedecker v. St. Alexius
Hospital" in "... Boedecker v. St. Alexius Hospital, 298 N.W.2d 372 ...".

This is a *best-effort heuristic* over surrounding prose, not a deterministic
parse: the left boundary of a case name in running text is inherently
ambiguous. Callers must tolerate ``None`` and treat the result as a hint, not a
guarantee. It exists so that a citation to a reporter page shared by more than
one case can be matched back to the right case.
"""

from __future__ import annotations

import re

# How far back from the citation to look for a governing name.
_LOOKBACK = 200

# Lowercase fragments that legitimately appear *inside* a party / caption name.
# Deliberately excludes bare prepositions ("in", "for", "on", "a") that precede
# names rather than belong to them.
_INNER = r"(?:of|the|and|ex\s+rel\.?|on\s+behalf\s+of|&)"

# A single name word: capitalized (incl. abbreviations like St., Co., Hosp.,
# Ass'n, possessives, hyphenated forms, initials).
_WORD = r"[A-Z][A-Za-z0-9.'’\-]*"

# A party: a name word followed by more name words / inner connectives.
_PARTY = rf"{_WORD}(?:\s+(?:{_WORD}|{_INNER}))*"

# Procedural caption prefixes (these stand on their own — no " v. " required).
_PREFIX = (
    r"(?:In\s+re(?:\s+the)?\s+(?:Matter|Estate|Interest|Application|Petition|"
    r"Adoption|Guardianship|Conservatorship|Trust|Will)\s+of\s+"
    r"|In\s+re\s+|In\s+the\s+Matter\s+of\s+|In\s+the\s+Interest\s+of\s+"
    r"|Matter\s+of\s+|Estate\s+of\s+|Interest\s+of\s+|Application\s+of\s+"
    r"|Petition\s+of\s+|Adoption\s+of\s+|Guardianship\s+of\s+)"
)

# Full adversary caption: [prefix?] Party v. Party, anchored to the window end.
_FULL_RE = re.compile(rf"(?P<name>(?:{_PREFIX})?{_PARTY}\s+v\.?\s+{_PARTY})\s*$")

# Procedural caption ending at the window end: "In re X", "Matter of X", ...
_PROC_RE = re.compile(rf"(?P<name>{_PREFIX}{_PARTY})\s*$")

# Short form: a bare party name immediately before the cite ("Boedecker, 298 ...").
_SHORT_RE = re.compile(rf"(?P<name>{_PARTY})\s*$")

# Leading capitalized tokens that are citation signals, not part of the name.
_SIGNALS = frozenset({
    "see", "cf", "cf.", "but", "accord", "also", "compare", "contra",
    "e.g.", "eg", "i.e.", "quoting", "citing", "following", "overruling",
    "affirming", "reversing", "rev'g", "aff'g", "modifying",
})

# Capitalized words that are not case names (reject short-form matches of these).
_NOT_A_NAME = frozenset({
    "id", "id.", "ibid", "ibid.", "see", "cf", "cf.", "but", "accord", "also",
    "compare", "contra", "e.g.", "eg", "i.e.", "the", "this", "it", "we", "in",
    "under", "here", "court", "section", "chapter", "rule", "article", "const",
    "const.", "order", "opinion", "supra", "infra", "ante", "post",
})

_LEAD_SIGNAL_RE = re.compile(
    r"^(?:" + "|".join(re.escape(s) for s in sorted(_SIGNALS, key=len, reverse=True)) + r")\s+",
    re.IGNORECASE,
)


def _clean_window(window: str) -> str:
    """Strip trailing whitespace, markdown/italic markers, and a trailing comma."""
    w = re.sub(r"[*_\s]+$", "", window)
    w = w.rstrip(",")
    w = re.sub(r"[*_\s]+$", "", w)
    return w


def _strip_leading_signals(name: str) -> str:
    """Remove leading citation signal words ("See", "Cf.", "Citing", ...)."""
    prev = None
    while prev != name:
        prev = name
        name = _LEAD_SIGNAL_RE.sub("", name, count=1).lstrip()
    # Drop a dangling leading inner connective ("and"/"the"/"of") if one leaked.
    name = re.sub(r"^(?:and|the|of)\s+", "", name)
    return name.strip()


def extract_antecedent_name(text: str, position: int, start: int | None = None) -> str | None:
    """Return the case name governing the citation at ``position``, or ``None``.

    Looks backward from ``position`` over a bounded window. ``start`` optionally
    clamps the left edge of the window (e.g. to the end of the previous citation)
    so a name belonging to an earlier cite is not picked up.

    Best-effort: prefers a full "X v. Y" caption, then a procedural "In re X"
    caption, then a conservative short-form surname. Returns ``None`` when no
    plausible name is found.
    """
    if position <= 0:
        return None
    left = max(0, position - _LOOKBACK)
    if start is not None:
        left = max(left, start)
    window = _clean_window(text[left:position])
    if not window:
        return None

    m = _FULL_RE.search(window)
    if m:
        name = _strip_leading_signals(m.group("name"))
        if name and " v" in f" {name} ".lower():
            return name

    m = _PROC_RE.search(window)
    if m:
        name = _strip_leading_signals(m.group("name"))
        if name:
            return name

    m = _SHORT_RE.search(window)
    if m:
        name = _strip_leading_signals(m.group("name"))
        # Short form is the least reliable: accept only a 1-2 word proper name
        # that is not a known signal/sentence word.
        words = name.split()
        if 1 <= len(words) <= 2 and name.lower() not in _NOT_A_NAME \
                and words[0].lower() not in _NOT_A_NAME and len(words[0]) >= 3:
            return name

    return None

"""Reader-facing links: the ``ndlaw`` source and ``Citation.link_url``.

Every North Dakota authority ndlaw.org serves gets an ``ndlaw`` source, a
``https://ndlaw.org/cite/...`` resolver link carrying the citation as written
in its canonical form, its pinpoint, and (for a reporter cite) its case name.
The source is appended, never prepended: ``sources[0]`` stays the official,
fetchable URL that consumers fetch from and that ndlaw's own citation graph
records (``text_citations.url``), so nothing downstream of ``sources[0]``
changes with this module.

Which link a reader clicks is a separate question, answered by
``Citation.link_url``: the ``ndlaw`` link when the caller prefers ndlaw.org
and the authority is one the preference covers, the primary URL otherwise.
``link_url`` belongs to the occurrence (its pinpoint included); a consumer
that links every appearance of a citation's text alike (a text -> URL map)
wants ``text_link_url`` instead, which carries a pinpoint only when the
citation's own text does ('N.D.R.Crim.P. 11(b)(1)', not the '¶ 17' that
follows '2019 ND 140').

The preference comes from the ``prefer`` argument of ``scan_text`` /
``lookup``, else the ``JETCITE_PREFER`` environment variable, else
``"official"``:

- ``"official"`` (default): ``link_url`` is the primary URL, as before.
- ``"ndlaw"``: ``link_url`` is the ndlaw.org link for ND opinions, court
  rules, N.D.C.C., and N.D.A.C. citations. The N.D. Constitution keeps its
  ndconst.org link and session laws their ndlegis.gov volume PDF (ndlaw.org
  carries a session law's record, not its text); both still carry an
  ``ndlaw`` source for callers that want it.

A North Western Reporter cite is North Dakota authority only on evidence: a
parallel ND cite, or a court parenthetical ``(N.D. 1994)`` /
``(N.D. Ct. App. 1995)`` after it. Without either it may be any of seven
states' opinion, and ndlaw.org would answer 404, so it gets no ``ndlaw``
source.
"""

from __future__ import annotations

import os
import re

from jetcite.models import Citation, CitationType, Source
from jetcite.sources.ndlaw import ndlaw_cite_url

PREFERENCES = ("official", "ndlaw")
ENV_VAR = "JETCITE_PREFER"

_ND_NEUTRAL = re.compile(r"^\d{4} ND(?: App)? \d+$")
_ND_REPORTER = re.compile(r"^\d+ N\.D\. \d+$")
_NW_REPORTER = re.compile(r"^\d+ N\.W\.(?:2d|3d)? \d+$")
# what may sit between a reporter cite and its court parenthetical: a page
# pin ('612, 616', '612, at 614', '612, 615-16'), then '(N.D. 1994)'
_ND_PAREN = re.compile(
    r"^(?:\s*,\s*(?:at\s+)?\d+(?:\s*[-–]\s*\d+)?)*\s*"
    r"\(\s*N\.\s?D\.(?:\s*Ct\.\s*App\.)?\s*\d{4}\s*\)")
_PREFERRED_TYPES = (CitationType.CASE, CitationType.COURT_RULE,
                    CitationType.STATUTE, CitationType.REGULATION)


def resolve_preference(prefer: str | None) -> str:
    """The effective preference: the argument, else $JETCITE_PREFER, else
    'official'. An unknown value raises rather than silently linking
    somewhere the caller did not ask for."""
    value = prefer if prefer is not None else os.environ.get(ENV_VAR, "")
    value = (value or "official").strip().lower()
    if value not in PREFERENCES:
        raise ValueError(
            f"unknown link preference {value!r} (from "
            f"{'prefer=' if prefer is not None else '$' + ENV_VAR}); "
            f"expected one of {', '.join(PREFERENCES)}")
    return value


def _is_case_nd(c: Citation, text: str | None) -> bool:
    n = c.normalized
    if _ND_NEUTRAL.match(n) or _ND_REPORTER.match(n):
        return True
    if not _NW_REPORTER.match(n):
        return False
    if any(_ND_NEUTRAL.match(p) or _ND_REPORTER.match(p)
           for p in c.parallel_cites):
        return True
    if text is not None:
        end = c.position + len(c.raw_text)
        if _ND_PAREN.match(text[end:end + 80]):
            return True
    return False


def _covered(c: Citation, text: str | None) -> bool:
    """Is ``c`` an authority ndlaw.org serves (full cites only)?"""
    t = c.cite_type
    if t == CitationType.CASE:
        return _is_case_nd(c, text)
    if c.jurisdiction != "nd":
        return False
    n = c.normalized
    if t == CitationType.STATUTE:
        return n.startswith("N.D.C.C.")
    if t == CitationType.REGULATION:
        return n.startswith("N.D.A.C.")
    if t == CitationType.COURT_RULE:
        return not n.lower().startswith("local")     # district local rules
    if t in (CitationType.CONSTITUTION, CitationType.SESSION_LAW):
        return True
    return False


def _pin_suffix(pinpoint: str | None) -> str:
    """The pinpoint as it follows a citation: '¶ 17' -> ', ¶ 17';
    'at 616' -> ', 616'; '(b)(1)' -> '(b)(1)'."""
    if not pinpoint:
        return ""
    p = pinpoint.strip()
    if p.startswith("("):
        return p
    if p.lower().startswith("at "):
        p = p[3:].strip()
    return f", {p}"


def _query(normalized: str, pinpoint: str | None, name: str | None) -> str:
    q = normalized + _pin_suffix(pinpoint)
    # a case name only helps a reporter cite (two opinions can share a first
    # page); a neutral cite is unique on its own
    if name and not _ND_NEUTRAL.match(normalized) and (
            _NW_REPORTER.match(normalized) or _ND_REPORTER.match(normalized)):
        q = f"{name}, {q}"
    return q


def _pin_pinpoint(pin: Citation) -> str | None:
    if pin.pin_paragraph:
        return f"¶ {pin.pin_paragraph}"
    if pin.pin_page:
        return pin.pin_page
    return pin.pinpoint


def apply_links(citations: list[Citation], text: str | None = None,
                prefer: str | None = None) -> list[Citation]:
    """Attach the ``ndlaw`` source and set ``link_url`` on every citation, in
    place; returns ``citations``. ``text`` is the text the citations' positions
    index (for the court-parenthetical test); None skips that test."""
    pref = resolve_preference(prefer)
    covered: dict[str, bool] = {}
    by_norm: dict[str, Citation] = {}
    for c in citations:
        if c.is_pin_cite:
            continue
        by_norm.setdefault(c.normalized, c)
        covered[c.normalized] = covered.get(c.normalized, False) or \
            _covered(c, text)
    # parallel members share their ND status: '1 N.W.2d 335' beside
    # '71 N.D. 363' is North Dakota authority whatever its own context
    for c in citations:
        if not c.is_pin_cite and covered.get(c.normalized):
            for p in c.parallel_cites:
                if p in covered and _NW_REPORTER.match(p):
                    covered[p] = True

    # Two ndlaw links per citation, at two levels:
    # - the ``ndlaw`` SOURCE names the authority (its first occurrence's
    #   citation and case name, no pinpoint), so a repeat or a pin cite
    #   carries exactly its parent's sources, as sources always have;
    # - ``link_url`` names this occurrence, pinpoint included, so
    #   'Id. ¶ 18' opens at ¶ 18.
    for c in citations:
        c.sources = [s for s in c.sources if s.name != "ndlaw"]
        primary = c.sources[0].url if c.sources else None
        if c.is_pin_cite:
            first = by_norm.get(c.parent_normalized or "")
            pin, name = _pin_pinpoint(c), c.antecedent_name
        else:
            first = by_norm.get(c.normalized)
            pin, name = c.pinpoint, c.antecedent_name
        if first is None or not covered.get(first.normalized):
            c.link_url = c.text_link_url = primary
            continue
        authority = ndlaw_cite_url(
            _query(first.normalized, None, first.antecedent_name))
        occurrence = ndlaw_cite_url(
            _query(first.normalized, pin, name or first.antecedent_name))
        # append only behind an official source: an ndlaw link must never
        # become sources[0], the URL consumers fetch and ndlaw records
        if primary is not None:
            c.sources.append(Source("ndlaw", authority))
        if pref == "ndlaw" and first.cite_type in _PREFERRED_TYPES:
            c.link_url = occurrence
            # valid wherever c.raw_text appears: the pinpoint only when the
            # citation's own text carries it ('N.D.R.Crim.P. 11(b)(1)',
            # 'Id. ¶ 18'), never one that follows it ('2019 ND 140, ¶ 17')
            own = _pin_suffix(pin).lstrip(", ")
            c.text_link_url = (occurrence if own and own in c.raw_text
                               else authority)
        else:
            c.link_url = c.text_link_url = primary
    return citations

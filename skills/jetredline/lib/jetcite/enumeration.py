"""Expansion of enumerated citation lists.

A citation that names several provisions under one authority marker —
``N.D.C.C. §§ 11-11-39, 11-11-43, and 28-34-01`` — is written once and read
many times. The pattern modules match only the *anchor* member, because each
of their regexes is built around the authority marker and the marker appears
exactly once. The tail members are bare numbers.

This module walks outward from the anchor and recovers the rest. It is
deliberately a post-match pass rather than a widening of the ~10 anchor
regexes: those carry dense negative lookaheads (``_NOT_STATUTE_NUM`` and
friends) whose whole job is to reject number-shaped text, and loosening each
of them to swallow a list would multiply that risk tenfold and duplicate the
list grammar in every module. Here the grammar is written once and guarded
once.

Two directions are needed, because the pattern modules anchor on the marker
and the marker can sit on either side of the list:

* **Forward** — ``N.D.C.C. §§ 28-27-01 and 28-27-02``. The marker leads, the
  anchor match ends at the first member, and the tail runs to the right.
* **Backward** — ``Rules 50 and 59, N.D.R.Civ.P.`` The marker trails, so the
  pattern matches the *last* member and earlier members run to the left.

Guards, in the order they do work:

1. **Shape congruence.** A member must have the anchor's arity — three
   dash-separated groups for an N.D.C.C. section, four for an N.D.A.C.
   section. Arity does more work than a title check would: in
   ``§§ 11-11-39, 11-11-43, and 28-34-01`` the last member sits in a
   different title from the first, so requiring a shared title would drop it.
2. **Member-or-stop.** After a separator the next text must itself parse as a
   member. Anything else ends the list. This one rule retires a whole family
   of special cases: ``, and N.D.C.C. § 28-27-01`` after a constitutional
   list stops at the marker, ``; *see also*`` stops at the signal,
   ``, et seq.`` stops at ``et``, and ``[UCCJA §§ 7, 8]`` stops at the
   bracket.
3. **Truncated members are restricted.** ND practice sometimes abbreviates a
   tail member to its final group — ``Sections 12.1-23-01, 02``. That form is
   real but rare (about five instances across the 20,102-opinion corpus), and
   a bare one- or two-digit number is exactly what a treatise page or
   reporter volume looks like. It is therefore accepted only for anchors of
   arity three or more, and only when what follows the member is a list
   terminator rather than a capitalized word.
4. **Ranges record endpoints only.** ``§§ 28-27-01 through 28-27-02`` yields
   both endpoints with ``range_end`` set on the first. The interior is never
   interpolated: this library has no inventory of which section numbers
   exist, and in a code with decimal sections the interior is not even
   enumerable.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from jetcite.models import Citation

__all__ = ["EnumSpec", "expand_enumerations"]

# A single group of a dash-separated provision number: "12", "12.1", "01".
_GROUP = r"\d{1,3}(?:\.\d+)?"

# Inter-group separator inside one provision number. Mirrors ``_SEP`` in the
# ND pattern module: a real dash from the Unicode dash family, optionally
# spaced, so a number the court's PDF wraps across a line still parses.
_NUM_SEP = r"\s*[-‐‑‒–—―−]\s*"

# Separator BETWEEN members of a list. Semicolons are included because the
# administrative code cites that way in practice —
# ``N.D.A.C. §§ 59.5-03-03-02(1); 4-07-19-02(1)`` — and the member-or-stop
# rule is what keeps a semicolon from running past the end of a string cite
# into the next authority. "or" appears in rule lists ("Rules 12 or 56").
_LIST_SEP = re.compile(
    r"""
    \s*
    (?:
        [,;&]\s*(?:and/or\s+|and\s+|or\s+)?   # ", " / "; " / "& " / ", and "
      | \s(?:and/or|and|or)\s                 # bare " and " / " or "
    )
    """,
    re.VERBOSE,
)

# Range connector between two endpoints. Only the spelled connectors are
# honoured: a bare dash between two provision numbers is indistinguishable
# from the dash *inside* one ("55-4401-55-4426" is either a range of two
# four-group numbers or one eight-group number), and in prose it is also how
# page spans and date spans are written.
_RANGE_WORD = re.compile(r"\s*(?:through|thru|to)\s*", re.IGNORECASE)

# A subdivision suffix carried by a member: "(2)", "(a)", "(2)(f)", "(a-d)".
# Each group is kept short and free of internal periods so that a trailing
# parenthetical which is NOT a subdivision stays outside the citation's span:
# a year ("416(l) (1994)") and a uniform-act note ("30.1-20-09 (U.P.C.3-909)")
# would otherwise be absorbed, which does not change the normalized cite but
# does widen raw_text — and raw_text is what a consumer hyperlinks.
_SUBDIV = r"(?:\s*\([A-Za-z0-9]{1,3}(?:[-–][A-Za-z0-9]{1,3})?\))*"

# What may legitimately follow a *truncated* member. A truncated member is a
# bare one- or two-digit number, which is also what a reporter volume, a page,
# and a year look like, so the text after it has to close the list rather than
# start something new. The code-attribution branch demands the Century Code or
# Administrative Code marker specifically ("02, N.D.C.C.") and not a bare
# "N.D.", which would let the reporter in "§§ 12-1-1, 5 N.D. 3" pose as a
# member. A bracket is allowed because a bracketed parallel cite is how the
# corpus closes such a list: "§§ 14-14-07, 08 [UCCJA §§ 7, 8]".
_TRUNC_TERMINATOR = re.compile(
    r"\s*(?:[,;.&)\]\[—-]|$|and\b|or\b|of\b|N\.?\s*D\.?\s*[CA])", re.IGNORECASE
)


@dataclass(frozen=True)
class EnumSpec:
    """How to expand one family of citations.

    ``arity``
        Number of dash-separated groups in a provision number of this family.
    ``build``
        Callback ``(anchor, groups, raw_text, position) -> Citation | None``
        that the owning pattern module supplies. Keeping construction with the
        module that owns the family means URL building, normalization, and
        component naming stay in exactly one place. The anchor is passed so a
        member can inherit context the list states only once — a
        constitutional article, for instance, in "art. VI, §§ 2 and 6".
    ``groups_of``
        Callback returning the anchor's provision number as a list of groups,
        or None if this anchor is not of the family. Reading the number from
        the owning module rather than sniffing ``components`` keeps the
        constitution honest: there the article is Roman and is *not* part of
        the enumerable number, so "art. VI, §§ 2 and 6" is an arity-1 list
        whose members inherit the article.
    ``allow_truncated``
        Whether a tail member may abbreviate to its final group. Only true
        for the dash-numbered codes.
    ``group_re``
        Grammar for one group of this family's provision number. Defaults to
        the dash-numbered code shape; U.S.C. overrides it because its sections
        run to four digits with an optional letter suffix ("1981a").
    ``plural_required``
        Whether expansion requires the anchor to have used a plural marker
        (``§§``, ``Sections``, ``chs.``, ``Rules``). True for everything
        except the rule families, where "Rules 50 and 59" is the plural form
        and the marker itself is the rule-set name.
    """

    arity: int
    build: Callable[[Citation, list[str], str, int], Citation | None]
    groups_of: Callable[[Citation], list[str] | None]
    allow_truncated: bool = False
    plural_required: bool = True
    group_re: str = _GROUP


def _member_re(arity: int, group_re: str = _GROUP) -> re.Pattern:
    """Regex for a full member of the given arity, plus optional subdivision."""
    body = group_re + (_NUM_SEP + group_re) * (arity - 1)
    # Reject a longer number: "28-27-01" must not match inside "28-27-01-05".
    return re.compile(rf"({body}){_SUBDIV}(?!{_NUM_SEP}\d)")


def _truncated_re(group_re: str = _GROUP) -> re.Pattern:
    """Regex for an abbreviated tail member — a single trailing group."""
    return re.compile(rf"({group_re}){_SUBDIV}(?!{_NUM_SEP}\d)")


def _split_groups(number: str) -> list[str]:
    return [g.strip() for g in re.split(_NUM_SEP, number) if g.strip()]


def _has_plural_marker(text: str, anchor_start: int) -> bool:
    """Did the anchor's marker use a plural form?

    Looks back a short distance from the anchor for ``§§``, ``Sections``,
    ``Secs.``, ``chs.``, ``Rules``, or ``Articles``. Bluebook R3.3 requires
    the doubled symbol for multiple sections, which makes the plural marker a
    reliable signal in drafted legal text and its absence a reliable stop.
    """
    window = text[max(0, anchor_start - 40) : anchor_start + 40]
    return bool(
        re.search(
            r"§§|\b(?:Sections|Secs?s\.|Secs\.|chs\.|Chs\.|Rules|Articles|Arts\.)",
            window,
            re.IGNORECASE,
        )
    )


def _scan_forward(
    text: str, start: int, spec: EnumSpec, anchor_groups: list[str]
) -> list[tuple[list[str], int, int]]:
    """Collect members appearing to the right of ``start``.

    Returns ``(groups, span_start, span_end)`` per member, in document order.
    """
    member_re = _member_re(spec.arity, spec.group_re)
    trunc_re = _truncated_re(spec.group_re)
    out: list[tuple[list[str], int, int]] = []
    pos = start
    prev_groups = anchor_groups

    while True:
        sep = _LIST_SEP.match(text, pos)
        if not sep:
            break
        after = sep.end()

        m = member_re.match(text, after)
        if m:
            groups = _split_groups(m.group(1))
            if len(groups) != spec.arity:
                break
            out.append((groups, m.start(1), m.end()))
            prev_groups = groups
            pos = m.end()
            continue

        if spec.allow_truncated and spec.arity >= 3:
            t = trunc_re.match(text, after)
            if t and _TRUNC_TERMINATOR.match(text, t.end()):
                tail = _split_groups(t.group(1))
                if len(tail) == 1:
                    groups = prev_groups[: spec.arity - 1] + tail
                    out.append((groups, t.start(1), t.end()))
                    prev_groups = groups
                    pos = t.end()
                    continue
        break

    return out


def _scan_backward(
    text: str, end: int, spec: EnumSpec
) -> list[tuple[list[str], int, int]]:
    """Collect members appearing to the left of ``end``.

    Used for trailing-marker forms such as ``Rules 50 and 59, N.D.R.Civ.P.``,
    where the pattern module matches the member nearest the marker and the
    earlier members of the list run leftward.
    """
    member_re = _member_re(spec.arity, spec.group_re)
    out: list[tuple[list[str], int, int]] = []
    pos = end

    while True:
        head = text[:pos]
        # The separator must sit flush against the text we have consumed.
        sep = None
        for m in _LIST_SEP.finditer(head):
            if m.end() == pos:
                sep = m
        if sep is None:
            break

        # Find a member ending exactly where the separator begins.
        candidate = None
        for m in member_re.finditer(text[: sep.start()]):
            if m.end() == sep.start():
                candidate = m
        if candidate is None:
            break
        groups = _split_groups(candidate.group(1))
        if len(groups) != spec.arity:
            break
        out.append((groups, candidate.start(1), candidate.end()))
        pos = candidate.start(1)

    out.reverse()
    return out


def expand_enumerations(
    text: str,
    citations: list[Citation],
    spec: EnumSpec,
    *,
    match_end: Callable[[Citation], int] | None = None,
) -> list[Citation]:
    """Return citations expanded from enumerated lists anchored on ``citations``.

    ``citations`` are the anchor matches already produced by a pattern module;
    the return value contains only the *additional* members, each built via
    ``spec.build`` and tagged in ``components`` with ``enumerated=True`` and
    ``enumerated_from`` naming the anchor. Callers append the result to their
    own list.
    """
    added: list[Citation] = []
    seen: set[tuple[str, int]] = set()

    for anchor in citations:
        groups = spec.groups_of(anchor)
        if groups is None or len(groups) != spec.arity:
            continue
        if spec.plural_required and not _has_plural_marker(text, anchor.position):
            continue

        # Scan from the end of the anchor's NUMBER, not the end of its match:
        # the anchor patterns consume a trailing boundary character, and that
        # character is usually the list's first separator.
        span = _number_span(text, anchor, groups)
        if span is None:
            end = match_end(anchor) if match_end else anchor.position + len(anchor.raw_text)
            num_start = None
        else:
            num_start, end = span
        # The anchor's own match may stop before a subdivision the text
        # carries ("§§ 59.5-03-03-02(1); 4-07-19-02(1)"), which would leave
        # the scan starting on "(" and miss the separator behind it.
        end = _skip_subdivisions(text, end)
        members = _scan_forward(text, end, spec, groups)

        # Trailing-marker forms ("Rules 50 and 59, N.D.R.Civ.P.") put the
        # anchor at the END of the list, so the earlier members run leftward.
        # Leading forms yield nothing here, since no separator abuts the
        # number's left edge.
        if num_start is not None:
            members = _scan_backward(text, num_start, spec) + members

        for mgroups, mstart, mend in members:
            key = ("-".join(mgroups), mstart)
            if key in seen:
                continue
            seen.add(key)
            cite = spec.build(anchor, mgroups, text[mstart:mend], mstart)
            if cite is None:
                continue
            if cite.normalized == anchor.normalized:
                continue
            cite.components = dict(cite.components)
            cite.components["enumerated"] = True
            cite.components["enumerated_from"] = anchor.normalized
            added.append(cite)

            rng = _range_after(text, mend, spec)
            if rng is not None:
                rgroups, rstart, rend = rng
                cite.components["range_end"] = "-".join(rgroups)
                rkey = ("-".join(rgroups), rstart)
                if rkey not in seen:
                    seen.add(rkey)
                    endpoint = spec.build(anchor, rgroups, text[rstart:rend], rstart)
                    if endpoint is not None and endpoint.normalized != anchor.normalized:
                        endpoint.components = dict(endpoint.components)
                        endpoint.components["enumerated"] = True
                        endpoint.components["enumerated_from"] = anchor.normalized
                        endpoint.components["range_start"] = "-".join(mgroups)
                        added.append(endpoint)

        # A range attached directly to the anchor: "§§ 28-27-01 through 28-27-02".
        rng = _range_after(text, end, spec)
        if rng is not None:
            rgroups, rstart, rend = rng
            key = ("-".join(rgroups), rstart)
            if key not in seen:
                seen.add(key)
                endpoint = spec.build(anchor, rgroups, text[rstart:rend], rstart)
                if endpoint is not None and endpoint.normalized != anchor.normalized:
                    anchor.components = dict(anchor.components)
                    anchor.components["range_end"] = "-".join(rgroups)
                    endpoint.components = dict(endpoint.components)
                    endpoint.components["enumerated"] = True
                    endpoint.components["enumerated_from"] = anchor.normalized
                    endpoint.components["range_start"] = "-".join(groups)
                    added.append(endpoint)

    return added


def _range_after(
    text: str, pos: int, spec: EnumSpec
) -> tuple[list[str], int, int] | None:
    """A range connector plus endpoint immediately following ``pos``."""
    member_re = _member_re(spec.arity, spec.group_re)
    m = _RANGE_WORD.match(text, pos)
    if not m:
        return None
    e = member_re.match(text, m.end())
    if not e:
        return None
    groups = _split_groups(e.group(1))
    if len(groups) != spec.arity:
        return None
    return groups, e.start(1), e.end()


def _skip_subdivisions(text: str, pos: int) -> int:
    """Advance past any subdivision suffix sitting at ``pos``."""
    m = re.compile(_SUBDIV).match(text, pos)
    return m.end() if m else pos


def _number_span(
    text: str, cite: Citation, groups: list[str]
) -> tuple[int, int] | None:
    """Offsets of the anchor's provision number within its own match.

    Located by the number's *known* group values rather than by re-running a
    generic member regex, which would otherwise fasten onto the wrong digits:
    in "42 U.S.C. § 1983" a bare arity-1 number pattern matches the title 42,
    not the section. The last occurrence is taken so a trailing-marker form
    ("59, N.D.R.Civ.P.") resolves to the number and not to a digit inside the
    marker.
    """
    body = _NUM_SEP.join(re.escape(g) for g in groups)
    pat = re.compile(rf"{body}{_SUBDIV}")
    span = text[cite.position : cite.position + len(cite.raw_text)]
    last = None
    for m in pat.finditer(span):
        last = m
    if last is None:
        return None
    return cite.position + last.start(), cite.position + last.end()

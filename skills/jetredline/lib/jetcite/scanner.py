"""Batch document scanning for citations."""

from __future__ import annotations

import re
from pathlib import Path

from jetcite.casename import extract_antecedent_name
from jetcite.cleanup import preprocess_document_text
from jetcite.models import Citation, CitationType
from jetcite.patterns import get_matchers
from jetcite.resolver import resolve_nd_opinion_urls


_ND_NEUTRAL_NORM = re.compile(r"^[12]\d{3} ND(?: App)? \d{1,3}$")
# A page pin cite trailing a reporter cite: ", 360" / ", 360-62" / ", 360, 365".
_TRAILING_PAGE_PIN = re.compile(r"^\s*,\s*\d+(?:\s*[-–]\s*\d+)?")

# A full cite's own trailing page pin: "259 N.W.2d 621, 627 (N.D. 1977)",
# with an optional footnote ("501 N.W.2d 739, 744 n.3" / "nn.3-4"). The
# letter lookahead refuses ", 627 N.W.2d" and ", 627 U.S." — a number
# followed by letters (or §) is the next citation's volume or a statute, not
# a pin; the footnote alternative is matched before that lookahead applies.
# The (?![0-9]) digit boundary keeps the engine from backtracking a blocked
# "627" down to "62" to dodge that lookahead.
_TRAILING_FULL_CITE_PIN = re.compile(
    r"^\s*,\s*(\d+(?:\s*[-–]\s*\d+)?"
    r"(?:\s*nn?\.\s*\d+(?:\s*[-–]\s*\d+)?)?)(?![0-9])(?!\s*[A-Za-z§])")


def _capture_trailing_page_pins(citations: list[Citation], text: str) -> None:
    """Attach trailing page pins to full case cites lacking a pinpoint.

    Reporter matchers capture only "vol reporter page"; the pin in
    ``259 N.W.2d 621, 627 (N.D. 1977)`` was previously lost, so consumers
    could not open the source at the cited page the way short forms
    (``id. at 627``, carrying pin_page) allow. Reads the text *after* each
    cite — same statute as _flag_improper_parallel_pincite: no existing
    match, raw_text, or offset changes. Stored as ``pinpoint = "at 627"``,
    matching the pin-cite pinpoint style. Multi-page pins ("627, 630") keep
    their first page; ¶-pinned cites (neutral form) already carry a pinpoint
    and are left alone.
    """
    for c in citations:
        if c.cite_type != CitationType.CASE or c.is_pin_cite or c.pinpoint:
            continue
        after = text[c.position + len(c.raw_text):]
        m = _TRAILING_FULL_CITE_PIN.match(after)
        if m:
            c.pinpoint = f"at {m.group(1)}"


def _flag_improper_parallel_pincite(cite_a: Citation, cite_b: Citation,
                                    text: str) -> None:
    """Flag a page pin cite on the reporter half of a ND public-domain pair.

    Per the ND Supreme Court's Redbook supplement, a full public-domain cite
    gives the North Western Reporter's *first page only* — the ¶ carries the
    pinpoint — so ``1997 ND 231, ¶ 10, 571 N.W.2d 358, 360`` is improper and
    ``…, 571 N.W.2d 358`` is correct.

    Scoped to ND pairs: other states' medium-neutral conventions are not
    jetcite's to assert. Detection reads the text *after* the reporter cite
    rather than widening the reporter pattern, so no existing match, raw_text,
    or offset changes.
    """
    # Orientation: the ND neutral cite leads, its reporter parallel follows.
    # Keying on cite_a's normalized form (not jurisdiction) is deliberate —
    # regional reporters carry jurisdiction "us", so N.W.2d halves of a ND pair
    # would otherwise never qualify.
    if not _ND_NEUTRAL_NORM.match(cite_a.normalized):
        return
    if _ND_NEUTRAL_NORM.match(cite_b.normalized):
        return  # two neutral cites — not a reporter parallel
    after = text[cite_b.position + len(cite_b.raw_text):]
    if _TRAILING_PAGE_PIN.match(after):
        cite_b.improper_parallel_pincite = True


def _separator_verdict(text: str, cite_a: Citation, cite_b: Citation) -> str | None:
    """Classify the gap between two adjacent case cites.

    Returns ``"parallel"`` when the gap is a parallel-cite separator — a comma
    with at most a pinpoint after it, as in ``2024 ND 156, ¶ 12, 10 N.W.3d
    500`` — ``"suspected"`` when the gap would qualify but for a semicolon in
    it, and ``None`` when the two cites are unrelated.

    The semicolon is the Bluebook separator between *different* authorities,
    so a pair written across one is not linked. It is not discarded either:
    pre-1960 opinions used a semicolon where modern form uses a comma
    (``State v. Albertson, 20 N.D. 512; 128 N.W. 1122``), and the "suspected"
    verdict is how that reaches the caller — recorded, never asserted.
    """
    between = text[cite_a.position + len(cite_a.raw_text):cite_b.position]
    stripped = between.strip()

    # Must be a short separator — a comma or semicolon, or a pinpoint between
    # two of them
    if not stripped:
        return None

    # The separator should be short (under ~40 chars) and start with , or ;
    # or be just whitespace around a pinpoint
    if len(stripped) > 40:
        return None
    if not stripped.startswith((",", ";")):
        return None

    # Should not contain sentence-ending punctuation or text that indicates
    # a new thought (period, "see", "and", etc.)
    # Strip separators from both ends: a trailing comma belongs to the
    # following citation, not to the pinpoint, and would otherwise fail
    # the $-anchored pinpoint test below (", 691," -> "691," -> no match).
    inner = stripped.strip(",;").strip()
    if any(sep in inner.lower() for sep in (".", "see ", "and ", "but ", "cf.")):
        return None

    # Valid inner: empty, or just a pinpoint like "¶ 12" or "at 128"
    if inner and not _looks_like_pinpoint_or_empty(inner):
        return None

    # A semicolon anywhere in the gap — leading ("; 128 N.W. 1122") or after a
    # pin (", 196; 114 P.2d 569") — is the source's own signal that these are
    # separate authorities. The pin-cite antecedent logic already reads it that
    # way (see ambiguous_string_cite); this keeps the two halves of the scanner
    # consistent. Measured over 2,500 opinions of the ndlaw corpus, 7 of 11,224
    # links crossed a semicolon: 6 were genuine parallels (5 of them pre-1960)
    # and 1 joined two different cases. The trade is deliberate — a false
    # parallel group misplaces a consumer's badge on a live draft, while the 6
    # are preserved as suspected rather than lost.
    return "suspected" if ";" in stripped else "parallel"


def _detect_parallel_citations(citations: list[Citation], text: str) -> None:
    """Detect parallel citations and link them.

    When two case citations appear close together in text separated by a comma
    (e.g., "2024 ND 156, 10 N.W.3d 500"), they refer to the same case. This
    function links them by populating each citation's parallel_cites list and
    merging their sources. A pair separated by a semicolon instead is recorded
    in suspected_parallel_cites and otherwise left alone — no link, no merged
    sources, no inherited case name.
    """
    case_cites = [c for c in citations if c.cite_type == CitationType.CASE]

    for cite_a, cite_b in zip(case_cites, case_cites[1:]):
        verdict = _separator_verdict(text, cite_a, cite_b)

        if verdict is None:
            continue

        if verdict == "suspected":
            if cite_b.normalized not in cite_a.suspected_parallel_cites:
                cite_a.suspected_parallel_cites.append(cite_b.normalized)
            if cite_a.normalized not in cite_b.suspected_parallel_cites:
                cite_b.suspected_parallel_cites.append(cite_a.normalized)
            continue

        # Link them
        if cite_b.normalized not in cite_a.parallel_cites:
            cite_a.parallel_cites.append(cite_b.normalized)
        if cite_a.normalized not in cite_b.parallel_cites:
            cite_b.parallel_cites.append(cite_a.normalized)

        _flag_improper_parallel_pincite(cite_a, cite_b, text)

        # Merge sources: each citation gets the other's sources it doesn't have
        a_source_names = {s.name for s in cite_a.sources}
        b_source_names = {s.name for s in cite_b.sources}
        for src in cite_b.sources:
            if src.name not in a_source_names:
                cite_a.sources.append(src)
        for src in cite_a.sources:
            if src.name not in b_source_names:
                cite_b.sources.append(src)


def _detect_antecedent_names(citations: list[Citation], text: str) -> None:
    """Attach the governing case name to each CASE citation (best-effort).

    For each case citation, look backward from its position (clamped to the end
    of the previous citation so a name belonging to an earlier cite is not
    captured) and record the preceding party/caption name. A citation in a
    parallel group with no name of its own inherits the name from a parallel
    that has one — handles "Name, <neutral>, <reporter>" where the name precedes
    only the first cite.
    """
    case_cites = [c for c in citations if c.cite_type == CitationType.CASE]
    prev_end = 0
    for cite in case_cites:
        cite.antecedent_name = extract_antecedent_name(text, cite.position, start=prev_end)
        prev_end = cite.position + len(cite.raw_text)

    by_norm = {c.normalized: c for c in case_cites}
    for cite in case_cites:
        if cite.antecedent_name or not cite.parallel_cites:
            continue
        for pc in cite.parallel_cites:
            other = by_norm.get(pc)
            if other and other.antecedent_name:
                cite.antecedent_name = other.antecedent_name
                break


def _looks_like_pinpoint_or_empty(s: str) -> bool:
    """Check if a string looks like a pinpoint reference or is trivially empty."""
    import re
    # Match: ¶ 12, ¶¶ 12-15, at 128, 128, at ¶ 12, or nothing meaningful
    return bool(re.match(
        r'^(?:at\s+)?(?:¶¶?\s*)?\d+(?:\s*[-–]\s*\d+)?$',
        s.strip(),
    ))


def _name_keys(name: str) -> set[str]:
    """Lookup keys for a full cite's antecedent name (lowercased).

    Keys: the whole name, then for each party (either side of " v. ") the
    party itself plus its first and last words when they are plausible
    surnames (≥3 chars). "Goss Int'l Corp. v. Man Roland" answers to
    "goss"; the second party matters for criminal captions — the Bluebook
    short form of "State v. Gonzalez" is "Gonzalez" — and individual
    parties shorten to the surname, i.e. the last word ("LaNora R.
    Himmerick" → "himmerick"). False-positive control stays on the pin
    side: a candidate must already look like a name and carry explicit
    pin syntax before these keys are ever consulted.
    """
    import re
    keys = {name.lower()}
    for party in re.split(r"\s+v\.?\s", name, maxsplit=1):
        party = party.strip().rstrip(",.")
        if not party:
            continue
        keys.add(party.lower())
        words = party.split()
        for word in (words[0], words[-1]):
            word = word.rstrip(".,").lower()
            if len(word) >= 3:
                keys.add(word)
    return keys


def _link_pin(pin: Citation, parent: Citation) -> None:
    """Attach a resolved parent to a pin cite."""
    pin.parent_normalized = parent.parent_normalized or parent.normalized
    if parent.jurisdiction:
        pin.jurisdiction = parent.jurisdiction
    if not pin.antecedent_name:
        pin.antecedent_name = parent.antecedent_name
    # Transitive: a pin chained through another pin records the ultimate
    # full cite's position, so source inheritance reaches the real parent.
    pin.components["parent_position"] = parent.components.get(
        "parent_position", parent.position)


_PARA_PINPOINT_RE = re.compile(r"¶¶?\s*(\d+(?:\s*[-–]\s*\d+)?)")
_PAGE_PINPOINT_RE = re.compile(r"(?:^|at\s+)(\d+(?:\s*[-–]\s*\d+)?)")

# What may sit between a bare "Rule 60(b)" and a trailing rule-set marker:
# a subdivision chain, commas/space, an optional "of the". Anything more
# ("Rule 12 and N.D.R.Ev. 403") rejects trailing attribution.
# (Ported from ndcourts-mcp notes.py.)
#
# The chain repeats. _RULE_PIN normally swallows an unspaced chain into the
# candidate itself, but a brief that spaces the subdivision off the number —
# "Rule 32 (a)(8)(A) of the North Dakota Rules of Appellate Procedure" —
# leaves the whole chain sitting in this gap, and one optional parenthetical
# rejected it. The ladder then fell through to the nearest PRECEDING marker
# and attributed Rule 32 to whichever set was mentioned earlier.
_RULE_TRAILING_GAP_RE = re.compile(
    r"[\s,]*(?:\([^)]{1,20}\))*[\s,]*(?:of\s+the\s+)?$"
)


def _split_rule_normalized(normalized: str) -> tuple[str, str] | None:
    """Split a full rule cite's normalized form into (set_prefix, number).

    "N.D.R.Civ.P. 60" → ("N.D.R.Civ.P.", "60"); a federal form's trailing
    subsection is stripped ("Fed. R. Civ. P. 12(b)(6)" → number "12").
    Non-numeric rule identifiers (Student Practice roman numerals, Judicial
    Conduct canons) return None — bare "Rule N" short forms are numeric.
    """
    parts = normalized.rsplit(" ", 1)
    if len(parts) != 2:
        return None
    number = re.sub(r"\(.*$", "", parts[1])
    if not re.fullmatch(r"\d{1,4}(?:\.\d{1,2}){0,2}", number):
        return None
    return parts[0], number


def _inherit_pinpoint(pin: Citation, antecedent: Citation) -> None:
    """A bare Id. adopts the antecedent's pinpoint.

    Bluebook: "Id." with no pinpoint of its own means the same authority
    at the same page or paragraph as the immediately preceding citation
    ("2024 ND 4, ¶ 6 ... Id." pins ¶ 6). The inherited pinpoint is marked
    in components so verification can distinguish it from one the drafter
    wrote out.
    """
    if pin.pin_page or pin.pin_paragraph:
        return
    if antecedent.is_pin_cite:
        para, page = antecedent.pin_paragraph, antecedent.pin_page
    elif antecedent.cite_type != CitationType.CASE:
        # Rule/statute/constitution pinpoints are subdivisions ("(b)"),
        # not pages or paragraphs — nothing to inherit under Id.'s
        # page/¶ semantics.
        return
    else:
        para = page = None
        pp = antecedent.pinpoint or ""
        m = _PARA_PINPOINT_RE.search(pp)
        if m:
            para = m.group(1)
        else:
            m = _PAGE_PINPOINT_RE.search(pp.strip())
            if m:
                page = m.group(1)
    if para:
        pin.pin_paragraph = para
        pin.pinpoint = f"¶ {para}"
    elif page:
        pin.pin_page = page
        pin.pinpoint = f"at {page}"
    if para or page:
        pin.components["pinpoint_inherited"] = True


# Curly double quotes. Straight quotes are deliberately not paired: without
# the open/close distinction a single stray mark inverts every span after it.
_QUOTE_OPEN = "“"   # “
_QUOTE_CLOSE = "”"  # ”


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    """Spans of double-quoted matter, sorted by position.

    A citation inside quoted text is part of the quotation, not a citation
    by the author — it must not capture a following ``Id.`` (Bluebook: id.
    tracks the author's own citation sequence; quoted citations are why
    "(citations omitted)" exists).

    Pairing is per line: extract_text.py emits one paragraph per line, and
    the Bluebook multi-paragraph quotation convention re-opens each
    paragraph with ``“`` while closing only the last — so an opening quote
    with no close before the line break extends its span to the line end.
    A ``“`` inside an open span and a stray ``”`` with no open are ignored.

    Known gap: indented block quotes carry no quotation marks and survive
    extraction as plain text, so they are invisible here. The page-pin type
    guard in _resolve_pin_cites covers part of that; full coverage needs
    blockquote markers from extract_text.
    """
    spans: list[tuple[int, int]] = []
    open_pos: int | None = None
    for i, ch in enumerate(text):
        if ch == "\n":
            if open_pos is not None:
                spans.append((open_pos, i))
                open_pos = None
        elif ch == _QUOTE_OPEN:
            if open_pos is None:
                open_pos = i
        elif ch == _QUOTE_CLOSE:
            if open_pos is not None:
                spans.append((open_pos, i + 1))
                open_pos = None
    if open_pos is not None:
        spans.append((open_pos, len(text)))
    return spans


def _resolve_pin_cites(
    pin_candidates: list[Citation],
    citations: list[Citation],
    text: str,
) -> list[Citation]:
    """Link pin-cite candidates to their parent full cites.

    Resolution by shape (components["shape"]):
      reporter_pin — nearest preceding full cite with the same volume+reporter
        (or, for neutral "at ¶" pins, the same normalized form). No antecedent
        → kept with parent_normalized=None: explicit pin syntax with nothing
        to point at is a brief-writing error worth surfacing.
      name_pin — nearest preceding full cite whose antecedent name matches.
        No match → dropped entirely; this is the false-positive control that
        kills prose like "argued at 363".
      id — the nearest preceding citation (full or already-resolved pin),
        resolved transitively. Kept unresolved when the antecedent is an
        ambiguous string cite; a bare "Id." with no antecedent at all is
        dropped as noise.
      rule_pin — bare "Rule 60(b)" attributed to a rule set by the marker
        ladder (see _resolve_rule_pin); unattributable candidates are
        dropped, matching the bare-name doctrine.
    """
    if not pin_candidates:
        return []

    # Overlap suppression uses emitted spans only: a pin candidate sitting
    # inside a shadow re-citation IS that occurrence's pin representation
    # (e.g. the "at ¶" form of a deduped repeat) and must survive.
    full_spans = [(c.position, c.position + len(c.raw_text)) for c in citations
                  if not c.components.get("_shadow")]
    case_cites = [c for c in citations if c.cite_type == CitationType.CASE]
    # Id. can point at any authority — Bluebook sanctions it for rules,
    # statutes, regulations, and constitutions, not just cases. Reporter
    # and name pins stay case-only: their anchors (volume+reporter, party
    # name) are inherently case-shaped.
    id_antecedents = list(citations)

    # Quoted-matter spans and authority types, for the id-branch guards.
    _qspans = _quoted_spans(text)

    def _in_quote(pos: int) -> bool:
        for s, e in _qspans:
            if s <= pos < e:
                return True
            if s > pos:
                break
        return False

    norm_type = {c.normalized: c.cite_type for c in citations}

    by_vol_rep: dict[tuple[str, str], list[Citation]] = {}
    by_norm: dict[str, list[Citation]] = {}
    by_name: dict[str, list[Citation]] = {}
    for c in case_cites:
        comp = c.components
        if "volume" in comp and "reporter" in comp:
            by_vol_rep.setdefault((comp["volume"], comp["reporter"]), []).append(c)
        by_norm.setdefault(c.normalized, []).append(c)
        if c.antecedent_name:
            for key in _name_keys(c.antecedent_name):
                by_name.setdefault(key, []).append(c)

    def nearest_preceding(cands: list[Citation], pos: int) -> Citation | None:
        best = None
        for c in cands:
            if c.position < pos and (best is None or c.position > best.position):
                best = c
        return best

    def _is_neutral(c: Citation) -> bool:
        comp = c.components
        return "year" in comp and "number" in comp and "reporter" not in comp

    def parallel_member_for(pin: Citation, parent: Citation, pos: int) -> Citation:
        """Pick the parallel-group member whose pagination matches the pin.

        A parallel pair ("2024 ND 4, ¶ 6, 1 N.W.3d 919") is one authority,
        but the textually nearest member is the trailing reporter cite —
        linking there hands the pin the reporter's sources instead of the
        primary's. Bare Id. and ¶ pins are anchored in the medium-neutral
        (or U.S. Reports) pagination, so they prefer that member; page pins
        ("Id. at 921") reference reporter pagination, so they prefer a
        reporter member (U.S. Reports first for SCOTUS pairs). Falls back
        to the originally resolved parent.
        """
        if parent.cite_type != CitationType.CASE or not parent.parallel_cites:
            return parent
        members = [parent]
        for norm in parent.parallel_cites:
            m = nearest_preceding(by_norm.get(norm, []), pos)
            if m is not None:
                members.append(m)
        if pin.pin_page:
            pool = [m for m in members if not _is_neutral(m)]
            pool.sort(key=lambda m: 0 if m.components.get("reporter") == "U.S." else 1)
        else:  # bare Id. or ¶ pin
            pool = [m for m in members
                    if _is_neutral(m) or m.components.get("reporter") == "U.S."]
            pool.sort(key=lambda m: 0 if _is_neutral(m) else 1)
        return pool[0] if pool else parent

    def ambiguous_string_cite(nearest: Citation, pos: int,
                              pool: list[Citation]) -> bool:
        """True when the citation preceding ``pos`` sits in a string cite, so
        an Id. reference to it is ambiguous. Parallel pairs are one authority,
        not ambiguous."""
        second = None
        for c in pool:
            if c is nearest or c.position >= pos:
                continue
            if second is None or c.position > second.position:
                second = c
        if second is None:
            return False
        if second.normalized in nearest.parallel_cites:
            return False
        import re
        between = text[second.position + len(second.raw_text):nearest.position]
        stripped = between.strip()
        # Skip a court/date parenthetical attached to the earlier cite:
        # "A v. B, 1 N.W.2d 1 (N.D. 1941); C v. D, ..." is still a string cite.
        stripped = re.sub(r"^\([^)]{0,60}\)\s*", "", stripped)
        # A semicolon separator between two non-parallel cites within ~80
        # chars is a string cite. (No sentence-end check: case names like
        # "C v. D" put periods inside the separator legitimately.)
        return stripped.startswith(";") and len(stripped) <= 80

    # Rule-pin attribution state, built only when rule_pin candidates exist
    # (rule_set_markers scans the whole text).
    rule_markers: list[tuple[int, int, str]] | None = None
    rule_fulls: dict[tuple[str, str], list[Citation]] = {}
    sets_by_number: dict[str, set[str]] = {}
    if any(p.components.get("shape") == "rule_pin" for p in pin_candidates):
        from jetcite.patterns.states.nd import rule_set_markers

        rule_markers = rule_set_markers(text)
        for c in citations:
            if c.cite_type != CitationType.COURT_RULE:
                continue
            split = _split_rule_normalized(c.normalized)
            if split is None:
                continue
            rule_fulls.setdefault(split, []).append(c)
            sets_by_number.setdefault(split[1], set()).add(split[0])

    def resolve_rule_pin(pin: Citation, start: int, end: int) -> bool:
        """Attribute a bare "Rule N(x)" to a rule set and link it.

        Ladder (ported from ndcourts-mcp notes.py), most reliable first:
        (1) explicit trailing marker through a constrained gap ("Rule 60(b)
        of the North Dakota Rules of Civil Procedure"); (2) nearest
        preceding rule-set marker anywhere earlier; (3) sole set: the
        document's full cites use this number under exactly one set.
        Otherwise drop (return False) — false-positive control.

        Linking: the nearest preceding full cite of the attributed set and
        number; else the earliest one anywhere (bare form first, full cite
        later). When no full cite of that set+number exists, the parent is
        synthesized from set + number — but only when the attribution is
        explicit (trailing) or uncontradicted (no other set in the document
        cites this number). A nearest-marker attribution that conflicts
        with the document's full cites is dropped: a miss is recoverable, a
        confidently wrong parent is not.
        """
        number = pin.components["rule"]
        attributed = rung = None
        for ms, _me, canon in rule_markers:
            if end <= ms <= end + 80 and _RULE_TRAILING_GAP_RE.fullmatch(text[end:ms]):
                attributed, rung = canon, "trailing"
                break
        if attributed is None:
            preceding = [c for ms, _me, c in rule_markers if ms < start]
            if preceding:
                attributed, rung = preceding[-1], "marker"
        if attributed is None:
            sets = sets_by_number.get(number, set())
            if len(sets) == 1:
                attributed, rung = next(iter(sets)), "sole_set"
        if attributed is None:
            return False

        members = rule_fulls.get((attributed, number), [])
        parent = nearest_preceding(members, start)
        if parent is None and members:
            parent = min(members, key=lambda c: c.position)
        if parent is None:
            other_sets = sets_by_number.get(number, set()) - {attributed}
            if rung != "trailing" and other_sets:
                return False
            pin.parent_normalized = f"{attributed} {number}"
            from jetcite.patterns.states.nd import RULE_SET_JURISDICTION
            pin.jurisdiction = RULE_SET_JURISDICTION.get(
                attributed, pin.jurisdiction)
        else:
            _link_pin(pin, parent)
        pin.components["attribution"] = rung
        return True

    resolved: list[Citation] = []
    for pin in sorted(pin_candidates, key=lambda c: c.position):
        start, end = pin.position, pin.position + len(pin.raw_text)
        if any(s < end and start < e for s, e in full_spans):
            continue  # span already covered by a full citation
        shape = pin.components.get("shape")

        if shape == "reporter_pin":
            if "year" in pin.components:  # neutral "at ¶" short form
                key = f"{pin.components['year']} ND {pin.components['number']}"
                parent = nearest_preceding(by_norm.get(key, []), start)
            else:
                vr = (pin.components["volume"], pin.components["reporter"])
                parent = nearest_preceding(by_vol_rep.get(vr, []), start)
            # Shape 2: pick up the short-form case name preceding the pin
            # ("Goss, 491 F.3d at 363") — diagnostic, not used for linking.
            name = extract_antecedent_name(text, start)
            if name and len(name.split()) <= 2:
                pin.antecedent_name = name
            if parent is not None:
                _link_pin(pin, parent)
            resolved.append(pin)

        elif shape == "name_pin":
            key = pin.components.get("name", "").lower().rstrip(".,")
            parent = nearest_preceding(by_name.get(key, []), start)
            if parent is None:
                continue  # unresolvable bare name — drop
            pin.antecedent_name = pin.components["name"]
            _link_pin(pin, parallel_member_for(pin, parent, start))
            resolved.append(pin)

        elif shape == "rule_pin":
            if resolve_rule_pin(pin, start, end):
                resolved.append(pin)

        elif shape == "id":
            # Two guards on the antecedent pools:
            #   1. Quoted-matter exclusion — a citation inside a quotation is
            #      the quoted author's, not this writer's, so it cannot
            #      capture an id. outside the quote. An id. that is itself
            #      inside a quote resolves within the quoted world (filter
            #      skipped).
            #   2. Page-pin type guard — "id. at 146" references a paginated
            #      source; constitutions, statutes, and rules take
            #      subdivision pins, not page pins. Case antecedents only.
            #      Also catches quotes the span detector cannot see
            #      (unmarked block quotes).
            pin_in_quote = _in_quote(start)
            fulls = id_antecedents if pin_in_quote else [
                c for c in id_antecedents if not _in_quote(c.position)]
            chain = resolved if pin_in_quote else [
                p for p in resolved if not _in_quote(p.position)]
            if pin.pin_page and not pin.pin_paragraph:
                fulls = [c for c in fulls if c.cite_type == CitationType.CASE]
                chain = [p for p in chain
                         if p.parent_normalized is None
                         or norm_type.get(p.parent_normalized,
                                          CitationType.CASE)
                         == CitationType.CASE]
            nearest_full = nearest_preceding(fulls, start)
            nearest_pin = nearest_preceding(chain, start)
            if nearest_pin is not None and (
                nearest_full is None or nearest_pin.position > nearest_full.position
            ):
                # Chained Id. — inherit the prior pin's parent transitively.
                if nearest_pin.parent_normalized is not None:
                    _link_pin(pin, nearest_pin)
                    _inherit_pinpoint(pin, nearest_pin)
                resolved.append(pin)
            elif nearest_full is not None:
                if ambiguous_string_cite(nearest_full, start, fulls):
                    resolved.append(pin)  # kept unresolved — ambiguous antecedent
                else:
                    member = parallel_member_for(pin, nearest_full, start)
                    _link_pin(pin, member)
                    # Bare Id.: same pinpoint as the antecedent. The ¶
                    # usually rides the parallel group's neutral member;
                    # fall back to the textually nearest cite.
                    _inherit_pinpoint(pin, member)
                    if not (pin.pin_page or pin.pin_paragraph):
                        _inherit_pinpoint(pin, nearest_full)
                    resolved.append(pin)
            else:
                # No preceding citation at all: explicit pin syntax is kept as
                # a warning; a bare "Id." is dropped as noise.
                if pin.pin_page or pin.pin_paragraph:
                    resolved.append(pin)

    return resolved


def _inherit_pin_sources(pins: list[Citation], citations: list[Citation]) -> None:
    """Copy each resolved pin's sources from its parent full cite.

    Runs after URL resolution and cache application so pins inherit resolved
    PDF URLs and local sources. Pin cites never get their own refs files.
    """
    by_position = {c.position: c for c in citations}
    for pin in pins:
        parent = by_position.get(pin.components.get("parent_position"))
        if parent is not None:
            pin.sources = list(parent.sources)


def _apply_cache(citations: list[Citation], refs_dir: Path) -> None:
    """Check the local cache for each citation and add local sources."""
    from jetcite.cache import add_local_source, resolve_local

    for cite in citations:
        local_path = resolve_local(cite, refs_dir)
        if local_path is not None:
            add_local_source(cite, local_path)


def scan_text(
    text: str,
    refs_dir: Path | None = None,
    resolve: bool = True,
    include_pin_cites: bool = False,
    include_occurrences: bool = False,
) -> list[Citation]:
    """Scan text for all citations, deduplicated by normalized form.

    Returns citations in order of first appearance, with parallel
    citations detected and linked.

    If refs_dir is provided, checks the local cache and adds a local
    Source at the front of each citation's sources list when found.

    If resolve is True (default), resolves ndcourts.gov search URLs to
    direct opinion PDF URLs via HTTP.

    If include_pin_cites is True, Bluebook short forms ("491 F.3d at 363",
    "Goss at 363", "Id. ¶ 14", bare "Rule 60(b)") are returned as
    additional entries with
    ``is_pin_cite=True``, linked to their parent full cite via
    ``parent_normalized`` (None when unresolved) and inheriting the parent's
    sources. Pin cites never enter dedup and never affect the full-citation
    entries; the default output is unchanged.

    If include_occurrences is True, repeat full-form CASE citations — the
    second and later appearances of a normalized form, e.g. a short cite
    written out as "Olson, 2024 ND 156, ¶ 12" — are returned as additional
    entries with ``is_repeat=True`` and ``parent_normalized`` linking back
    to the first occurrence. Repeats inherit the parent's sources, never
    resolve URLs or map to refs-cache files of their own, and never affect
    the deduplicated entries; the default output is unchanged.

    Citation positions index into ``preprocess_document_text(text)``, not
    the raw input — consumers mapping positions back to the document must
    preprocess identically.
    """
    # Strip page furniture up front so a citation split across a page break
    # rejoins, and so matcher positions stay aligned with the text the
    # parallel/antecedent detectors below see. Idempotent with the same call
    # inside each matcher's find_all.
    text = preprocess_document_text(text)

    all_citations: list[Citation] = []
    repeats: list[Citation] = []
    # Re-citations that are NOT emitted (non-case types, or any repeat when
    # include_occurrences is off) still mark real positions in the text.
    # Pin resolution must see them: an "Id." following a re-citation of
    # N.D.C.C. § X refers to the statute at that position, not to whatever
    # emitted citation happens to sit nearer to the first occurrence.
    shadow_repeats: list[Citation] = []
    pin_candidates: list[Citation] = []
    seen: set[str] = set()

    matchers = get_matchers()
    for matcher in matchers:
        for cite in matcher.find_all(text):
            if cite.is_pin_cite:
                if include_pin_cites:
                    pin_candidates.append(cite)
                continue
            if cite.normalized not in seen:
                seen.add(cite.normalized)
                all_citations.append(cite)
            elif include_occurrences and cite.cite_type == CitationType.CASE:
                cite.is_repeat = True
                repeats.append(cite)
            elif include_pin_cites:
                shadow_repeats.append(cite)

    # Sort by position in source text
    all_citations.sort(key=lambda c: c.position)

    # Detect parallel citations (authority-level: first occurrences only)
    _detect_parallel_citations(all_citations, text)

    occurrences = all_citations
    if repeats:
        repeats.sort(key=lambda c: c.position)
        first_by_norm: dict[str, Citation] = {}
        for c in all_citations:
            first_by_norm.setdefault(c.normalized, c)
        for rep in repeats:
            parent = first_by_norm.get(rep.normalized)
            if parent is not None:
                rep.parent_normalized = parent.normalized
                rep.components["parent_position"] = parent.position
        # Link adjacent repeat pairs ("2024 ND 156, ¶ 12, 10 N.W.3d 500")
        # so consumers can fold a restated parallel into one occurrence.
        _detect_parallel_citations(repeats, text)
        occurrences = sorted(all_citations + repeats, key=lambda c: c.position)

    # Attach the governing case name to each case citation (best-effort).
    # Run over the full occurrence list so the backward-search window for
    # each cite is clamped at the true preceding citation.
    _detect_antecedent_names(occurrences, text)

    # Full-cite trailing page pins ("259 N.W.2d 621, 627"): every occurrence,
    # repeats included, gets its own pin from its own position in the text.
    _capture_trailing_page_pins(occurrences, text)

    # Resolve ND opinion URLs to direct PDF links (first occurrences only;
    # repeats inherit the resolved sources below)
    if resolve:
        resolve_nd_opinion_urls(all_citations)

    # Check local cache
    if refs_dir is not None:
        _apply_cache(all_citations, refs_dir)

    if repeats:
        _inherit_pin_sources(repeats, all_citations)

    if include_pin_cites:
        # Antecedent pool for pin resolution: the emitted occurrences plus
        # the shadow re-citations, each linked to its first occurrence so a
        # pin resolved against a shadow inherits the first occurrence's
        # sources via parent_position. Shadows are never returned.
        antecedents = occurrences
        if shadow_repeats:
            first_by_norm = {}
            for c in all_citations:
                first_by_norm.setdefault(c.normalized, c)
            linked = []
            for rep in shadow_repeats:
                parent = first_by_norm.get(rep.normalized)
                if parent is None:
                    continue
                rep.parent_normalized = parent.normalized
                rep.components["parent_position"] = parent.position
                rep.components["_shadow"] = True
                linked.append(rep)
            antecedents = sorted(occurrences + linked, key=lambda c: c.position)
        pins = _resolve_pin_cites(pin_candidates, antecedents, text)
        _inherit_pin_sources(pins, antecedents)
        return sorted(occurrences + pins, key=lambda c: c.position)

    return occurrences


def lookup(
    text: str,
    refs_dir: Path | None = None,
    resolve: bool = True,
) -> Citation | None:
    """Look up a single citation string. Returns the first match.

    If refs_dir is provided, checks the local cache and adds a local
    Source at the front of the citation's sources list when found.

    If resolve is True (default), resolves ndcourts.gov search URLs to
    direct opinion PDF URLs via HTTP.
    """
    matchers = get_matchers()
    for matcher in matchers:
        result = matcher.find_first(text)
        if result:
            if resolve:
                resolve_nd_opinion_urls([result])
            if refs_dir is not None:
                _apply_cache([result], refs_dir)
            return result
    return None

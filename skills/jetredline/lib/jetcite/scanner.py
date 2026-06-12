"""Batch document scanning for citations."""

from __future__ import annotations

from pathlib import Path

from jetcite.casename import extract_antecedent_name
from jetcite.cleanup import preprocess_document_text
from jetcite.models import Citation, CitationType
from jetcite.patterns import get_matchers
from jetcite.resolver import resolve_nd_opinion_urls


def _detect_parallel_citations(citations: list[Citation], text: str) -> None:
    """Detect parallel citations and link them.

    When two case citations appear close together in text separated by a comma
    or semicolon (e.g., "2024 ND 156, 10 N.W.3d 500"), they refer to the same
    case. This function links them by populating each citation's parallel_cites
    list and merging their sources.
    """
    case_cites = [(i, c) for i, c in enumerate(citations) if c.cite_type == CitationType.CASE]

    for idx in range(len(case_cites) - 1):
        _, cite_a = case_cites[idx]
        _, cite_b = case_cites[idx + 1]

        # Check if they're adjacent in the original text
        end_a = cite_a.position + len(cite_a.raw_text)
        start_b = cite_b.position

        # Get the text between them
        between = text[end_a:start_b]

        # Parallel citations are separated by ", " or "; " with optional whitespace
        # and possibly a pinpoint like ", ¶ 12, "
        stripped = between.strip()

        # Must be a short separator — comma, semicolon, or pinpoint then comma
        if not stripped:
            continue

        # Common patterns between parallel cites:
        #   ", "  or  "; "  or  ", ¶ 12, "  or  " ¶ 12, "
        # The separator should be short (under ~40 chars) and start with , or ;
        # or be just whitespace around a pinpoint
        if len(stripped) > 40:
            continue

        # Must start with comma or semicolon
        if not stripped.startswith((",", ";")):
            continue

        # Should not contain sentence-ending punctuation or text that indicates
        # a new thought (period, "see", "and", etc.)
        inner = stripped.lstrip(",;").strip()
        if any(sep in inner.lower() for sep in (".", "see ", "and ", "but ", "cf.")):
            continue

        # If inner text remains and it's not a pinpoint or empty, skip
        # Valid inner: empty, or just a pinpoint like "¶ 12" or "at 128"
        if inner and not _looks_like_pinpoint_or_empty(inner):
            continue

        # Link them
        if cite_b.normalized not in cite_a.parallel_cites:
            cite_a.parallel_cites.append(cite_b.normalized)
        if cite_a.normalized not in cite_b.parallel_cites:
            cite_b.parallel_cites.append(cite_a.normalized)

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

    Keys: the whole name, the first party (text before " v. "), and the first
    party's first word when it is a plausible surname (≥3 chars) — so a full
    cite named "Goss Int'l Corp. v. Man Roland" answers to "goss".
    """
    import re
    keys = {name.lower()}
    first_party = re.split(r"\s+v\.?\s", name, maxsplit=1)[0].strip().rstrip(",")
    if first_party:
        keys.add(first_party.lower())
        first_word = first_party.split()[0].rstrip(".,").lower()
        if len(first_word) >= 3:
            keys.add(first_word)
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
    """
    if not pin_candidates:
        return []

    full_spans = [(c.position, c.position + len(c.raw_text)) for c in citations]
    case_cites = [c for c in citations if c.cite_type == CitationType.CASE]

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

    def ambiguous_string_cite(nearest: Citation, pos: int) -> bool:
        """True when the citation preceding ``pos`` sits in a string cite, so
        an Id. reference to it is ambiguous. Parallel pairs are one authority,
        not ambiguous."""
        second = None
        for c in case_cites:
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
            _link_pin(pin, parent)
            resolved.append(pin)

        elif shape == "id":
            nearest_full = nearest_preceding(case_cites, start)
            nearest_pin = nearest_preceding(resolved, start)
            if nearest_pin is not None and (
                nearest_full is None or nearest_pin.position > nearest_full.position
            ):
                # Chained Id. — inherit the prior pin's parent transitively.
                if nearest_pin.parent_normalized is not None:
                    _link_pin(pin, nearest_pin)
                resolved.append(pin)
            elif nearest_full is not None:
                if ambiguous_string_cite(nearest_full, start):
                    resolved.append(pin)  # kept unresolved — ambiguous antecedent
                else:
                    _link_pin(pin, nearest_full)
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
) -> list[Citation]:
    """Scan text for all citations, deduplicated by normalized form.

    Returns citations in order of first appearance, with parallel
    citations detected and linked.

    If refs_dir is provided, checks the local cache and adds a local
    Source at the front of each citation's sources list when found.

    If resolve is True (default), resolves ndcourts.gov search URLs to
    direct opinion PDF URLs via HTTP.

    If include_pin_cites is True, Bluebook short forms ("491 F.3d at 363",
    "Goss at 363", "Id. ¶ 14") are returned as additional entries with
    ``is_pin_cite=True``, linked to their parent full cite via
    ``parent_normalized`` (None when unresolved) and inheriting the parent's
    sources. Pin cites never enter dedup and never affect the full-citation
    entries; the default output is unchanged.
    """
    # Strip page furniture up front so a citation split across a page break
    # rejoins, and so matcher positions stay aligned with the text the
    # parallel/antecedent detectors below see. Idempotent with the same call
    # inside each matcher's find_all.
    text = preprocess_document_text(text)

    all_citations: list[Citation] = []
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

    # Sort by position in source text
    all_citations.sort(key=lambda c: c.position)

    # Detect parallel citations
    _detect_parallel_citations(all_citations, text)

    # Attach the governing case name to each case citation (best-effort)
    _detect_antecedent_names(all_citations, text)

    # Resolve ND opinion URLs to direct PDF links
    if resolve:
        resolve_nd_opinion_urls(all_citations)

    # Check local cache
    if refs_dir is not None:
        _apply_cache(all_citations, refs_dir)

    if include_pin_cites:
        pins = _resolve_pin_cites(pin_candidates, all_citations, text)
        _inherit_pin_sources(pins, all_citations)
        return sorted(all_citations + pins, key=lambda c: c.position)

    return all_citations


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

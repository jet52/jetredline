"""Batch document scanning for citations."""

from __future__ import annotations

from pathlib import Path

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


def _looks_like_pinpoint_or_empty(s: str) -> bool:
    """Check if a string looks like a pinpoint reference or is trivially empty."""
    import re
    # Match: ¶ 12, ¶¶ 12-15, at 128, 128, at ¶ 12, or nothing meaningful
    return bool(re.match(
        r'^(?:at\s+)?(?:¶¶?\s*)?\d+(?:\s*[-–]\s*\d+)?$',
        s.strip(),
    ))


def _verify_parallel_citations(citations: list[Citation], refs_dir: Path) -> None:
    """For parallel pairs where one cite is cached, verify the other via CL lookup.

    Compares case names between the cached opinion and the CL cluster metadata
    for the uncached parallel cite. Sets parallel_verified on the uncached cite.
    """
    import re

    from jetcite.sources.courtlistener import _get_token, lookup_citation

    token = _get_token()
    if not token:
        return

    norm_map = {c.normalized: c for c in citations}

    for cite in citations:
        if not cite.parallel_cites:
            continue
        has_local = any(s.name == "local" for s in cite.sources)
        if not has_local:
            continue

        for par_norm in cite.parallel_cites:
            par = norm_map.get(par_norm)
            if par is None or par.parallel_verified is not None:
                continue
            if any(s.name == "local" for s in par.sources):
                continue

            comp = par.components
            if not (comp.get("volume") and comp.get("reporter") and comp.get("page")):
                continue

            # Read case name from cached file: first line is "# Case Name"
            local_source = next((s for s in cite.sources if s.name == "local"), None)
            if local_source is None:
                continue
            local_path = Path(local_source.url.removeprefix("file://"))
            try:
                first_line = local_path.open(encoding="utf-8").readline().strip()
            except OSError:
                continue
            if not first_line.startswith("# "):
                continue
            cached_name = first_line[2:].strip()

            result = lookup_citation(
                volume=comp["volume"],
                reporter=comp["reporter"],
                page=comp["page"],
                token=token,
                timeout=5.0,
            )
            if result is None:
                continue

            def _norm_name(s: str) -> str:
                return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

            if _norm_name(cached_name) == _norm_name(result["case_name"]):
                par.parallel_verified = True
            else:
                par.parallel_verified = False


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
) -> list[Citation]:
    """Scan text for all citations, deduplicated by normalized form.

    Returns citations in order of first appearance, with parallel
    citations detected and linked.

    If refs_dir is provided, checks the local cache and adds a local
    Source at the front of each citation's sources list when found.

    If resolve is True (default), resolves ndcourts.gov search URLs to
    direct opinion PDF URLs via HTTP.
    """
    all_citations: list[Citation] = []
    seen: set[str] = set()

    matchers = get_matchers()
    for matcher in matchers:
        for cite in matcher.find_all(text):
            if cite.normalized not in seen:
                seen.add(cite.normalized)
                all_citations.append(cite)

    # Sort by position in source text
    all_citations.sort(key=lambda c: c.position)

    # Detect parallel citations
    _detect_parallel_citations(all_citations, text)

    # Resolve ND opinion URLs to direct PDF links
    if resolve:
        resolve_nd_opinion_urls(all_citations)

    # Check local cache
    if refs_dir is not None:
        _apply_cache(all_citations, refs_dir)
        _verify_parallel_citations(all_citations, refs_dir)

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

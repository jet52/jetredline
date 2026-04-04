"""Local reference cache for fetched citation content.

Resolves citations to local file paths in a ~/refs/ directory structure
and caches fetched content for future offline access.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from jetcite.models import Citation, CitationType, Source

USER_AGENT = "jetcite/1.5 (legal-research-tool; https://github.com/jet52/jetcite)"
from jetcite.patterns.base import roman_to_int

# Staleness thresholds in days — informational only, not auto-refetch
STALENESS_DAYS = {
    CitationType.CASE: None,  # permanent
    CitationType.CONSTITUTION: None,  # permanent
    CitationType.STATUTE: 90,
    CitationType.REGULATION: 90,
    CitationType.COURT_RULE: 180,
}

DEFAULT_REFS_DIR = Path.home() / "refs"

# Historical North Western reporters (pre-neutral-citation era)
_ND_REPORTERS = frozenset({"N.W.", "N.W.2d", "N.D."})

# Federal case reporters (used by legacy.py for cite_type classification)
_FEDERAL_REPORTERS = frozenset({
    "U.S.", "S. Ct.", "L. Ed.", "L. Ed. 2d",
    "F.", "F.2d", "F.3d", "F.4th",
    "F. Supp.", "F. Supp. 2d", "F. Supp. 3d",
    "B.R.", "F.R.D.", "Fed. Cl.", "M.J.",
    "Vet. App.", "T.C.", "F. App\u2019x", "F. App'x",
})

# Map federal rule_set keys to directory names
_FEDERAL_RULE_DIRS = {
    "frcp": "FRCP",
    "frcrp": "FRCrP",
    "fre": "FRE",
    "frap": "FRAP",
    "frbp": "FRBP",
}


def _reporter_dir(reporter: str) -> str:
    """Normalize a reporter abbreviation to a directory name.

    U.S. Reports maps to 'US' (not 'scotus') so all opinions live under
    opin/{reporter_dir}/ in a consistent pattern.
    """
    return reporter.replace(".", "").replace(" ", "").replace("\u2019", "").replace("'", "")


def _citation_path(citation: Citation) -> Path | None:
    """Map a citation to its relative path within the refs directory.

    Content-type-centric layout:
      opin/{reporter}/   — all opinions (cases), keyed by reporter abbreviation
      statute/{code}/    — statutes (NDCC, USC)
      reg/{code}/        — regulations (NDAC, CFR)
      cnst/{jurisdiction}/ — constitutions (US, ND)
      rule/{rule_set}/   — court rules (ND and federal)

    Returns None if the citation type/components don't map to a known path.
    """
    c = citation.components

    if citation.cite_type == CitationType.CASE:
        if citation.jurisdiction == "nd" and "year" in c and "number" in c:
            return Path("opin/ND") / c["year"] / f"{c['year']}ND{c['number']}.md"
        elif "reporter" in c and "volume" in c and "page" in c:
            rdir = _reporter_dir(c["reporter"])
            return Path("opin") / rdir / c["volume"] / f"{c['page']}.md"
        return None

    if citation.cite_type == CitationType.STATUTE:
        if citation.jurisdiction == "nd":
            if "title" in c and "chapter" in c:
                t = f"{c['title']}.{c['title_dec']}" if c.get("title_dec") else c["title"]
                ch = f"{c['chapter']}.{c['chapter_dec']}" if c.get("chapter_dec") else c["chapter"]
                return Path("statute/NDCC") / f"title-{t}" / f"chapter-{t}-{ch}.md"
        elif "title" in c and "section" in c:
            return Path("statute/USC") / c["title"] / f"{c['section']}.md"
        return None

    if citation.cite_type == CitationType.CONSTITUTION:
        if citation.jurisdiction == "nd":
            if "article" in c and "section" in c:
                art_num = roman_to_int(c["article"])
                return Path("cnst/ND") / f"art-{art_num:02d}" / f"sec-{c['section']}.md"
        elif citation.jurisdiction == "us":
            if "amendment" in c:
                amend_num = roman_to_int(c["amendment"])
                if amend_num:
                    return Path("cnst/US") / f"amend-{amend_num}.md"
            elif "article" in c:
                art_num = roman_to_int(c["article"])
                if art_num and "section" in c:
                    return Path("cnst/US") / f"art-{art_num:02d}" / f"sec-{c['section']}.md"
                elif art_num:
                    return Path("cnst/US") / f"art-{art_num:02d}.md"
        return None

    if citation.cite_type == CitationType.REGULATION:
        if citation.jurisdiction == "nd" and all(k in c for k in ("part1", "part2", "part3")):
            return (Path("reg/NDAC") / f"title-{c['part1']}"
                    / f"article-{c['part1']}-{c['part2']}"
                    / f"chapter-{c['part1']}-{c['part2']}-{c['part3']}.md")
        elif "title" in c and "section" in c:
            return Path("reg/CFR") / c["title"] / f"{c['section']}.md"
        return None

    if citation.cite_type == CitationType.COURT_RULE:
        # Federal rules
        rule_set = c.get("rule_set", "")
        if rule_set in _FEDERAL_RULE_DIRS:
            rule_num = c.get("rule_number", "")
            if rule_num:
                return Path("rule") / _FEDERAL_RULE_DIRS[rule_set] / f"rule-{rule_num}.md"
            return None

        # ND court rules
        rule_parts = c.get("parts", [])
        if rule_set and rule_parts:
            if rule_set == "ndstdsimposinglawyersanctions":
                filename = f"rule-{'-'.join(rule_parts)}.md"
            elif rule_set == "ndcodejudconduct":
                filename = f"rule-{rule_parts[0]}.md"
            elif rule_set == "rltdpracticeoflawbylawstudents":
                arabic = roman_to_int(rule_parts[0])
                filename = f"rule-{arabic}.md" if arabic else f"rule-{rule_parts[0]}.md"
            else:
                filename = f"rule-{'.'.join(rule_parts)}.md"
            return Path("rule") / rule_set / filename
        return None

    return None


def citation_path(citation: Citation) -> Path | None:
    """Public API: map a citation to its relative path within the refs directory.

    Returns a relative path (e.g., ``opin/NW2d/585/351.md``) or None if the
    citation type/components don't map to a known cache path.
    """
    return _citation_path(citation)


def resolve_local(citation: Citation, refs_dir: Path | None = None) -> Path | None:
    """Check if a citation has a local cached file.

    Returns the full path if found, None otherwise.
    """
    if refs_dir is None:
        refs_dir = DEFAULT_REFS_DIR

    rel = _citation_path(citation)
    if rel is None:
        return None

    full = refs_dir / rel
    if full.is_file():
        return full
    return None


def _refs_writable(refs_dir: Path) -> bool:
    """Check whether the refs directory exists and is writable."""
    try:
        if refs_dir.is_dir():
            return os.access(refs_dir, os.W_OK)
        refs_dir.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def _original_suffix(content_type: str | None) -> str:
    """Map a MIME content type to a file extension for the original."""
    _SUFFIXES = {
        "text/html": ".html",
        "application/pdf": ".pdf",
        "application/xhtml+xml": ".html",
        "text/plain": ".txt",
    }
    return _SUFFIXES.get(content_type or "", ".bin")


def write_meta(path: Path, meta: dict) -> None:
    """Write or update a .meta.json sidecar for a cached file."""
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def cache_content(
    citation: Citation,
    content: str,
    refs_dir: Path | None = None,
    source_url: str | None = None,
    content_type: str = "text/markdown",
    original: bytes | None = None,
    original_content_type: str | None = None,
    http_headers: dict | None = None,
    # Backward compat: accept raw_html as alias for original
    raw_html: str | None = None,
) -> Path | None:
    """Write content to the local cache and create a .meta.json sidecar.

    If ``original`` bytes are provided (or the legacy ``raw_html`` string),
    writes a dot-prefixed original sibling file (e.g., ``.351.orig.html``)
    alongside the markdown.

    The ``.meta.json`` sidecar includes:
      - citation, source_url, fetched, content_type (always)
      - original_content_type, original_file, content_hash (when original provided)
      - etag, last_modified (when http_headers provided)

    Best-effort: returns None silently if the refs directory is missing,
    read-only, or any write fails (e.g., sandboxed environments).

    Returns the path written, or None if the citation can't be mapped to a
    path or the write fails.
    """
    if refs_dir is None:
        refs_dir = DEFAULT_REFS_DIR

    rel = _citation_path(citation)
    if rel is None:
        return None

    if not _refs_writable(refs_dir):
        return None

    # Handle legacy raw_html parameter
    if raw_html is not None and original is None:
        original = raw_html.encode("utf-8")
        if original_content_type is None:
            original_content_type = "text/html"

    full = refs_dir / rel
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")

        # Build metadata
        meta: dict = {
            "citation": citation.normalized,
            "source_url": source_url or (citation.sources[0].url if citation.sources else None),
            "fetched": datetime.now(timezone.utc).isoformat(),
            "content_type": content_type,
        }

        # Write original as dot-prefixed sibling and record in metadata
        if original:
            suffix = _original_suffix(original_content_type)
            orig_name = f".{full.stem}.orig{suffix}"
            orig_path = full.parent / orig_name
            orig_path.write_bytes(original)

            meta["original_content_type"] = original_content_type
            meta["original_file"] = orig_name
            meta["content_hash"] = f"sha256:{hashlib.sha256(original).hexdigest()}"

        # Record HTTP caching headers
        if http_headers:
            if "etag" in http_headers:
                meta["etag"] = http_headers["etag"]
            elif "ETag" in http_headers:
                meta["etag"] = http_headers["ETag"]
            if "last-modified" in http_headers:
                meta["last_modified"] = http_headers["last-modified"]
            elif "Last-Modified" in http_headers:
                meta["last_modified"] = http_headers["Last-Modified"]

        write_meta(full, meta)
    except OSError:
        return None

    return full


def read_meta(path: Path) -> dict | None:
    """Read the .meta.json sidecar for a cached file."""
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    if meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return None


def is_stale(citation: Citation, path: Path) -> bool | None:
    """Check if a cached file is stale based on staleness policy.

    Returns True if stale, False if fresh, None if no metadata or no policy.
    """
    max_days = STALENESS_DAYS.get(citation.cite_type)
    if max_days is None:
        return False  # permanent content

    meta = read_meta(path)
    if not meta or "fetched" not in meta:
        return None

    fetched = datetime.fromisoformat(meta["fetched"])
    age = (datetime.now(timezone.utc) - fetched).days
    return age > max_days


def add_local_source(citation: Citation, path: Path) -> None:
    """Add a local file source to the front of a citation's sources list."""
    local_url = path.as_uri()
    # Don't add duplicate
    if any(s.name == "local" for s in citation.sources):
        return
    citation.sources.insert(0, Source(name="local", url=local_url))


def _get_extractor(url: str):
    """Return a source-specific content extractor for the given URL, or None.

    Extractors return (markdown, metadata_dict, raw_content) where raw_content
    is str (HTML) for courtlistener/justia/cornell, or bytes (PDF) for ndcourts.
    """
    host = urlparse(url).netloc
    _EXTRACTORS = {
        "www.courtlistener.com": "courtlistener",
        "supreme.justia.com": "justia",
        "www.law.cornell.edu": "cornell",
        "www.ndcourts.gov": "ndcourts",
    }
    source_key = _EXTRACTORS.get(host)
    if source_key == "courtlistener":
        from jetcite.sources.courtlistener import fetch_courtlistener
        return fetch_courtlistener
    elif source_key == "justia":
        from jetcite.sources.justia import fetch_justia
        return fetch_justia
    elif source_key == "cornell":
        from jetcite.sources.cornell import fetch_cornell
        return fetch_cornell
    elif source_key == "ndcourts":
        from jetcite.sources.ndcourts import fetch_ndcourts
        return fetch_ndcourts
    return None


def pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber.

    Returns the extracted text with pages separated by double newlines,
    or an empty string on failure.
    """
    import io
    import pdfplumber

    pages = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=False)
                if text:
                    pages.append(text)
    except Exception:
        return ""
    return "\n\n".join(pages)


def _fetch_generic(
    source_url: str,
    citation: Citation,
    timeout: float = 10.0,
) -> tuple[str | None, dict, bytes | None, str | None, dict | None]:
    """Generic fetcher: download and convert content to markdown.

    Handles HTML (via markdownify) and PDF (via pdfplumber) based on the
    Content-Type header.

    Returns (markdown, metadata, original_bytes, original_content_type, http_headers)
    or (None, {}, None, None, None) on failure.
    """
    try:
        resp = httpx.get(source_url, follow_redirects=True, timeout=timeout,
                         headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        return None, {}, None, None, None

    original_bytes = resp.content
    content_type = resp.headers.get("content-type", "text/html").split(";")[0].strip()
    http_headers = dict(resp.headers)

    if content_type == "application/pdf":
        content = pdf_to_text(original_bytes)
        if not content:
            return None, {}, None, None, None
    elif content_type in ("text/html", "application/xhtml+xml"):
        from markdownify import markdownify
        content = markdownify(resp.text, strip=["img", "script", "style"]).strip()
    else:
        content = resp.text

    return content, {}, original_bytes, content_type, http_headers


def _try_conditional_fetch(
    source_url: str, meta: dict, timeout: float = 10.0,
) -> httpx.Response | None:
    """Attempt a conditional HTTP GET using stored ETag/Last-Modified.

    Returns the response if the server returned 200 (content changed),
    or None if the server returned 304 (not modified) or the request failed.
    """
    headers = {"User-Agent": USER_AGENT}
    if meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]

    # If we have no caching headers, can't do a conditional request
    if len(headers) == 1:
        return None

    try:
        resp = httpx.get(source_url, follow_redirects=True, timeout=timeout,
                         headers=headers)
        if resp.status_code == 304:
            return None  # not modified
        resp.raise_for_status()
        return resp
    except (httpx.HTTPError, httpx.TimeoutException):
        return None


def fetch_and_cache(
    citation: Citation,
    refs_dir: Path | None = None,
    timeout: float = 10.0,
    force: bool = False,
    refresh_stale: bool = False,
) -> Path | None:
    """Fetch citation content from its primary web source and cache locally.

    Uses source-specific extractors for known hosts (CourtListener, Justia,
    Cornell, ndcourts) to produce well-formatted markdown. Falls back to
    generic markdownify/pdfplumber for unknown sources.

    Args:
        force: Re-fetch even when a local file already exists.
        refresh_stale: Only re-fetch if is_stale() returns True. Uses
            conditional HTTP requests (ETag/Last-Modified) when available,
            and compares content hashes to detect actual changes.

    Returns the cached file path, or None if fetching fails or the
    citation can't be mapped to a cache path.
    """
    if refs_dir is None:
        refs_dir = DEFAULT_REFS_DIR

    existing = resolve_local(citation, refs_dir)

    # Handle refresh_stale: only re-fetch if actually stale
    if refresh_stale and existing is not None:
        if not is_stale(citation, existing):
            add_local_source(citation, existing)
            return existing
        # It's stale — try conditional fetch first
        meta = read_meta(existing) or {}
        source_url = meta.get("source_url")
        if source_url:
            resp = _try_conditional_fetch(source_url, meta, timeout)
            if resp is None:
                # 304 Not Modified — just update the timestamp
                meta["fetched"] = datetime.now(timezone.utc).isoformat()
                write_meta(existing, meta)
                add_local_source(citation, existing)
                return existing
            # Got new content — check if it actually changed
            new_hash = f"sha256:{hashlib.sha256(resp.content).hexdigest()}"
            if meta.get("content_hash") == new_hash:
                # Content unchanged despite 200 — update timestamp + headers
                meta["fetched"] = datetime.now(timezone.utc).isoformat()
                if resp.headers.get("etag"):
                    meta["etag"] = resp.headers["etag"]
                if resp.headers.get("last-modified"):
                    meta["last_modified"] = resp.headers["last-modified"]
                write_meta(existing, meta)
                add_local_source(citation, existing)
                return existing
        # Content actually changed or no conditional headers — fall through to full fetch
        force = True

    # Don't fetch if already cached (unless forced)
    if existing is not None and not force:
        add_local_source(citation, existing)
        return existing

    # Find a web source URL and try source-specific extractors first
    content = None
    original: bytes | None = None
    original_content_type: str | None = None
    http_headers: dict | None = None
    source_url = None

    for s in citation.sources:
        if s.name == "local":
            continue
        extractor = _get_extractor(s.url)
        if extractor is not None:
            content, _meta, raw_content = extractor(s.url, citation, timeout)
            if content:
                source_url = s.url
                if raw_content is not None:
                    if isinstance(raw_content, bytes):
                        original = raw_content
                        original_content_type = "application/pdf"
                    else:
                        original = raw_content.encode("utf-8")
                        original_content_type = "text/html"
                break

    # If no source-specific extractor worked, fall back to generic
    if content is None:
        for s in citation.sources:
            if s.name == "local":
                continue
            source_url = s.url
            break
        if source_url is None:
            return None
        content, _meta, original, original_content_type, http_headers = (
            _fetch_generic(source_url, citation, timeout))

    if not content:
        return None

    # Apply content-type-specific cleanup
    from jetcite.cleanup import cleanup
    content = cleanup(content, citation.cite_type, citation.jurisdiction)

    path = cache_content(citation, content, refs_dir, source_url=source_url,
                         content_type="text/markdown",
                         original=original,
                         original_content_type=original_content_type,
                         http_headers=http_headers)
    if path is not None:
        add_local_source(citation, path)
    return path


# ── Batch / parallel fetching ─────────────────────────────────────


import asyncio
import time


class _PerHostRateLimiter:
    """Track last-request timestamps per hostname for polite rate limiting."""

    def __init__(self, delay: float = 0.5):
        self._delay = delay
        self._last: dict[str, float] = {}

    async def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        now = time.monotonic()
        last = self._last.get(host, 0.0)
        wait_time = self._delay - (now - last)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        self._last[host] = time.monotonic()


async def _fetch_one_async(
    citation: Citation,
    refs_dir: Path,
    timeout: float,
    force: bool,
    refresh_stale: bool,
    semaphore: asyncio.Semaphore,
    rate_limiter: _PerHostRateLimiter,
) -> tuple[Citation, Path | None]:
    """Fetch a single citation, respecting concurrency and rate limits.

    Runs the synchronous fetch_and_cache in a thread to avoid blocking
    the event loop (httpx sync client, pdfplumber, file I/O).
    """
    async with semaphore:
        # Rate-limit based on the primary source URL
        source_url = None
        for s in citation.sources:
            if s.name != "local":
                source_url = s.url
                break
        if source_url:
            await rate_limiter.wait(source_url)

        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(
            None,
            lambda: fetch_and_cache(
                citation, refs_dir=refs_dir, timeout=timeout,
                force=force, refresh_stale=refresh_stale,
            ),
        )
        return citation, path


async def fetch_and_cache_batch(
    citations: list[Citation],
    refs_dir: Path | None = None,
    max_concurrent: int = 5,
    per_host_delay: float = 0.5,
    timeout: float = 15.0,
    force: bool = False,
    refresh_stale: bool = False,
    on_complete: callable | None = None,
) -> list[tuple[Citation, Path | None]]:
    """Fetch and cache multiple citations concurrently.

    Args:
        citations: Citations to fetch.
        refs_dir: Reference cache directory.
        max_concurrent: Maximum concurrent fetches.
        per_host_delay: Minimum seconds between requests to same host.
        timeout: HTTP request timeout per citation.
        force: Re-fetch even when cached.
        refresh_stale: Only re-fetch stale mutable content.
        on_complete: Optional callback(citation, path) called as each completes.

    Returns:
        List of (citation, path_or_none) tuples in completion order.
    """
    if refs_dir is None:
        refs_dir = DEFAULT_REFS_DIR

    semaphore = asyncio.Semaphore(max_concurrent)
    rate_limiter = _PerHostRateLimiter(per_host_delay)

    async def _fetch_with_callback(cite):
        result = await _fetch_one_async(
            cite, refs_dir, timeout, force, refresh_stale,
            semaphore, rate_limiter,
        )
        if on_complete:
            on_complete(*result)
        return result

    tasks = [_fetch_with_callback(cite) for cite in citations]
    return await asyncio.gather(*tasks)


def fetch_and_cache_batch_sync(
    citations: list[Citation],
    refs_dir: Path | None = None,
    max_concurrent: int = 5,
    per_host_delay: float = 0.5,
    timeout: float = 15.0,
    force: bool = False,
    refresh_stale: bool = False,
    on_complete: callable | None = None,
) -> list[tuple[Citation, Path | None]]:
    """Synchronous wrapper for fetch_and_cache_batch.

    Creates an event loop and runs the async batch fetch.
    """
    return asyncio.run(fetch_and_cache_batch(
        citations, refs_dir=refs_dir, max_concurrent=max_concurrent,
        per_host_delay=per_host_delay, timeout=timeout,
        force=force, refresh_stale=refresh_stale, on_complete=on_complete,
    ))

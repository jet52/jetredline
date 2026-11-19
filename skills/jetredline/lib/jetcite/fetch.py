"""Fetch the text of a cited authority from its online source.

Nothing here touches the disk. Through 2.x this module's ancestor
(``jetcite.cache``) wrote every fetch into a ``~/refs`` tree and answered
later lookups from it; 3.0 removed that. A caller that wants to keep the
text keeps it itself, wherever suits the run. For North Dakota authority
the ndlaw MCP server is the better source in any case: it serves corpus
text, dated versions, and verification that a flat file cannot.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from jetcite._egress import NON_FETCH_HOSTS
from jetcite._http import USER_AGENT
from jetcite.models import Citation

try:
    import httpx
except ImportError:  # pragma: no cover - exercised in sandboxes without httpx
    httpx = None


@dataclass
class Fetched:
    """One fetched authority, held in memory."""

    text: str                       # cleaned markdown / plain text
    source_url: str                 # the URL that answered
    original: bytes | None = None   # the bytes as served (HTML or PDF)
    original_content_type: str | None = None
    # The normalized citation the answering source actually addresses, when
    # the text was reached only through a parallel cite the document paired.
    # A caller must not read such a fetch as confirming the pairing.
    via_parallel: str | None = None


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
) -> tuple[str | None, bytes | None, str | None]:
    """Generic fetcher: download and convert content to markdown.

    Handles HTML (via markdownify) and PDF (via pdfplumber) based on the
    Content-Type header.

    Returns (markdown, original_bytes, original_content_type), or
    (None, None, None) on failure.
    """
    if httpx is None:
        return None, None, None
    try:
        resp = httpx.get(source_url, follow_redirects=True, timeout=timeout,
                         headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException, ImportError):
        return None, None, None

    original_bytes = resp.content
    content_type = resp.headers.get("content-type", "text/html").split(";")[0].strip()

    if content_type == "application/pdf":
        content = pdf_to_text(original_bytes)
        if not content:
            return None, None, None
    elif content_type in ("text/html", "application/xhtml+xml"):
        from markdownify import markdownify
        content = markdownify(resp.text, strip=["img", "script", "style"]).strip()
    else:
        content = resp.text

    return content, original_bytes, content_type



def fetch_text(citation: Citation, timeout: float = 10.0) -> Fetched | None:
    """Fetch a citation's text from its best online source.

    Tries each source's own extractor in order, then a generic download of
    the first fetchable source no extractor claims. A host that has an extractor is
    never fetched generically: when ndcourts.gov's citation search finds no
    opinion, the generic path used to keep the search page as the opinion.

    Returns None when nothing usable comes back.
    """
    content = None
    original: bytes | None = None
    original_content_type: str | None = None
    used = None

    for s in citation.sources:
        extractor = _get_extractor(s.url)
        if extractor is None:
            continue
        content, _meta, raw = extractor(s.url, citation, timeout)
        if content:
            used = s
            if isinstance(raw, bytes):
                original, original_content_type = raw, "application/pdf"
            elif raw is not None:
                original, original_content_type = raw.encode("utf-8"), "text/html"
            break

    if not content:
        for s in citation.sources:
            if _get_extractor(s.url) is not None:
                continue
            if urlparse(s.url).netloc in NON_FETCH_HOSTS:
                continue  # link-only (official-print PDFs, reading copies)
            used = s
            content, original, original_content_type = _fetch_generic(
                s.url, citation, timeout)
            break

    if not content or used is None:
        return None

    from jetcite.cleanup import cleanup
    content = cleanup(content, citation.cite_type, citation.jurisdiction)
    if not content:
        return None
    return Fetched(text=content, source_url=used.url, original=original,
                   original_content_type=original_content_type,
                   via_parallel=used.via_parallel)


# ── Batch fetching ────────────────────────────────────────────────


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



async def fetch_text_batch(
    citations: list[Citation],
    max_concurrent: int = 5,
    per_host_delay: float = 0.5,
    timeout: float = 15.0,
    on_complete: callable | None = None,
) -> list[tuple[Citation, Fetched | None]]:
    """Fetch several citations concurrently, politely per host.

    ``on_complete(citation, fetched_or_none)`` is called as each finishes.
    Returns (citation, fetched_or_none) pairs in input order.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    rate_limiter = _PerHostRateLimiter(per_host_delay)

    async def _one(cite: Citation):
        async with semaphore:
            if cite.sources:
                await rate_limiter.wait(cite.sources[0].url)
            loop = asyncio.get_running_loop()
            got = await loop.run_in_executor(
                None, lambda: fetch_text(cite, timeout=timeout))
        if on_complete:
            on_complete(cite, got)
        return cite, got

    return await asyncio.gather(*[_one(c) for c in citations])


def fetch_text_batch_sync(citations: list[Citation], **kwargs):
    """Synchronous wrapper for :func:`fetch_text_batch`."""
    return asyncio.run(fetch_text_batch(citations, **kwargs))

"""URL resolution and optional HTTP verification."""

from __future__ import annotations

import asyncio

import httpx

from jetcite.models import Citation, CitationType, Source


async def _verify_url(client: httpx.AsyncClient, source: Source) -> None:
    """Verify a single URL with an HTTP HEAD request."""
    try:
        resp = await client.head(source.url, follow_redirects=True, timeout=10.0)
        source.verified = resp.status_code < 400
    except (httpx.HTTPError, httpx.TimeoutException):
        source.verified = False


async def verify_citations(
    citations: list[Citation],
    rate_limit: float = 1.0,
) -> None:
    """Verify source URLs in a list of citations.

    Verifies only the primary (first) source per citation to minimize
    external requests. Skips CourtListener /c/ redirect URLs when the
    citation has another verifiable source — CourtListener prefers API
    access for programmatic lookups, and the /c/ URLs are redirect
    endpoints meant for browser use.

    Args:
        citations: Citations whose sources will be verified in-place.
        rate_limit: Minimum seconds between requests.
    """
    verified_urls: dict[str, bool] = {}

    async with httpx.AsyncClient() as client:
        for cite in citations:
            if not cite.sources:
                continue

            # Pick the best source to verify: prefer non-CourtListener
            # when alternatives exist
            source = cite.sources[0]
            for s in cite.sources:
                if "courtlistener.com/c/" not in s.url:
                    source = s
                    break

            # Skip if we already verified this URL (e.g., shared via parallel cites)
            if source.url in verified_urls:
                source.verified = verified_urls[source.url]
                continue

            await _verify_url(client, source)
            verified_urls[source.url] = source.verified
            if rate_limit > 0:
                await asyncio.sleep(rate_limit)


def verify_citations_sync(
    citations: list[Citation],
    rate_limit: float = 1.0,
) -> None:
    """Synchronous wrapper for verify_citations."""
    asyncio.run(verify_citations(citations, rate_limit))


def resolve_nd_opinion_urls(citations: list[Citation]) -> None:
    """Resolve ndcourts.gov search URLs to direct opinion PDF URLs.

    For each ND neutral citation, fetches the search results page and
    extracts the direct link to the opinion PDF. Updates the source URL
    in-place. Citations that fail to resolve keep the search URL.
    """
    from jetcite.sources.ndcourts import resolve_nd_opinion_url

    for cite in citations:
        if cite.jurisdiction != "nd" or cite.cite_type != CitationType.CASE:
            continue
        year = cite.components.get("year")
        number = cite.components.get("number")
        if not year or not number:
            continue
        # Find the ndcourts source and replace its URL
        for src in cite.sources:
            if src.name == "ndcourts":
                resolved = resolve_nd_opinion_url(year, number)
                if resolved:
                    src.url = resolved
                break

"""ndcourts.gov URL generation for ND opinions and court rules."""

from __future__ import annotations

import re

from jetcite._http import http_get


def nd_opinion_url(year: str, number: str) -> str:
    """Generate an ndcourts.gov search URL for an ND Supreme Court opinion.

    This returns the search page URL. Use resolve_nd_opinion_url() to
    follow through to the direct PDF URL.
    """
    return (
        f"https://www.ndcourts.gov/supreme-court/opinions"
        f"?cit1={year}&citType=ND&cit2={number}"
        f"&pageSize=10&sortOrder=1"
    )


_OPINION_ID_RE = re.compile(
    r"window\.open\('/supreme-court/opinions/(\d+)'"
)


def resolve_nd_opinion_url(year: str, number: str) -> str | None:
    """Fetch the ndcourts.gov search page and extract the direct opinion URL.

    Returns the direct PDF URL (e.g., /supreme-court/opinions/171302),
    or None if the search returned no results or the request failed.
    """
    search_url = nd_opinion_url(year, number)
    resp = http_get(search_url, timeout=10.0)
    if resp is None or resp.status_code >= 400:
        return None

    m = _OPINION_ID_RE.search(resp.text)
    if not m:
        return None
    return f"https://www.ndcourts.gov/supreme-court/opinions/{m.group(1)}"


def fetch_ndcourts(
    source_url: str,
    citation: object,
    timeout: float = 15.0,
) -> tuple[str | None, dict, bytes | None]:
    """Fetch ND opinion content from ndcourts.gov.

    Downloads the opinion PDF, extracts text via pdfplumber, and applies
    opinion-specific cleanup.

    Returns (markdown_content, metadata_dict, original_pdf_bytes)
    or (None, {}, None) on failure.
    """
    resp = http_get(source_url, timeout=timeout)
    if resp is None or resp.status_code >= 400:
        return None, {}, None

    content_type = resp.content_type
    pdf_bytes = resp.content

    # If we got HTML (search page), try to extract the opinion ID and follow
    if content_type in ("text/html", "application/xhtml+xml"):
        m = _OPINION_ID_RE.search(resp.text)
        if not m:
            return None, {}, None
        direct_url = f"https://www.ndcourts.gov/supreme-court/opinions/{m.group(1)}"
        resp = http_get(direct_url, timeout=timeout)
        if resp is None or resp.status_code >= 400:
            return None, {}, None
        pdf_bytes = resp.content

    from jetcite.cache import pdf_to_text
    text = pdf_to_text(pdf_bytes)
    if not text:
        return None, {}, None

    return text, {}, pdf_bytes


def nd_court_rule_url(rule_set: str, parts: list[str]) -> str:
    """Generate an ndcourts.gov URL for a ND court rule."""
    joined = "-".join(parts)
    return f"https://www.ndcourts.gov/legal-resources/rules/{rule_set}/{joined}"


def nd_local_rule_url(rule: str) -> str:
    """Generate an ndcourts.gov search URL for a local rule."""
    return f"https://www.ndcourts.gov/legal-resources/rules/local/search?rule={rule}"


def nd_case_record_url(case_number: str) -> str:
    """Generate an ndcourts.gov URL for a case record."""
    return f"https://record.ndcourts.gov/{case_number}"


"""ndcourts.gov URL generation for ND opinions and court rules."""

from __future__ import annotations

import re

import httpx

_USER_AGENT = "jetcite/1.5 (legal-research-tool; https://github.com/jet52/jetcite)"


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
    try:
        resp = httpx.get(search_url, follow_redirects=True, timeout=10.0,
                         headers={"User-Agent": _USER_AGENT})
        if resp.status_code >= 400:
            return None
    except (httpx.HTTPError, httpx.TimeoutException):
        return None

    m = _OPINION_ID_RE.search(resp.text)
    if not m:
        return None
    return f"https://www.ndcourts.gov/supreme-court/opinions/{m.group(1)}"


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


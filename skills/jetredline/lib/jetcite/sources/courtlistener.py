"""CourtListener URL generation and content extraction for case citations.

Uses the Citation Lookup REST API (preferred by CourtListener) for fetching
opinion content:

    POST https://www.courtlistener.com/api/rest/v4/citation-lookup/
    Auth: "Authorization: Token <token>"
    Rate limits: 5000 queries/hr, 60 valid lookups/min, 250 cites/request

The lookup returns cluster metadata; opinion text requires follow-up requests
to /api/rest/v4/opinions/<id>/.

When no auth token is available, falls back to the unauthenticated search API
(/api/rest/v4/search/) which returns opinion text inline.

Set COURTLISTENER_TOKEN or COURTLISTENER_API_KEY environment variable to use
the preferred API.
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote

import httpx

_USER_AGENT = "jetcite/1.5 (legal-research-tool; https://github.com/jet52/jetcite)"
_CL_BASE = "https://www.courtlistener.com"
_LOOKUP_URL = f"{_CL_BASE}/api/rest/v4/citation-lookup/"
_SEARCH_URL = f"{_CL_BASE}/api/rest/v4/search/"


def _get_token() -> str | None:
    """Get CourtListener API token from environment.

    Checks COURTLISTENER_TOKEN first, then COURTLISTENER_API_KEY.
    """
    return os.environ.get("COURTLISTENER_TOKEN") or os.environ.get("COURTLISTENER_API_KEY")


def _auth_headers(token: str | None = None) -> dict:
    """Build auth headers if a token is available."""
    headers = {"User-Agent": _USER_AGENT}
    t = token or _get_token()
    if t:
        headers["Authorization"] = f"Token {t}"
    return headers


def courtlistener_url(reporter: str, volume: str, page: str) -> str:
    """Generate a CourtListener URL for a case citation."""
    encoded = quote(reporter, safe="")
    return f"{_CL_BASE}/c/{encoded}/{volume}/{page}/"


def courtlistener_neutral_url(jurisdiction: str, year: str, number: str) -> str:
    """Generate a CourtListener URL for a neutral citation."""
    return f"{_CL_BASE}/c/{jurisdiction}/{year}/{number}/"


def _clean_html_to_markdown(html: str) -> str:
    """Convert opinion HTML to clean markdown, preserving all text content.

    Walks the DOM tree recursively to capture text in any element, not just
    a fixed set of tags. This avoids dropping content wrapped in <div>, <span>,
    or bare text nodes.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Remove footnote markers and other cruft
    for tag in soup.find_all(["sup", "a"]):
        if tag.get("class") and "footnote" in " ".join(tag.get("class", [])):
            tag.decompose()

    # Remove scripts, styles, nav
    for tag in soup.find_all(["script", "style", "nav"]):
        tag.decompose()

    # Convert page-number tags to bracketed references so the asterisk
    # doesn't open spurious markdown italics (e.g. *380 -> [*380])
    for pn in soup.find_all("page-number"):
        label = pn.get("label", pn.get_text(strip=True))
        pn.replace_with(f" [{label}] ")

    return _walk_to_markdown(soup)


# Inline tags whose children should be flattened into a single text run
_INLINE_TAGS = frozenset({
    "a", "abbr", "b", "bdi", "bdo", "br", "cite", "code", "data",
    "del", "dfn", "em", "i", "ins", "kbd", "mark", "q", "rp", "rt",
    "ruby", "s", "samp", "small", "span", "strong", "sub", "sup",
    "time", "u", "var", "wbr",
    # CourtListener-specific inline elements
    "footnotemark", "footnote", "author",
})


def _walk_to_markdown(element) -> str:
    """Recursively walk DOM and convert to markdown, capturing all text."""
    blocks: list[str] = []
    _collect_blocks(element, blocks, depth=0)
    # Deduplicate consecutive blank lines
    lines = "\n\n".join(b for b in blocks if b)
    return lines.strip()


def _collect_blocks(element, blocks: list[str], depth: int) -> None:
    """Collect text blocks from the DOM tree."""
    from bs4 import NavigableString, Tag

    if isinstance(element, NavigableString):
        text = element.get_text(strip=False).strip()
        if text:
            blocks.append(text)
        return

    if not isinstance(element, Tag):
        return

    tag = element.name

    # Headings
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(tag[1])
        text = element.get_text(separator=" ", strip=True)
        if text:
            blocks.append(f"{'#' * level} {text}")
        return

    # Blockquotes — recurse into children (not self) to avoid infinite loop
    if tag == "blockquote":
        child_blocks: list[str] = []
        for child in element.children:
            _collect_blocks(child, child_blocks, depth + 1)
        inner = "\n\n".join(b for b in child_blocks if b)
        if inner:
            quoted = "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
            blocks.append(quoted)
        return

    # Paragraph and list items — leaf blocks whose content is flattened
    if tag in ("p", "li"):
        text = element.get_text(separator=" ", strip=True)
        if text:
            prefix = "- " if tag == "li" else ""
            blocks.append(f"{prefix}{text}")
        return

    # Pre/code blocks
    if tag == "pre":
        text = element.get_text()
        if text.strip():
            blocks.append(f"```\n{text.rstrip()}\n```")
        return

    # Inline elements — flatten into a single text run
    if tag in _INLINE_TAGS:
        text = element.get_text(separator=" ", strip=True)
        if text:
            blocks.append(text)
        return

    # Everything else (block-level, unknown/custom tags like <opinion>)
    # — recurse into children so paragraph structure is preserved
    child_blocks: list[str] = []
    for child in element.children:
        _collect_blocks(child, child_blocks, depth + 1)
    text = "\n\n".join(b for b in child_blocks if b)
    if text:
        blocks.append(text)


def fetch_courtlistener(
    source_url: str,
    citation: object,
    timeout: float = 10.0,
) -> tuple[str | None, dict, str | None]:
    """Fetch case opinion content from CourtListener.

    Strategy:
    1. If COURTLISTENER_TOKEN is set, use the Citation Lookup API (preferred)
       → get cluster → fetch opinion text from opinions endpoint
    2. Otherwise fall back to the search API (no auth, text inline)
    3. Last resort: scrape the /c/ redirect target

    Returns (markdown_content, metadata_dict, raw_html) or (None, {}, None) on failure.
    """
    normalized = citation.normalized if hasattr(citation, "normalized") else ""
    components = citation.components if hasattr(citation, "components") else {}

    token = _get_token()

    # Try Citation Lookup API (preferred) if we have a token
    if token and components.get("volume") and components.get("reporter") and components.get("page"):
        result = _fetch_via_citation_lookup(
            volume=components["volume"],
            reporter=components["reporter"],
            page=components["page"],
            normalized=normalized,
            token=token,
            timeout=timeout,
        )
        if result[0]:
            return result

    # Fallback: search API (no auth needed, returns text inline)
    search_cite = normalized or _cite_from_url(source_url)
    if search_cite:
        result = _fetch_via_search(search_cite, timeout)
        if result[0]:
            return result

    # Last resort: scrape the /c/ redirect target
    return _fetch_via_scrape(source_url, normalized, timeout)


# ── Citation Lookup API (preferred) ──────────────────────────────


def _fetch_via_citation_lookup(
    volume: str,
    reporter: str,
    page: str,
    normalized: str,
    token: str,
    timeout: float = 10.0,
) -> tuple[str | None, dict, str | None]:
    """Use the Citation Lookup REST API to find and fetch an opinion.

    POST /api/rest/v4/citation-lookup/ with volume/reporter/page
    → cluster metadata → GET /api/rest/v4/opinions/<id>/ for text.
    """
    headers = {"Authorization": f"Token {token}", "User-Agent": _USER_AGENT}

    # Step 1: Citation lookup
    try:
        resp = httpx.post(
            _LOOKUP_URL,
            data={"volume": volume, "reporter": reporter, "page": page},
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code >= 400:
            return None, {}, None
        results = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError):
        return None, {}, None

    if not results:
        return None, {}, None

    # Find first result with status 200 and clusters
    hit = None
    for r in results:
        if r.get("status") == 200 and r.get("clusters"):
            hit = r
            break
    if not hit:
        return None, {}, None

    cluster = hit["clusters"][0]
    case_name = cluster.get("case_name", "Unknown")
    date_filed = cluster.get("date_filed", "")
    court = cluster.get("court", "")

    # Step 2: Get opinion text from sub_opinions
    sub_opinions = cluster.get("sub_opinions", [])
    if not sub_opinions:
        # Try the cluster's absolute_url to find opinions
        cluster_url = cluster.get("resource_uri") or cluster.get("absolute_url", "")
        if cluster_url:
            sub_opinions = _get_sub_opinions(cluster_url, headers, timeout)

    body = None
    raw_html = None
    for op in sub_opinions:
        op_url = op if isinstance(op, str) else op.get("resource_uri", "")
        if not op_url:
            continue
        body, raw_html = _fetch_opinion_text(op_url, headers, timeout)
        if body:
            break

    if not body:
        return None, {}, None

    metadata = {
        "case_name": case_name,
        "date_filed": date_filed,
        "court": court,
    }

    md = _format_case_markdown(
        case_name=case_name,
        citation=normalized,
        court=court,
        date=date_filed,
        source="CourtListener Citation Lookup API",
        body=body,
    )
    return md, metadata, raw_html


def _get_sub_opinions(cluster_url: str, headers: dict, timeout: float) -> list:
    """Fetch a cluster to get its sub_opinions list."""
    if not cluster_url.startswith("http"):
        cluster_url = f"{_CL_BASE}{cluster_url}"

    try:
        resp = httpx.get(cluster_url, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            return []
        data = resp.json()
        return data.get("sub_opinions", [])
    except (httpx.HTTPError, httpx.TimeoutException, ValueError):
        return []


def _fetch_opinion_text(opinion_url: str, headers: dict, timeout: float) -> tuple[str | None, str | None]:
    """Fetch opinion text from the opinions endpoint.

    Tries fields in preference order: html_with_citations, html,
    xml_harvard, plain_text.

    Returns (markdown, raw_html) tuple.
    """
    if not opinion_url.startswith("http"):
        opinion_url = f"{_CL_BASE}{opinion_url}"

    try:
        resp = httpx.get(opinion_url, headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            return None, None
        data = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError):
        return None, None

    # Try HTML fields in preference order
    for field in ("html_with_citations", "html", "html_columbia",
                  "html_lawbox", "html_anon_2020"):
        html = data.get(field)
        if html:
            return _clean_html_to_markdown(html), html

    # Try XML (Harvard Caselaw Access Project)
    xml = data.get("xml_harvard")
    if xml:
        return _clean_html_to_markdown(xml), xml

    # Plain text fallback
    plain = data.get("plain_text")
    if plain:
        return plain.strip(), None

    return None, None


# ── Search API fallback (no auth) ───────────────────────────────


def _fetch_via_search(
    cite_query: str,
    timeout: float = 10.0,
) -> tuple[str | None, dict, str | None]:
    """Fetch opinion from CourtListener search API (no auth needed)."""
    params = {"type": "o", "cite": cite_query}

    try:
        resp = httpx.get(
            _SEARCH_URL,
            params=params,
            follow_redirects=True,
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        )
        if resp.status_code >= 400:
            return None, {}, None
        data = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException, ValueError):
        return None, {}, None

    results = data.get("results", [])
    if not results:
        return None, {}, None

    hit = results[0]
    case_name = hit.get("caseName", "Unknown")
    date_filed = hit.get("dateFiled", "")
    court = hit.get("court", "")

    # Search API returns text inline
    html_content = hit.get("html_with_citations") or hit.get("html") or ""
    plain_text = hit.get("plain_text") or ""
    raw_html = html_content or None

    if html_content:
        body = _clean_html_to_markdown(html_content)
    elif plain_text:
        body = plain_text.strip()
    else:
        return None, {}, None

    metadata = {
        "case_name": case_name,
        "date_filed": date_filed,
        "court": court,
    }

    md = _format_case_markdown(
        case_name=case_name,
        citation=cite_query,
        court=court,
        date=date_filed,
        source="CourtListener Search API",
        body=body,
    )
    return md, metadata, raw_html


# ── Scrape fallback ──────────────────────────────────────────────


def _cite_from_url(url: str) -> str | None:
    """Extract a rough citation string from a /c/ URL."""
    m = re.search(r"/c/([^/]+)/(\d+)/(\d+)", url)
    if m:
        return f"{m.group(2)} {m.group(1)} {m.group(3)}"
    return None


def _fetch_via_scrape(
    url: str,
    normalized: str,
    timeout: float = 10.0,
) -> tuple[str | None, dict, str | None]:
    """Scrape opinion text by following a /c/ redirect URL."""
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=timeout,
                         headers={"User-Agent": _USER_AGENT})
        if resp.status_code >= 400:
            return None, {}, None
    except (httpx.HTTPError, httpx.TimeoutException):
        return None, {}, None

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "html.parser")

    opinion_div = (
        soup.find(id="opinion-content")
        or soup.find("article")
        or soup.find(class_="opinion-content")
    )
    if not opinion_div:
        return None, {}, None

    raw_html = str(opinion_div)
    body = _clean_html_to_markdown(raw_html)
    if not body.strip():
        return None, {}, None

    title_tag = soup.find("title")
    case_name = title_tag.get_text(strip=True) if title_tag else "Unknown"
    case_name = re.sub(r"\s*[-–|].*CourtListener.*$", "", case_name)

    metadata = {"case_name": case_name}

    md = _format_case_markdown(
        case_name=case_name,
        citation=normalized,
        court="",
        date="",
        source=str(resp.url),
        body=body,
    )
    return md, metadata, raw_html


# ── Shared formatting ────────────────────────────────────────────


def _format_case_markdown(
    case_name: str,
    citation: str,
    court: str,
    date: str,
    source: str,
    body: str,
) -> str:
    """Format a case opinion as standardized markdown."""
    lines = [f"# {case_name}", ""]
    if citation:
        lines.append(f"**Citation:** {citation}")
    if court:
        lines.append(f"**Court:** {court}")
    if date:
        lines.append(f"**Date:** {date}")
    if source:
        lines.append(f"**Source:** {source}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)

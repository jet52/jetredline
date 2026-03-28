"""Justia URL generation and content extraction for U.S. Reports citations."""

from __future__ import annotations

import re

import httpx

_USER_AGENT = "jetcite/1.5 (legal-research-tool; https://github.com/jet52/jetcite)"


def us_reports_url(volume: str, page: str) -> str:
    """Generate a Justia URL for a U.S. Reports citation."""
    return f"https://supreme.justia.com/cases/federal/us/{volume}/{page}"


def fetch_justia(
    source_url: str,
    citation: object,
    timeout: float = 10.0,
) -> tuple[str | None, dict, str | None]:
    """Fetch SCOTUS opinion content from Justia.

    Extracts opinion text from the case page.
    Returns (markdown_content, metadata_dict, raw_html) or (None, {}, None) on failure.
    """
    try:
        resp = httpx.get(source_url, follow_redirects=True, timeout=timeout,
                         headers={"User-Agent": _USER_AGENT})
        if resp.status_code >= 400:
            return None, {}, None
    except (httpx.HTTPError, httpx.TimeoutException):
        return None, {}, None

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract case name from h1 or title
    h1 = soup.find("h1")
    case_name = h1.get_text(strip=True) if h1 else ""
    if not case_name:
        title_tag = soup.find("title")
        case_name = title_tag.get_text(strip=True) if title_tag else "Unknown"
        case_name = re.sub(r"\s*[-–|].*Justia.*$", "", case_name)

    # Extract opinion text — Justia puts it in #tab-opinion or similar containers
    opinion_div = (
        soup.find(id="tab-opinion")
        or soup.find(id="opinion")
        or soup.find(class_="tab-content")
    )

    if not opinion_div:
        # Try the main content area
        opinion_div = soup.find("div", class_="opinion-content")

    if not opinion_div:
        return None, {}, None

    raw_html = str(opinion_div)
    body = _extract_text(opinion_div)
    if not body.strip():
        return None, {}, None

    # Try to extract metadata from the sidebar or header
    metadata = {"case_name": case_name}

    normalized = citation.normalized if hasattr(citation, "normalized") else ""

    lines = [f"# {case_name}", ""]
    if normalized:
        lines.append(f"**Citation:** {normalized}")
    lines.append(f"**Court:** Supreme Court of the United States")
    lines.append(f"**Source:** {source_url}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(body)

    return "\n".join(lines), metadata, raw_html


# Inline tags whose children should be flattened into a single text run
_INLINE_TAGS = frozenset({
    "a", "abbr", "b", "bdi", "bdo", "br", "cite", "code", "data",
    "del", "dfn", "em", "i", "ins", "kbd", "mark", "q", "rp", "rt",
    "ruby", "s", "samp", "small", "span", "strong", "sub", "sup",
    "time", "u", "var", "wbr",
})


def _extract_text(element) -> str:
    """Extract readable text from a BeautifulSoup element.

    Walks the DOM tree recursively to capture text in any element, not just
    a fixed set of tags.
    """
    # Remove scripts, styles, nav
    for tag in element.find_all(["script", "style", "nav"]):
        tag.decompose()

    blocks: list[str] = []
    _collect_blocks(element, blocks)
    return "\n\n".join(b for b in blocks if b).strip()


def _collect_blocks(element, blocks: list[str]) -> None:
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
            _collect_blocks(child, child_blocks)
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

    # Everything else (block-level, unknown/custom tags)
    # — recurse into children so paragraph structure is preserved
    child_blocks: list[str] = []
    for child in element.children:
        _collect_blocks(child, child_blocks)
    text = "\n\n".join(b for b in child_blocks if b)
    if text:
        blocks.append(text)

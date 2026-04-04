"""Cornell LII URL generation and content extraction for federal rules."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

_USER_AGENT = "jetcite/1.5 (legal-research-tool; https://github.com/jet52/jetcite)"

# Rule set abbreviation -> LII URL path segment
_RULE_PATHS = {
    "frcp": "frcivp",
    "frcrp": "frcrmp",
    "fre": "fre",
    "frap": "frap",
    "frbp": "frbkp",
}


def federal_rule_url(rule_set: str, rule_number: str) -> str:
    """Generate a Cornell LII URL for a federal rule."""
    path = _RULE_PATHS.get(rule_set.lower(), rule_set.lower())
    return f"https://www.law.cornell.edu/rules/{path}/rule_{rule_number}"


def _extract_rule_text(soup: BeautifulSoup) -> str | None:
    """Extract federal rule text from a Cornell LII page.

    Tries several selectors to find the rule content area.
    """
    # Primary: the rule content div
    content = soup.select_one("div.field-name-body") or soup.select_one("#block-field-blocknoderulesfield-body")
    if not content:
        content = soup.select_one("article .content") or soup.select_one(".field--type-text-with-summary")
    if not content:
        return None

    lines = []
    for el in content.descendants:
        if el.name in ("script", "style", "nav"):
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            text = el.get_text(strip=True)
            if text:
                level = int(el.name[1])
                lines.append("")
                lines.append(f"{'#' * level} {text}")
                lines.append("")
        elif el.name == "p":
            text = el.get_text(" ", strip=True)
            if text:
                lines.append(text)
                lines.append("")
        elif el.name == "li":
            text = el.get_text(" ", strip=True)
            if text:
                lines.append(f"- {text}")
        elif el.name == "blockquote":
            text = el.get_text(" ", strip=True)
            if text:
                lines.append(f"> {text}")
                lines.append("")

    return "\n".join(lines).strip() if lines else None


def fetch_cornell(
    source_url: str,
    citation: object,
    timeout: float = 10.0,
) -> tuple[str | None, dict, str | None]:
    """Fetch federal rule content from Cornell LII.

    Returns (markdown_content, metadata_dict, raw_html) or (None, {}, None).
    """
    try:
        resp = httpx.get(source_url, follow_redirects=True, timeout=timeout,
                         headers={"User-Agent": _USER_AGENT})
        if resp.status_code >= 400:
            return None, {}, None
    except (httpx.HTTPError, httpx.TimeoutException):
        return None, {}, None

    raw_html = resp.text
    soup = BeautifulSoup(raw_html, "html.parser")

    # Extract title
    title_el = soup.select_one("h1.page-title") or soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else ""

    content = _extract_rule_text(soup)
    if not content:
        return None, {}, None

    lines = []
    if title:
        lines.append(f"# {title}")
        lines.append("")
    lines.append(content)
    lines.append("")

    metadata = {"title": title}
    return "\n".join(lines), metadata, raw_html

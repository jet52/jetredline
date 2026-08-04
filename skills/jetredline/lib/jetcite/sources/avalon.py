"""Avalon Project (Yale Law School) URLs for U.S. Constitution citations.

The Lillian Goldman Law Library's transcription — a scholarly copy, not the
official text, but the only reliable Constitution source that allows
cross-origin framing (no X-Frame-Options, no frame-ancestors, no
frame-busting; verified 2026-08-04). Consumers embed it as the reading pane
and pair it with the official constitution.congress.gov link, which cannot
be framed.

Link-only for jetcite itself: never fetched (no extractor, never the first
source), so the host lives in ``_egress.NON_FETCH_HOSTS``.

URL scheme:

- Articles I–VII: ``/18th_century/art{n}.asp`` with ``#{n}sec{s}`` section
  anchors (clause anchors exist but their naming is inconsistent — section
  level is the reliable grain).
- Amendments I–X: ``/18th_century/rights1.asp#{n}``.
- Amendments XI–XXVII: ``/18th_century/amend1.asp#{n}``.
"""

from __future__ import annotations

from jetcite.patterns.base import roman_to_int

_BASE = "https://avalon.law.yale.edu/18th_century"


def avalon_article_url(article_roman: str, section: str | None = None) -> str:
    """Avalon Project URL for a U.S. Constitution article."""
    n = roman_to_int(article_roman)
    base = f"{_BASE}/art{n}.asp"
    if section:
        return f"{base}#{n}sec{section}"
    return base


def avalon_amendment_url(amendment_roman: str) -> str:
    """Avalon Project URL for a U.S. Constitution amendment.

    Amendment-section pinpoints have no anchor on Avalon; the link lands on
    the amendment itself.
    """
    n = roman_to_int(amendment_roman)
    page = "rights1.asp" if n <= 10 else "amend1.asp"
    return f"{_BASE}/{page}#{n}"

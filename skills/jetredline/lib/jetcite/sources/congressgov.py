"""constitution.congress.gov URL generation for U.S. Constitution citations.

The Constitution Annotated, published by the Library of Congress for
Congress — the official government publication of the constitutional text.
URL scheme (verified 2026-08-04): ``/constitution/article-{n}/`` and
``/constitution/amendment-{n}/`` (Arabic numbers; articles 1–7, amendments
1–27, plus ``/constitution/preamble/``), with in-page section anchors
``#article-{n}-section-{s}`` / ``#amendment-{n}-section-{s}``.

The site serves browsers only (403 to non-browser clients) and sends
``X-Frame-Options: SAMEORIGIN``, so these URLs are effectively link-out:
consumers show them as the official source and open them in a tab.
"""

from __future__ import annotations

from jetcite.patterns.base import roman_to_int


def congress_article_url(article_roman: str, section: str | None = None) -> str:
    """Constitution Annotated URL for a U.S. Constitution article."""
    n = roman_to_int(article_roman)
    base = f"https://constitution.congress.gov/constitution/article-{n}/"
    if section:
        return f"{base}#article-{n}-section-{section}"
    return base


def congress_amendment_url(amendment_roman: str,
                           section: str | None = None) -> str:
    """Constitution Annotated URL for a U.S. Constitution amendment."""
    n = roman_to_int(amendment_roman)
    base = f"https://constitution.congress.gov/constitution/amendment-{n}/"
    if section:
        return f"{base}#amendment-{n}-section-{section}"
    return base

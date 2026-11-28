"""ndlaw.org link generation for North Dakota authority (link-only).

ndlaw.org resolves any citation, however spelled, through one endpoint:
``https://ndlaw.org/cite/{citation}``. It 301s to the authority's page and
keeps the pinpoint as a fragment where the page has that anchor (``¶ 17`` ->
``#p17``, ``510 N.W.2d 612, 616`` -> ``#star616``, ``N.D.R.Crim.P. 11(b)(1)``
-> ``#b-1``), and a case name settles two opinions printed on one first page.
So jetcite builds no ndlaw.org paths of its own: it hands over the citation.

Link-only, never fetched. ndlaw.org's robots.txt disallows crawling and the
site rate-limits automated clients, so the ``ndlaw`` source never becomes a
citation's primary (fetchable) URL; it rides at the end of ``sources`` and
surfaces through ``Citation.link_url`` when a caller prefers it (see
``jetcite.links``).
"""

from __future__ import annotations

from urllib.parse import quote

NDLAW_CITE_BASE = "https://ndlaw.org/cite/"


def ndlaw_cite_url(citation_text: str) -> str:
    """The ndlaw.org resolver URL for ``citation_text`` (any spelling, with or
    without a case name and pinpoint)."""
    return NDLAW_CITE_BASE + quote(" ".join(citation_text.split()), safe=",")

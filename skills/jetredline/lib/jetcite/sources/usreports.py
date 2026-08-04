"""Official-print PDF links for U.S. Reports citations.

Link-only source: these URLs are surfaced to reviewers (e.g. jetredline's
cite-review pane) but never fetched by jetcite — there is no extractor for
these hosts, and they are appended after the fetchable sources, so neither
the extractor loop nor the generic-fetch fallback in ``fetch_and_cache``
ever touches them. Both hosts are listed in ``_egress.NON_FETCH_HOSTS``.

Two publishers, checked in coverage order:

- Library of Congress: per-case scans of the official U.S. Reports bound
  volumes, vols 1–578. Keyed by volume and the case's first page, each
  zero-padded to three digits.
- supremecourt.gov: whole-volume bound-volume PDFs, vols 502–587, direct
  from the Court.

Volumes above 587 exist only as slip opinions keyed by term and docket
number, which cannot be derived from a U.S. Reports citation alone.

Coverage bounds probed 2026-08-04; bump the constants as new volumes are
published.
"""

from __future__ import annotations

#: Highest volume with per-case PDFs at the Library of Congress.
LOC_MAX_VOLUME = 578

#: Bound-volume PDFs available at supremecourt.gov (inclusive range).
SCOTUS_BV_MIN_VOLUME = 502
SCOTUS_BV_MAX_VOLUME = 587


def us_reports_official_pdf(volume: str, page: str) -> str | None:
    """Return an official-print PDF URL for a U.S. Reports cite, or None.

    Prefers the Library of Congress per-case scan (opens at the case);
    falls back to the Court's whole-volume bound PDF for 579–587.
    """
    try:
        vol, pg = int(volume), int(page)
    except (TypeError, ValueError):
        return None
    if 1 <= vol <= LOC_MAX_VOLUME:
        return (
            "https://tile.loc.gov/storage-services/service/ll/usrep/"
            f"usrep{vol:03d}/usrep{vol:03d}{pg:03d}/usrep{vol:03d}{pg:03d}.pdf"
        )
    if SCOTUS_BV_MIN_VOLUME <= vol <= SCOTUS_BV_MAX_VOLUME:
        return f"https://www.supremecourt.gov/opinions/boundvolumes/{vol}bv.pdf"
    return None

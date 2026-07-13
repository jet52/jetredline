"""apps.azsos.gov URL generation for the Arizona Administrative Code.

A.A.C. is published only as chapter-level PDFs by the Secretary of State, so a
citation resolves to its chapter document, not the individual rule. The section
component (e.g. the -201 in R20-6-201) has no addressable in-PDF anchor and is
not used in the URL. Verified structure (direct fetch is bot-blocked, 403):
  A.A.C. R20-6-201 -> https://apps.azsos.gov/public_services/Title_20/20-06.pdf
"""

from __future__ import annotations


def aac_chapter_url(title: str, chapter: str) -> str:
    """Generate an apps.azsos.gov URL for an A.A.C. chapter PDF.

    The folder segment pads the title to two digits (``Title_20``, ``Title_02``);
    the filename leaves the title unpadded but pads the chapter to two digits
    (``20-06.pdf``, ``2-06.pdf``).
    """
    return (
        f"https://apps.azsos.gov/public_services/"
        f"Title_{int(title):02d}/{title}-{int(chapter):02d}.pdf"
    )

"""ndlegis.gov URL generation for NDCC and NDAC citations."""


def _format_title_file(title: str, title_dec: str | None) -> str:
    """Format title for filename: decimal -> hyphenated, integer -> zero-padded."""
    if title_dec:
        return f"{title}-{title_dec}"
    return title.zfill(2)


def _format_chapter_file(chapter: str, chapter_dec: str | None) -> str:
    """Format chapter for filename."""
    if chapter_dec:
        return f"{chapter}-{chapter_dec}"
    return chapter.zfill(2)


def _format_dest(value: str, dec: str | None) -> str:
    """Format a component for the named destination anchor."""
    if dec:
        return f"{value}p{dec}"
    return value


def ndcc_section_url(
    title: str,
    chapter: str,
    section: str,
    title_dec: str | None = None,
    chapter_dec: str | None = None,
    section_dec: str | None = None,
) -> str | None:
    """Generate an ndlegis.gov URL for an NDCC section."""
    title_file = _format_title_file(title, title_dec)
    chapter_file = _format_chapter_file(chapter, chapter_dec)
    title_dest = _format_dest(title, title_dec)
    chapter_dest = _format_dest(chapter, chapter_dec)
    section_dest = _format_dest(section, section_dec)

    url = (
        f"https://ndlegis.gov/cencode/t{title_file}c{chapter_file}.pdf"
        f"#nameddest={title_dest}-{chapter_dest}-{section_dest}"
    )

    # Validation: reject obviously malformed URLs
    if "t--" in url or "c--" in url or "pp" in url:
        return None
    return url


def ndcc_chapter_url(
    title: str,
    chapter: str,
    title_dec: str | None = None,
    chapter_dec: str | None = None,
) -> str | None:
    """Generate an ndlegis.gov URL for an NDCC chapter."""
    title_file = _format_title_file(title, title_dec)
    chapter_file = _format_chapter_file(chapter, chapter_dec)

    url = f"https://ndlegis.gov/cencode/t{title_file}c{chapter_file}.pdf"
    if "t--" in url or "c--" in url:
        return None
    return url


def ndac_url(part1: str, part2: str, part3: str) -> str:
    """Generate an ndlegis.gov URL for an NDAC chapter."""
    return f"https://ndlegis.gov/information/acdata/pdf/{part1}-{part2}-{part3}.pdf"
